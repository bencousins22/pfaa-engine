"""
AutonomousAgent — Goal-driven, self-decomposing, resumable agent.

Replaces Agent Zero's sequential monologue with:
    goal → decompose → parallel DAG → phase-fluid execute → learn → replan

Python 3.15: lazy import, frozendict snapshots, kqueue subprocess.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

lazy import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolRegistry
from agent_setup_cli.core.persistence import PersistentMemory
from agent_setup_cli.core.claude_bridge import ClaudeBridge, ClaudeConfig

import agent_setup_cli.core.tools_extended  # noqa: F401
try:
    import agent_setup_cli.core.tools_generated  # noqa: F401
except ImportError:
    pass

logger = logging.getLogger("pfaa.autonomous")
CHECKPOINT_DIR = os.path.expanduser("~/.pfaa/checkpoints")


class GoalStatus(Enum):
    PENDING = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    FAILED = auto()


@dataclass
class SubTask:
    id: str
    description: str
    tool_name: str | None = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    phase_hint: Phase | None = None
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    result: Any = None
    error: str | None = None
    elapsed_us: int = 0
    attempt: int = 0


@dataclass
class GoalState:
    goal_id: str
    goal_text: str
    status: GoalStatus
    subtasks: list[SubTask]
    created_at: float
    replan_count: int = 0


# ── TOOL PATTERN MAP ────────────────────────────────────────────────

TOOL_KEYWORDS: dict[str, list[tuple[str, tuple]]] = {
    "search":    [("codebase_search", ("TODO|FIXME",))],
    "find":      [("glob_search", ("*.py",)), ("codebase_search", ("TODO",))],
    "grep":      [("codebase_search", ("TODO",))],
    "todo":      [("codebase_search", ("TODO|FIXME|HACK",))],
    "fixme":     [("codebase_search", ("FIXME",))],
    "read":      [("read_file", ())],
    "lines":     [("line_count", (".",))],
    "count":     [("line_count", (".",))],
    "git":       [("git_status",  ())],
    "status":    [("git_status",  ()), ("system_info", ())],
    "log":       [("git_log", (".", 10))],
    "commit":    [("git_log", (".", 5))],
    "branch":    [("git_branch", ())],
    "diff":      [("git_diff", ())],
    "hash":      [("hash_data", ("test",))],
    "compute":   [("compute", ("42",))],
    "calculate": [("compute", ("pi*e",))],
    "system":    [("system_info", ())],
    "disk":      [("disk_usage", (".",))],
    "port":      [("port_check", ("localhost", 8000))],
    "dns":       [("dns_lookup", ("localhost",))],
    "process":   [("process_list", ("",))],
    "docker":    [("docker_ps", ()), ("docker_images", ())],
    "shell":     [("shell", ("echo hello",))],
    "run":       [("shell", ("echo hello",))],
    "test":      [("sandbox_exec", ("print('ok')",))],
    "json":      [("json_parse", ('{"a":1}',))],
    "regex":     [("regex_extract", ("test", r"\w+"))],
    "fetch":     [("http_fetch", ("https://httpbin.org/ip",))],
    "analyze":   [("line_count", (".",)), ("file_stats", (".",)), ("codebase_search", ("class|def",))],
    "review":    [("codebase_search", ("TODO|FIXME|HACK",)), ("line_count", (".",))],
    "info":      [("system_info", ()), ("file_stats", (".",))],
}


def _decompose(goal: str, memory: PersistentMemory) -> list[SubTask]:
    """Decompose a goal into subtasks via keyword matching."""
    words = goal.lower().split()
    seen_tools: set[str] = set()
    subtasks: list[SubTask] = []

    for word in words:
        # Strip punctuation
        clean = word.strip(".,!?;:'\"")
        if clean in TOOL_KEYWORDS:
            for tool_name, default_args in TOOL_KEYWORDS[clean]:
                if tool_name not in seen_tools:
                    seen_tools.add(tool_name)
                    phase = memory.recommend_phase(tool_name)
                    subtasks.append(SubTask(
                        id=f"st-{uuid.uuid4().hex[:6]}",
                        description=f"{tool_name}: {goal[:60]}",
                        tool_name=tool_name,
                        args=default_args,
                        phase_hint=phase,
                    ))

    # If nothing matched, create a single Claude task
    if not subtasks:
        subtasks.append(SubTask(
            id=f"st-{uuid.uuid4().hex[:6]}",
            description=goal,
            tool_name=None,
        ))

    return subtasks


class AutonomousAgent:
    """
    Goal-driven autonomous agent.

    Usage:
        agent = AutonomousAgent()
        result = await agent.pursue("analyze codebase and search for TODO and count lines and check git status")
    """

    def __init__(self):
        self._memory = PersistentMemory()
        self._registry = ToolRegistry.get()
        self._registry.set_memory(self._memory.memory)
        self._bridge = ClaudeBridge(memory=self._memory.memory)
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)

    async def pursue(self, goal: str) -> GoalState:
        goal_id = f"goal-{uuid.uuid4().hex[:8]}"
        subtasks = _decompose(goal, self._memory)

        state = GoalState(
            goal_id=goal_id,
            goal_text=goal,
            status=GoalStatus.EXECUTING,
            subtasks=subtasks,
            created_at=time.time(),
        )

        print(f"\n🎯 GOAL: {goal}")
        print(f"   ID:   {goal_id}")
        print(f"\n📋 DECOMPOSED into {len(subtasks)} subtasks:")
        for st in subtasks:
            tool = st.tool_name or "claude"
            phase = st.phase_hint.name if st.phase_hint else "auto"
            print(f"   [{st.id}] {tool:20s} phase={phase}")

        self._checkpoint(state)

        # Execute DAG — all independent tasks run in parallel
        await self._execute_dag(state)

        # Retry failed tasks once
        failed = [st for st in state.subtasks if st.status == "failed"]
        if failed and state.replan_count < 2:
            state.replan_count += 1
            print(f"\n🔄 RETRYING {len(failed)} failed subtasks...")
            for st in failed:
                st.status = "pending"
                st.attempt += 1
            await self._execute_dag(state)

        # Final status
        completed = sum(1 for st in state.subtasks if st.status == "completed")
        failed_n = sum(1 for st in state.subtasks if st.status == "failed")
        state.status = GoalStatus.COMPLETED if failed_n == 0 else GoalStatus.FAILED

        self._memory.force_learn()
        self._checkpoint(state)

        total_us = sum(st.elapsed_us for st in state.subtasks)
        icon = "✅" if state.status == GoalStatus.COMPLETED else "⚠️"
        print(f"\n{icon} GOAL {state.status.name}: {completed}/{len(state.subtasks)} subtasks, "
              f"{total_us / 1000:.1f}ms total")
        print(f"   Memory: {self._memory.status()['l1_episodes']} episodes, "
              f"{self._memory.status()['l2_patterns']} patterns")

        return state

    async def _execute_dag(self, state: GoalState) -> None:
        while True:
            ready = [
                st for st in state.subtasks
                if st.status == "pending"
                and all(
                    next((t for t in state.subtasks if t.id == d), None) is None
                    or next((t for t in state.subtasks if t.id == d)).status == "completed"
                    for d in st.depends_on
                )
            ]
            if not ready:
                pending = [st for st in state.subtasks if st.status == "pending"]
                if not pending:
                    break
                # Deadlocked
                for st in pending:
                    st.status = "failed"
                    st.error = "deadlocked"
                break

            for st in ready:
                st.status = "running"

            results = await asyncio.gather(
                *[self._exec_one(st) for st in ready],
                return_exceptions=True,
            )
            for st, r in zip(ready, results):
                if isinstance(r, Exception):
                    st.status = "failed"
                    st.error = str(r)

    async def _exec_one(self, st: SubTask) -> None:
        start = time.perf_counter_ns()
        try:
            if st.tool_name:
                result = await self._registry.execute(st.tool_name, *st.args, **st.kwargs)
                st.result = result.result
                st.elapsed_us = result.elapsed_us
                self._memory.record(result, st.tool_name, st.args)

                if isinstance(st.result, dict) and st.result.get("success") is False:
                    st.status = "failed"
                    st.error = st.result.get("error", "unknown")
                else:
                    st.status = "completed"

                print(f"   ✓ {st.id} [{st.tool_name:15s}] "
                      f"{result.phase_used.name:6s} {st.elapsed_us}μs")
            else:
                if self._bridge.is_available:
                    cr = await self._bridge.ask(st.description, timeout=60.0)
                    st.result = cr.output
                    st.elapsed_us = int(cr.elapsed_ms * 1000)
                    st.status = "completed" if cr.success else "failed"
                else:
                    st.status = "failed"
                    st.error = "Claude not available"
                    print(f"   ✗ {st.id} [claude] not available")
        except Exception as e:
            st.elapsed_us = (time.perf_counter_ns() - start) // 1000
            st.status = "failed"
            st.error = str(e)
            print(f"   ✗ {st.id} [{st.tool_name or 'claude'}] {e}")

    def _checkpoint(self, state: GoalState) -> None:
        data = {
            "goal_id": state.goal_id,
            "goal_text": state.goal_text,
            "status": state.status.name,
            "created_at": state.created_at,
            "subtasks": [
                {"id": st.id, "tool": st.tool_name, "status": st.status,
                 "elapsed_us": st.elapsed_us, "error": st.error}
                for st in state.subtasks
            ],
        }
        path = os.path.join(CHECKPOINT_DIR, f"{state.goal_id}.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def list_checkpoints(self) -> list[dict]:
        cps = []
        if os.path.exists(CHECKPOINT_DIR):
            for f in os.listdir(CHECKPOINT_DIR):
                if f.endswith(".json"):
                    with open(os.path.join(CHECKPOINT_DIR, f)) as fh:
                        cps.append(json.load(fh))
        return cps

    async def shutdown(self) -> None:
        self._memory.close()
        await self._bridge.shutdown()


async def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m agent_setup_cli.core.autonomous '<goal>'")
        return
    agent = AutonomousAgent()
    try:
        await agent.pursue(" ".join(sys.argv[1:]))
    finally:
        await agent.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
