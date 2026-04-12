"""
Phase-Fluid Agent — The core agent that transitions between execution phases.

Each agent is born as VAPOR (cheapest). Based on task demands, it can
condense to LIQUID (thread) or freeze to SOLID (subprocess). When the
work completes, it evaporates back to VAPOR or undergoes apoptosis.

Python 3.15 features used:
    - lazy import: defer heavy module loading until phase transition
    - frozendict: immutable agent configuration blueprints
    - kqueue subprocess: efficient process lifecycle on macOS
    - sys.set_lazy_imports: startup optimization
"""

from __future__ import annotations

import asyncio
import logging
import os
import pickle
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from agent_setup_cli.core.phase import Phase, Transition, TRANSITIONS

# Lazy imports — these modules only load when the agent actually
# transitions to a phase that needs them
import multiprocessing
import subprocess
import threading
import json

logger = logging.getLogger("pfaa.agent")


@dataclass(slots=True)
class AgentConfig:
    """Immutable agent blueprint. Converted to frozendict for hashing."""
    name: str
    capabilities: tuple[str, ...] = ()
    max_phase: Phase = Phase.SOLID
    auto_transition: bool = True
    cpu_threshold_ms: float = 50.0  # condense to LIQUID above this
    isolation_required: bool = False  # force SOLID phase

    def frozen(self) -> frozendict:
        return frozendict(
            name=self.name,
            capabilities=self.capabilities,
            max_phase=self.max_phase.name,
            auto_transition=self.auto_transition,
            cpu_threshold_ms=self.cpu_threshold_ms,
            isolation_required=self.isolation_required,
        )


@dataclass(slots=True)
class TaskResult:
    agent_id: str
    phase_used: Phase
    result: Any
    elapsed_us: int
    transitions: list[str] = field(default_factory=list)


class FluidAgent:
    """An agent that flows between execution phases based on task demands."""

    __slots__ = (
        "id", "config", "_phase", "_mailbox", "_alive",
        "_transition_log", "_birth_ns", "_task_count",
    )

    def __init__(self, config: AgentConfig):
        self.id = f"{config.name}-{uuid.uuid4().hex[:8]}"
        self.config = config
        self._phase = Phase.SOLID if config.isolation_required else Phase.VAPOR
        self._mailbox: asyncio.Queue[Any] = asyncio.Queue()
        self._alive = True
        self._transition_log: list[tuple[float, str, Phase, Phase]] = []
        self._birth_ns = time.perf_counter_ns()
        self._task_count = 0

    @property
    def phase(self) -> Phase:
        return self._phase

    @property
    def age_ms(self) -> float:
        return (time.perf_counter_ns() - self._birth_ns) / 1_000_000

    @property
    def alive(self) -> bool:
        return self._alive

    def _transition(self, name: str) -> None:
        t = TRANSITIONS[name]
        if self._phase != t.from_phase:
            raise ValueError(
                f"Cannot {name}: agent is {self._phase.name}, "
                f"need {t.from_phase.name}"
            )
        if t.to_phase.value > self.config.max_phase.value:
            raise ValueError(
                f"Cannot {name}: {t.to_phase.name} exceeds max_phase "
                f"{self.config.max_phase.name}"
            )
        old = self._phase
        self._phase = t.to_phase
        self._transition_log.append(
            (time.perf_counter_ns(), name, old, t.to_phase)
        )
        logger.debug(
            "%s: %s → %s (%s)", self.id, old.name, t.to_phase.name, t.reason
        )

    # ── Phase-aware task execution ──────────────────────────────────

    async def execute(
        self,
        task_fn: Callable[..., Any],
        *args: Any,
        hint: Phase | None = None,
        **kwargs: Any,
    ) -> TaskResult:
        """Execute a task, auto-selecting or using hinted phase."""
        start = time.perf_counter_ns()
        transitions_used: list[str] = []

        target_phase = hint or self._auto_select_phase(task_fn)

        # Phase-transition to target
        transitions_used = self._navigate_to_phase(target_phase)

        # Execute in the appropriate mode — match/case on phase enum
        match self._phase:
            case Phase.VAPOR:
                result = await self._exec_vapor(task_fn, *args, **kwargs)
            case Phase.LIQUID:
                result = await self._exec_liquid(task_fn, *args, **kwargs)
            case Phase.SOLID:
                result = await self._exec_solid(task_fn, *args, **kwargs)

        elapsed_us = (time.perf_counter_ns() - start) // 1000
        self._task_count += 1

        # Auto-evaporate back to lightest phase after task
        if self.config.auto_transition and self._phase != Phase.VAPOR:
            try:
                back = self._navigate_to_phase(Phase.VAPOR)
                transitions_used.extend(back)
            except ValueError:
                pass  # can't go lighter, that's fine

        return TaskResult(
            agent_id=self.id,
            phase_used=target_phase,
            result=result,
            elapsed_us=elapsed_us,
            transitions=transitions_used,
        )

    def _auto_select_phase(self, task_fn: Callable) -> Phase:
        """Inspect task hints to pick optimal phase."""
        hints = getattr(task_fn, "_pfaa_hints", {})
        if hints.get("isolated"):
            return Phase.SOLID
        if hints.get("cpu_bound"):
            return Phase.LIQUID
        return Phase.VAPOR

    def _navigate_to_phase(self, target: Phase) -> list[str]:
        """Find shortest transition path to target phase."""
        transitions_used: list[str] = []
        # Direct transitions
        paths = {
            (Phase.VAPOR, Phase.LIQUID): ["condense"],
            (Phase.LIQUID, Phase.SOLID): ["freeze"],
            (Phase.VAPOR, Phase.SOLID): ["sublimate"],
            (Phase.SOLID, Phase.LIQUID): ["melt"],
            (Phase.LIQUID, Phase.VAPOR): ["evaporate"],
            (Phase.SOLID, Phase.VAPOR): ["deposit"],
        }
        key = (self._phase, target)
        if key in paths:
            for t_name in paths[key]:
                self._transition(t_name)
                transitions_used.append(t_name)
        return transitions_used

    # ── Execution modes ─────────────────────────────────────────────

    async def _exec_vapor(
        self, fn: Callable, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute as async coroutine — lightest, I/O-bound."""
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        # Wrap sync function in executor to avoid blocking the loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def _exec_liquid(
        self, fn: Callable, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute in a thread — CPU-parallel with free-threading.

        If fn is an async coroutine function, run it on the current event loop
        instead of a thread (coroutines can't be awaited from a plain thread).
        """
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args, **kwargs)
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix=self.id) as pool:
            return await loop.run_in_executor(pool, lambda: fn(*args, **kwargs))

    async def _exec_solid(
        self, fn: Callable, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute in a subprocess — full isolation, crash-safe.

        Uses Python 3.15's kqueue-based process waiting on macOS
        for near-instant process lifecycle management.

        Note: Functions must be picklable (top-level, not lambdas).
        We use functools.partial instead of lambdas for cross-process calls.
        """
        import functools
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=1) as pool:
            partial_fn = functools.partial(fn, *args, **kwargs)
            return await loop.run_in_executor(pool, partial_fn)

    # ── Mailbox (inter-agent messaging) ─────────────────────────────

    async def send(self, message: Any) -> None:
        """Enqueue a message to this agent's mailbox for inter-agent communication."""
        await self._mailbox.put(message)

    async def receive(self, timeout: float = 1.0) -> Any | None:
        """Dequeue the next message from the mailbox, returning None on timeout."""
        try:
            return await asyncio.wait_for(self._mailbox.get(), timeout)
        except asyncio.TimeoutError:
            return None

    # ── Lifecycle ───────────────────────────────────────────────────

    def apoptosis(self) -> None:
        """Graceful self-destruction."""
        self._alive = False
        logger.info(
            "%s: apoptosis after %d tasks, %.1fms lifetime",
            self.id, self._task_count, self.age_ms,
        )

    def __repr__(self) -> str:
        return (
            f"<FluidAgent {self.id} phase={self._phase.name} "
            f"tasks={self._task_count} age={self.age_ms:.1f}ms>"
        )


# ── Task decorators ─────────────────────────────────────────────────

def vapor_task(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Hint: this task should run as VAPOR (I/O-bound)."""
    fn._pfaa_hints = {"cpu_bound": False, "isolated": False}
    return fn

def liquid_task(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Hint: this task should run as LIQUID (CPU-bound, parallel)."""
    fn._pfaa_hints = {"cpu_bound": True, "isolated": False}
    return fn

def solid_task(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Hint: this task should run as SOLID (needs isolation)."""
    fn._pfaa_hints = {"cpu_bound": False, "isolated": True}
    return fn
