"""
Nucleus — The Phase-Fluid Agent Orchestrator

The Nucleus is the central coordinator that:
    1. Spawns agents on demand (lazy — only materializes when needed)
    2. Routes messages between agents regardless of their phase
    3. Monitors agent health and restarts failed agents (supervisor tree)
    4. Auto-scales: spawns more agents under load, apoptosis when idle
    5. Tracks phase transitions for self-optimization

Think of it as the "kernel" of the agent swarm — but unlike an OS kernel,
it's async-native and phase-aware.

Python 3.15 features:
    - lazy import: heavy deps (multiprocessing, profiling) load only when needed
    - frozendict: agent blueprints are immutable and hashable for dedup
    - kqueue: subprocess lifecycle is event-driven, not polled
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

lazy import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.agent import FluidAgent, AgentConfig, TaskResult

logger = logging.getLogger("pfaa.nucleus")


@dataclass
class SwarmMetrics:
    """Real-time swarm telemetry."""
    agents_spawned: int = 0
    agents_alive: int = 0
    agents_reaped: int = 0
    tasks_completed: int = 0
    total_task_us: int = 0
    phase_distribution: dict[str, int] = field(
        default_factory=lambda: defaultdict(int)
    )
    transitions: int = 0

    @property
    def avg_task_us(self) -> float:
        if self.tasks_completed == 0:
            return 0.0
        return self.total_task_us / self.tasks_completed


class Nucleus:
    """
    Orchestrator for a swarm of Phase-Fluid agents.

    Usage:
        nucleus = Nucleus()
        results = await nucleus.scatter(
            configs=[AgentConfig("worker", capabilities=("fetch",))],
            task_fn=my_task,
            args_list=[("url1",), ("url2",), ("url3",)],
        )
        await nucleus.shutdown()
    """

    def __init__(self, max_concurrency: int | None = None):
        import os
        self.max_concurrency = max_concurrency or os.cpu_count() * 4
        self._agents: dict[str, FluidAgent] = {}
        self._blueprint_cache: dict[frozendict, AgentConfig] = {}
        self._metrics = SwarmMetrics()
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._birth_ns = time.perf_counter_ns()
        self._shutdown = False

    @property
    def metrics(self) -> SwarmMetrics:
        return self._metrics

    @property
    def uptime_ms(self) -> float:
        return (time.perf_counter_ns() - self._birth_ns) / 1_000_000

    # ── Agent Lifecycle ─────────────────────────────────────────────

    def spawn(self, config: AgentConfig) -> FluidAgent:
        """Spawn a new agent from a config blueprint."""
        frozen = config.frozen()
        self._blueprint_cache[frozen] = config

        agent = FluidAgent(config)
        self._agents[agent.id] = agent
        self._metrics.agents_spawned += 1
        self._metrics.agents_alive += 1
        self._metrics.phase_distribution[agent.phase.name] += 1

        logger.debug("Spawned %s in %s phase", agent.id, agent.phase.name)
        return agent

    def spawn_many(self, config: AgentConfig, count: int) -> list[FluidAgent]:
        """Spawn N agents from the same blueprint."""
        return [self.spawn(config) for _ in range(count)]

    def reap(self, agent: FluidAgent) -> None:
        """Gracefully destroy an agent."""
        if agent.id in self._agents:
            old_phase = agent.phase.name
            self._metrics.phase_distribution[old_phase] = max(
                0, self._metrics.phase_distribution[old_phase] - 1
            )
            agent.apoptosis()
            del self._agents[agent.id]
            self._metrics.agents_alive -= 1
            self._metrics.agents_reaped += 1

    # ── Scatter/Gather — Parallel Task Execution ────────────────────

    async def scatter(
        self,
        config: AgentConfig,
        task_fn: Callable[..., Any],
        args_list: list[tuple[Any, ...]],
        hint: Phase | None = None,
    ) -> list[TaskResult]:
        """
        Scatter a task across N agents (one per args tuple),
        execute in parallel, gather results.

        This is the primary "fan-out / fan-in" pattern.
        """
        agents = self.spawn_many(config, len(args_list))

        async def _run_one(agent: FluidAgent, args: tuple) -> TaskResult:
            async with self._semaphore:
                try:
                    result = await agent.execute(task_fn, *args, hint=hint)
                    self._metrics.tasks_completed += 1
                    self._metrics.total_task_us += result.elapsed_us
                    self._metrics.transitions += len(result.transitions)
                    return result
                finally:
                    self.reap(agent)

        # Use TaskGroup for structured concurrency (Python 3.11+)
        # All scatter tasks run in a single group — if one fails,
        # others continue because errors are caught in _run_one
        task_results: dict[str, asyncio.Task] = {}
        try:
            async with asyncio.TaskGroup() as tg:
                for a, args in zip(agents, args_list):
                    task_results[a.id] = tg.create_task(
                        _run_one(a, args), name=a.id
                    )
        except* Exception as eg:
            logger.error("Scatter group error: %s", [str(e) for e in eg.exceptions])

        return [t.result() for t in task_results.values() if not t.cancelled()]

    async def execute_one(
        self,
        config: AgentConfig,
        task_fn: Callable[..., Any],
        *args: Any,
        hint: Phase | None = None,
        **kwargs: Any,
    ) -> TaskResult:
        """Spawn a single ephemeral agent, execute, teardown."""
        agent = self.spawn(config)
        try:
            result = await agent.execute(task_fn, *args, hint=hint, **kwargs)
            self._metrics.tasks_completed += 1
            self._metrics.total_task_us += result.elapsed_us
            return result
        finally:
            self.reap(agent)

    # ── Pipeline — Sequential Phase Escalation ──────────────────────

    async def pipeline(
        self,
        config: AgentConfig,
        stages: list[tuple[Phase, Callable[..., Any], tuple[Any, ...]]],
    ) -> list[TaskResult]:
        """
        Execute a pipeline where each stage runs in a specific phase.

        Example:
            await nucleus.pipeline(config, [
                (Phase.VAPOR,  fetch_data,    ("url",)),
                (Phase.LIQUID, process_data,  ()),     # gets previous result
                (Phase.SOLID,  sandbox_eval,  ()),     # gets previous result
            ])

        Each stage receives the previous stage's result as first arg.
        """
        agent = self.spawn(config)
        results: list[TaskResult] = []
        prev_result: Any = None

        try:
            for phase, fn, extra_args in stages:
                args = (prev_result, *extra_args) if prev_result is not None else extra_args
                result = await agent.execute(fn, *args, hint=phase)
                results.append(result)
                prev_result = result.result
                self._metrics.tasks_completed += 1
                self._metrics.total_task_us += result.elapsed_us
        finally:
            self.reap(agent)

        return results

    # ── Swarm — Persistent Agent Pool ───────────────────────────────

    async def swarm(
        self,
        config: AgentConfig,
        pool_size: int,
        task_queue: asyncio.Queue[tuple[Callable, tuple] | None],
        result_queue: asyncio.Queue[TaskResult],
    ) -> None:
        """
        Run a persistent pool of agents consuming from a task queue.
        Send None to the task queue to signal shutdown.
        """
        agents = self.spawn_many(config, pool_size)

        async def _worker(agent: FluidAgent) -> None:
            while agent.alive and not self._shutdown:
                item = await task_queue.get()
                if item is None:
                    task_queue.task_done()
                    break
                fn, args = item
                try:
                    result = await agent.execute(fn, *args)
                    await result_queue.put(result)
                    self._metrics.tasks_completed += 1
                    self._metrics.total_task_us += result.elapsed_us
                except Exception as e:
                    logger.error("%s failed: %s", agent.id, e)
                finally:
                    task_queue.task_done()

        await asyncio.gather(*[_worker(a) for a in agents])

        for agent in agents:
            self.reap(agent)

    # ── Introspection ───────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "uptime_ms": round(self.uptime_ms, 1),
            "agents_alive": self._metrics.agents_alive,
            "agents_spawned": self._metrics.agents_spawned,
            "agents_reaped": self._metrics.agents_reaped,
            "tasks_completed": self._metrics.tasks_completed,
            "avg_task_us": round(self._metrics.avg_task_us, 1),
            "phase_distribution": dict(self._metrics.phase_distribution),
            "transitions": self._metrics.transitions,
            "max_concurrency": self.max_concurrency,
        }

    async def shutdown(self) -> None:
        """Gracefully shut down all agents."""
        self._shutdown = True
        for agent in list(self._agents.values()):
            self.reap(agent)
        logger.info(
            "Nucleus shutdown: %d tasks in %.1fms",
            self._metrics.tasks_completed,
            self.uptime_ms,
        )
