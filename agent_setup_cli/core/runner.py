"""
PFAA Runner — Minimal end-to-end goal execution.

Wires up: Orchestrator → Nucleus → Tools pipeline.

Usage:
    import asyncio
    from agent_setup_cli.core.runner import run_goal
    results = asyncio.run(run_goal("compute 2+2", tools=["compute"]))

Or with the full task graph:
    results = asyncio.run(run_goal(
        "read and hash a file",
        tools=["read_file", "hash_data"],
        tool_args={"read_file": {"path": "README.md"}},
    ))
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_setup_cli.core.orchestrator import Orchestrator, TaskNode
from agent_setup_cli.core.tools import ToolRegistry

logger = logging.getLogger("pfaa.runner")


async def run_goal(
    goal: str,
    tools: list[str] | None = None,
    tool_args: dict[str, dict[str, Any]] | None = None,
    parallel: bool = True,
) -> list[TaskNode]:
    """Execute a goal through the Orchestrator → Nucleus → Tools pipeline.

    Args:
        goal: Human-readable description of the goal (logged for tracing).
        tools: List of tool names to execute. If None, lists available tools.
        tool_args: Per-tool keyword arguments, keyed by tool name.
        parallel: If True (default), all tools run concurrently.
                  If False, tools run sequentially (each depends on previous).

    Returns:
        List of completed TaskNode objects with results.
    """
    tool_args = tool_args or {}
    registry = ToolRegistry.get()
    orchestrator = Orchestrator()

    logger.info("Goal: %s", goal)

    if not tools:
        available = registry.list_tools()
        logger.info("No tools specified. Available: %s", [t.name for t in available])
        return []

    # Submit tasks to the orchestrator
    prev_id: str | None = None
    for name in tools:
        if registry.get_tool(name) is None:
            raise ValueError(f"Unknown tool: {name!r}. Available: {[t.name for t in registry.list_tools()]}")
        kwargs = tool_args.get(name, {})
        deps = [prev_id] if (not parallel and prev_id) else None
        task_id = orchestrator.submit(name, depends_on=deps, **kwargs)
        prev_id = task_id

    # Execute all tasks
    results = await orchestrator.run_all()
    await orchestrator.shutdown()

    logger.info(
        "Goal complete: %d tasks, %s",
        len(results),
        orchestrator.graph_summary(),
    )
    return results
