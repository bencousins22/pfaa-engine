"""
Aussie Agents Orchestrator — The brain that decides WHAT to do and HOW to do it.

This is the top-level coordinator that:
    1. Accepts natural language or structured task descriptions
    2. Decomposes tasks into tool calls
    3. Decides which tools to run in parallel vs. sequential
    4. Manages the Nucleus lifecycle
    5. Provides a Claude Code-compatible interface

The Orchestrator implements a "Reactive Task Graph" — it doesn't plan
everything upfront. Instead, it reacts to intermediate results and
dynamically spawns new agent-tool pairs as needed.

Python 3.15 features:
    - lazy import: only loads AI/networking when needed
    - frozendict: task descriptors are immutable snapshots
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

lazy import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolRegistry, ToolSpec
from agent_setup_cli.core.agent import TaskResult
from agent_setup_cli.core.nucleus import Nucleus

logger = logging.getLogger("pfaa.orchestrator")


class TaskStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class TaskNode:
    """A node in the reactive task graph."""
    id: str
    tool_name: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: TaskResult | None = None
    error: str | None = None
    depends_on: list[str] = field(default_factory=list)
    elapsed_us: int = 0

    def frozen_descriptor(self) -> frozendict:
        return frozendict(
            id=self.id,
            tool_name=self.tool_name,
            status=self.status.name,
        )


class Orchestrator:
    """
    Reactive task graph executor.

    Instead of building a full DAG upfront, the orchestrator:
    1. Starts with initial tasks
    2. As results arrive, may spawn follow-up tasks
    3. Runs independent tasks in parallel automatically
    4. Tracks the full execution graph for observability
    """

    def __init__(self):
        self._registry = ToolRegistry.get()
        self._tasks: dict[str, TaskNode] = {}
        self._completed: list[TaskNode] = []
        self._birth_ns = time.perf_counter_ns()

    @property
    def uptime_ms(self) -> float:
        return (time.perf_counter_ns() - self._birth_ns) / 1_000_000

    # ── Task Submission ─────────────────────────────────────────────

    def submit(
        self,
        tool_name: str,
        *args: Any,
        depends_on: list[str] | None = None,
        **kwargs: Any,
    ) -> str:
        """Submit a task and return its ID."""
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        node = TaskNode(
            id=task_id,
            tool_name=tool_name,
            args=args,
            kwargs=kwargs,
            depends_on=depends_on or [],
        )
        self._tasks[task_id] = node
        return task_id

    # ── Execution ───────────────────────────────────────────────────

    async def run_all(self) -> list[TaskNode]:
        """
        Execute all submitted tasks, respecting dependencies.
        Independent tasks run in parallel automatically.
        """
        while True:
            ready = self._get_ready_tasks()
            if not ready:
                # Check if we're done or deadlocked
                pending = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
                if not pending:
                    break
                running = [t for t in self._tasks.values() if t.status == TaskStatus.RUNNING]
                if not running and pending:
                    logger.error("Deadlock: %d pending tasks with unmet dependencies", len(pending))
                    for t in pending:
                        t.status = TaskStatus.FAILED
                        t.error = "deadlocked"
                    break
                # Wait for running tasks to complete
                await asyncio.sleep(0.001)
                continue

            # Execute all ready tasks in parallel
            results = await asyncio.gather(
                *[self._execute_task(t) for t in ready],
                return_exceptions=True,
            )

            for task, result in zip(ready, results):
                if isinstance(result, Exception):
                    task.status = TaskStatus.FAILED
                    task.error = str(result)
                    logger.error("Task %s failed: %s", task.id, result)

        return list(self._tasks.values())

    async def run_one(self, tool_name: str, *args: Any, **kwargs: Any) -> TaskResult:
        """Quick single-tool execution without task graph overhead."""
        return await self._registry.execute(tool_name, *args, **kwargs)

    async def run_parallel(
        self, calls: list[tuple[str, tuple, dict]]
    ) -> list[TaskResult]:
        """Execute multiple tools in parallel (convenience method)."""
        return await self._registry.execute_many(calls)

    # ── Internal ────────────────────────────────────────────────────

    def _get_ready_tasks(self) -> list[TaskNode]:
        """Find tasks whose dependencies are all completed."""
        ready = []
        for task in self._tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            deps_met = all(
                self._tasks[dep].status == TaskStatus.COMPLETED
                for dep in task.depends_on
                if dep in self._tasks
            )
            if deps_met:
                ready.append(task)
        return ready

    async def _execute_task(self, task: TaskNode) -> None:
        """Execute a single task node."""
        task.status = TaskStatus.RUNNING
        start = time.perf_counter_ns()

        try:
            # Inject dependency results into kwargs if needed
            dep_results = {}
            for dep_id in task.depends_on:
                dep = self._tasks.get(dep_id)
                if dep and dep.result:
                    dep_results[dep_id] = dep.result.result

            # Pass dependency results as metadata, not as kwargs
            # (tools don't know about the DAG — keep them clean)
            result = await self._registry.execute(
                task.tool_name, *task.args, **task.kwargs
            )
            if dep_results:
                result = TaskResult(
                    agent_id=result.agent_id,
                    phase_used=result.phase_used,
                    result={**(result.result if isinstance(result.result, dict) else {"value": result.result}), "_deps": dep_results},
                    elapsed_us=result.elapsed_us,
                    transitions=result.transitions,
                )
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.elapsed_us = (time.perf_counter_ns() - start) // 1000
            self._completed.append(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.elapsed_us = (time.perf_counter_ns() - start) // 1000
            raise

    # ── Introspection ───────────────────────────────────────────────

    def graph_summary(self) -> dict[str, Any]:
        """Return a summary of the task execution graph."""
        by_status = {}
        for task in self._tasks.values():
            status = task.status.name
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total_tasks": len(self._tasks),
            "by_status": by_status,
            "completed": len(self._completed),
            "total_elapsed_us": sum(t.elapsed_us for t in self._completed),
            "tools_used": list(set(t.tool_name for t in self._tasks.values())),
            "registry": self._registry.status(),
        }

    async def shutdown(self) -> None:
        await self._registry.shutdown()
