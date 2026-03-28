"""
Aussie Agents Framework — The complete agent framework entry point.

This is the replacement for Agent Zero's monologue loop. Instead of:
    Agent Zero: while True → LLM → tool → LLM → response (sequential)

Aussie Agents does:
    Framework.run(goal) → decompose → parallel DAG → phase-fluid execute
                        → stream events → learn → checkpoint → respond

The Framework class ties together:
    - AutonomousAgent (goal decomposition + DAG execution)
    - Supervisor tree (hierarchical delegation)
    - EventBus (real-time streaming to frontends)
    - PersistentMemory (5-layer meta-learning)
    - ToolRegistry (27+ phase-aware tools)
    - ClaudeBridge (Claude Code subprocess integration)

Python 3.15: lazy import, frozendict, kqueue subprocess.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

lazy import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolRegistry
from agent_setup_cli.core.persistence import PersistentMemory
from agent_setup_cli.core.autonomous import AutonomousAgent, GoalState, GoalStatus
from agent_setup_cli.core.delegation import Supervisor, WorkerSpec, RestartPolicy
from agent_setup_cli.core.streaming import EventBus, EventType
from agent_setup_cli.core.claude_bridge import ClaudeBridge, ClaudeConfig

import agent_setup_cli.core.tools_extended  # noqa: F401
try:
    import agent_setup_cli.core.tools_generated  # noqa: F401
except ImportError:
    pass

logger = logging.getLogger("pfaa")


class Framework:
    """
    The Aussie Agents Framework — a complete agent system.

    Usage:
        # Minimal
        fw = Framework()
        result = await fw.run("analyze codebase and find security issues")

        # With event streaming (for WebSocket/frontend)
        fw = Framework()
        fw.on_event(lambda e: print(e.to_json()))
        result = await fw.run("search for TODO and count lines")

        # Supervised pipeline
        fw = Framework()
        result = await fw.pipeline([
            ("search", "codebase_search", ("TODO",)),
            ("count",  "line_count",      (".",)),
            ("status", "git_status",      ()),
        ])

        # Direct tool execution
        result = await fw.tool("compute", "sqrt(42) * pi")
    """

    def __init__(self, storage_dir: str | None = None):
        self._memory = PersistentMemory(
            storage_dir=storage_dir or os.path.expanduser("~/.pfaa"),
        )
        self._registry = ToolRegistry.get()
        self._registry.set_memory(self._memory.memory)
        self._bus = EventBus.get()
        self._agent = AutonomousAgent.__new__(AutonomousAgent)
        self._agent._memory = self._memory
        self._agent._registry = self._registry
        self._agent._bridge = ClaudeBridge(memory=self._memory.memory)
        os.makedirs(os.path.expanduser("~/.pfaa/checkpoints"), exist_ok=True)
        self._start_ns = time.perf_counter_ns()

    @property
    def uptime_ms(self) -> float:
        return (time.perf_counter_ns() - self._start_ns) / 1_000_000

    # ── Event Streaming ─────────────────────────────────────────────

    def on_event(self, handler) -> None:
        """Subscribe to ALL framework events."""
        self._bus.subscribe_all(handler)

    def on(self, event_type: EventType, handler) -> None:
        """Subscribe to a specific event type."""
        self._bus.subscribe(event_type, handler)

    # ── Goal Execution ──────────────────────────────────────────────

    async def run(self, goal: str) -> GoalState:
        """
        Execute a natural language goal.

        Decomposes into subtasks, executes in parallel,
        learns from results, streams events.
        """
        await self._bus.emit(EventType.GOAL_STARTED, {
            "goal": goal,
        })

        state = await self._agent.pursue(goal)

        event_type = (
            EventType.GOAL_COMPLETED
            if state.status == GoalStatus.COMPLETED
            else EventType.GOAL_FAILED
        )
        await self._bus.emit(event_type, {
            "goal": goal,
            "goal_id": state.goal_id,
            "completed": sum(1 for st in state.subtasks if st.status == "completed"),
            "failed": sum(1 for st in state.subtasks if st.status == "failed"),
            "total": len(state.subtasks),
        })

        return state

    # ── Direct Tool Execution ───────────────────────────────────────

    async def tool(self, name: str, *args: Any, **kwargs: Any) -> dict:
        """Execute a single tool and return its result."""
        await self._bus.emit(EventType.TASK_STARTED, {"tool": name})

        result = await self._registry.execute(name, *args, **kwargs)
        self._memory.record(result, name, args)

        await self._bus.emit(EventType.TASK_COMPLETED, {
            "tool": name,
            "phase": result.phase_used.name,
            "elapsed_us": result.elapsed_us,
        })

        return result.result

    async def tools(self, calls: list[tuple[str, tuple]]) -> list[dict]:
        """Execute multiple tools in parallel."""
        results = await self._registry.execute_many([
            (name, args, {}) for name, args in calls
        ])
        outputs = []
        for r in results:
            if isinstance(r, Exception):
                outputs.append({"success": False, "error": str(r)})
            else:
                outputs.append(r.result)
        return outputs

    # ── Supervised Pipeline ─────────────────────────────────────────

    async def pipeline(
        self,
        steps: list[tuple[str, str, tuple]],
        restart_policy: RestartPolicy = RestartPolicy.ON_ERROR,
    ) -> dict[str, Any]:
        """
        Run a supervised pipeline of tool executions.

        Each step is (name, tool_name, args).
        All steps run in parallel with automatic restart on failure.
        """
        sup = Supervisor("pipeline")

        for step_name, tool_name, args in steps:
            entry = self._registry.get_tool(tool_name)
            if entry is None:
                raise ValueError(f"Unknown tool: {tool_name}")
            spec, fn = entry

            sup.add_worker(WorkerSpec(
                name=step_name,
                task_fn=fn,
                args=args,
                phase=spec.phase,
                restart_policy=restart_policy,
            ))

        return await sup.run_all()

    # ── Hierarchical Delegation ─────────────────────────────────────

    async def delegate(
        self,
        name: str,
        workers: list[WorkerSpec],
        children: list[tuple[str, list[WorkerSpec]]] | None = None,
    ) -> dict[str, Any]:
        """
        Create a supervisor tree and execute.

        Example:
            await fw.delegate("analysis", [
                WorkerSpec("search", search_fn, args=("TODO",)),
                WorkerSpec("count", count_fn),
            ], children=[
                ("git-ops", [
                    WorkerSpec("status", git_status_fn),
                    WorkerSpec("log", git_log_fn),
                ]),
            ])
        """
        sup = Supervisor(name)

        for worker in workers:
            sup.add_worker(worker)

        if children:
            for child_name, child_workers in children:
                child_sup = Supervisor(child_name)
                for w in child_workers:
                    child_sup.add_worker(w)
                sup.add_child_supervisor(child_sup)

        return await sup.run_all()

    # ── Self-Improvement ────────────────────────────────────────────

    async def self_build(self, auto_apply: bool = False) -> dict:
        """Run a self-improvement cycle."""
        from agent_setup_cli.core.self_build import SelfBuilder
        builder = SelfBuilder()
        try:
            return await builder.build_self(auto_apply=auto_apply)
        finally:
            await builder.shutdown()

    # ── Introspection ───────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        mem = self._memory.status()
        tools = self._registry.list_tools()
        return {
            "uptime_ms": round(self.uptime_ms, 1),
            "tools": len(tools),
            "tools_by_phase": {
                "VAPOR": len([t for t in tools if t.phase == Phase.VAPOR]),
                "LIQUID": len([t for t in tools if t.phase == Phase.LIQUID]),
                "SOLID": len([t for t in tools if t.phase == Phase.SOLID]),
            },
            "memory": {
                "episodes": mem["l1_episodes"],
                "patterns": mem["l2_patterns"],
                "strategies": mem["l3_strategies"],
                "learning_rate": mem["l4_learning_rate"],
                "knowledge": mem["l5_knowledge"],
                "db_size_kb": mem["db_size_kb"],
            },
            "events": self._bus.total_events,
            "claude_available": self._agent._bridge.is_available,
        }

    def learned_patterns(self) -> dict:
        """Return all learned L2 patterns."""
        return self._memory.dump().get("patterns", {})

    def learned_strategies(self) -> dict:
        """Return all L3 phase optimization strategies."""
        return self._memory.dump().get("strategies", {})

    def checkpoints(self) -> list[dict]:
        """List saved goal checkpoints."""
        return self._agent.list_checkpoints()

    # ── Cleanup ─────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        """Graceful shutdown — flush memory, close connections."""
        self._memory.close()
        await self._agent._bridge.shutdown()
        await self._bus.emit(EventType.SYSTEM_STATUS, {"action": "shutdown"})
        logger.info("Framework shutdown after %.1fms", self.uptime_ms)


# ── Convenience function ────────────────────────────────────────────

async def run(goal: str, **kwargs) -> GoalState:
    """One-liner: run a goal and return results."""
    fw = Framework(**kwargs)
    try:
        return await fw.run(goal)
    finally:
        await fw.shutdown()
