"""
Supervisor Tree — Hierarchical agent delegation with fault recovery.

Replaces Agent Zero's flat call_subordinate with a proper supervisor tree
where parent agents spawn, monitor, and restart child agents.

Architecture:
    Supervisor
    ├── Worker (compute)     ← restarts on failure
    ├── Worker (search)      ← restarts on failure
    └── Supervisor (nested)  ← escalates failures up
        ├── Worker (fetch)
        └── Worker (parse)

Python 3.15: lazy import, frozendict for immutable tree snapshots.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.agent import FluidAgent, AgentConfig, TaskResult
from agent_setup_cli.core.nucleus import Nucleus

logger = logging.getLogger("pfaa.delegation")


class RestartPolicy(Enum):
    ALWAYS = auto()      # restart on any failure
    NEVER = auto()       # let it die
    ON_ERROR = auto()    # restart on exception, not on normal exit
    TRANSIENT = auto()   # restart only if exit was abnormal


@dataclass(slots=True)
class WorkerSpec:
    """Blueprint for a worker in the supervisor tree."""
    name: str
    task_fn: Callable
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    phase: Phase = Phase.VAPOR
    restart_policy: RestartPolicy = RestartPolicy.ON_ERROR
    max_restarts: int = 3


@dataclass(slots=True)
class WorkerState:
    """Runtime state of a managed worker."""
    spec: WorkerSpec
    id: str = field(default_factory=lambda: f"w-{uuid.uuid4().hex[:6]}")
    status: str = "idle"       # idle, running, completed, failed, restarting
    result: Any = None
    error: str | None = None
    restarts: int = 0
    elapsed_us: int = 0


class Supervisor:
    """
    Manages a tree of workers with fault recovery.

    Usage:
        sup = Supervisor("data-pipeline")
        sup.add_worker(WorkerSpec("fetch", fetch_fn, args=("url",), phase=Phase.VAPOR))
        sup.add_worker(WorkerSpec("parse", parse_fn, phase=Phase.LIQUID))
        sup.add_worker(WorkerSpec("store", store_fn, phase=Phase.SOLID))
        results = await sup.run_all()
    """

    def __init__(self, name: str, nucleus: Nucleus | None = None):
        self.name = name
        self.id = f"sup-{uuid.uuid4().hex[:6]}"
        self._nucleus = nucleus or Nucleus()
        self._workers: list[WorkerState] = []
        self._children: list[Supervisor] = []
        self._start_ns: int = 0

    def add_worker(self, spec: WorkerSpec) -> str:
        """Add a worker to this supervisor. Returns worker ID."""
        state = WorkerState(spec=spec)
        self._workers.append(state)
        return state.id

    def add_child_supervisor(self, child: Supervisor) -> None:
        """Add a nested supervisor."""
        self._children.append(child)

    async def run_all(self) -> dict[str, Any]:
        """Run all workers in parallel, handling restarts."""
        self._start_ns = time.perf_counter_ns()

        # Run workers + child supervisors concurrently via TaskGroup
        worker_coros = [self._run_worker(w) for w in self._workers]
        child_coros = [c.run_all() for c in self._children]
        all_coros = worker_coros + child_coros

        all_results: list[Any] = []
        try:
            async with asyncio.TaskGroup() as tg:
                task_handles = [tg.create_task(c) for c in all_coros]
            all_results = [t.result() for t in task_handles]
        except* Exception as eg:
            # Collect partial results and exceptions
            for i, t in enumerate(task_handles):
                if t.done() and t.exception() is None:
                    all_results.append(t.result())
                else:
                    all_results.append(t.exception() if t.done() else None)

        elapsed_ms = (time.perf_counter_ns() - self._start_ns) / 1_000_000

        # Separate worker results from child results
        n_workers = len(self._workers)
        worker_results = all_results[:n_workers]
        child_results = all_results[n_workers:]

        # Handle any TaskGroup exceptions
        for i, result in enumerate(worker_results):
            if isinstance(result, Exception) and i < len(self._workers):
                self._workers[i].status = "failed"
                self._workers[i].error = str(result)

        completed = sum(1 for w in self._workers if w.status == "completed")
        failed = sum(1 for w in self._workers if w.status == "failed")
        total_restarts = sum(w.restarts for w in self._workers)

        return {
            "supervisor": self.name,
            "workers": len(self._workers),
            "completed": completed,
            "failed": failed,
            "restarts": total_restarts,
            "children": len(self._children),
            "child_results": [r for r in child_results if not isinstance(r, Exception)],
            "elapsed_ms": round(elapsed_ms, 1),
            "worker_details": [
                {
                    "name": w.spec.name,
                    "status": w.status,
                    "phase": w.spec.phase.name,
                    "restarts": w.restarts,
                    "elapsed_us": w.elapsed_us,
                    "error": w.error,
                }
                for w in self._workers
            ],
        }

    async def _run_worker(self, worker: WorkerState) -> None:
        """Run a single worker with restart policy enforcement."""
        while True:
            worker.status = "running"
            config = AgentConfig(
                name=f"{self.name}-{worker.spec.name}",
                capabilities=("worker",),
                max_phase=worker.spec.phase,
                isolation_required=(worker.spec.phase == Phase.SOLID),
            )

            start = time.perf_counter_ns()
            try:
                result = await self._nucleus.execute_one(
                    config, worker.spec.task_fn,
                    *worker.spec.args, hint=worker.spec.phase,
                    **worker.spec.kwargs,
                )
                worker.result = result.result
                worker.elapsed_us = result.elapsed_us
                worker.status = "completed"
                return

            except Exception as e:
                worker.elapsed_us = (time.perf_counter_ns() - start) // 1000
                worker.error = str(e)

                should_restart = (
                    worker.spec.restart_policy in (RestartPolicy.ALWAYS, RestartPolicy.ON_ERROR)
                    and worker.restarts < worker.spec.max_restarts
                )

                if should_restart:
                    worker.restarts += 1
                    worker.status = "restarting"
                    logger.warning(
                        "%s/%s restarting (%d/%d): %s",
                        self.name, worker.spec.name,
                        worker.restarts, worker.spec.max_restarts, e,
                    )
                    await asyncio.sleep(0.01 * worker.restarts)  # backoff
                    continue
                else:
                    worker.status = "failed"
                    logger.error(
                        "%s/%s failed permanently: %s",
                        self.name, worker.spec.name, e,
                    )
                    return

    def tree_snapshot(self) -> frozendict:
        """Immutable snapshot of the entire supervisor tree."""
        return frozendict(
            name=self.name,
            workers=tuple(
                frozendict(name=w.spec.name, status=w.status, restarts=w.restarts)
                for w in self._workers
            ),
            children=tuple(c.tree_snapshot() for c in self._children),
        )
