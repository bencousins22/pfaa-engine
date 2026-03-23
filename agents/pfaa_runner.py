#!/usr/bin/env python3
"""
PFAA Agent Runner — Claude Code entry point.

This script is invoked by Claude Code agents via Bash. It exposes
every PFAA capability as a simple CLI command with JSON output.

Usage from Claude Code:
    python3 agents/pfaa_runner.py tool compute "sqrt(42) * pi"
    python3 agents/pfaa_runner.py goal "search for TODO and count lines"
    python3 agents/pfaa_runner.py status
    python3 agents/pfaa_runner.py tools
    python3 agents/pfaa_runner.py memory
    python3 agents/pfaa_runner.py pipeline search:codebase_search:TODO count:line_count:. git:git_status
    python3 agents/pfaa_runner.py explore 100
    python3 agents/pfaa_runner.py self-build

All output is JSON for easy parsing by Claude Code agents.

Python 3.15: lazy import throughout.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import logging

lazy import json

# Ensure the package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Route ALL logging + print-based progress to stderr so stdout is pure JSON
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

# Monkey-patch the built-in print to go to stderr when running as agent
_original_print = print
def _stderr_print(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    _original_print(*args, **kwargs)

import builtins
builtins.print = _stderr_print

from agent_setup_cli.core.framework import Framework
from agent_setup_cli.core.streaming import EventType


def _json_out(data: dict) -> None:
    """Print JSON to stdout for Claude Code consumption."""
    _original_print(json.dumps(data, indent=2, default=str))


async def cmd_tool(fw: Framework, args: list[str]) -> None:
    """Execute a single PFAA tool."""
    if len(args) < 1:
        _json_out({"error": "Usage: tool <name> [args...]"})
        return
    name = args[0]
    tool_args = tuple(args[1:])
    start = time.perf_counter_ns()
    try:
        result = await fw.tool(name, *tool_args)
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        _json_out({"success": True, "tool": name, "result": result, "elapsed_ms": round(elapsed_ms, 1)})
    except Exception as e:
        _json_out({"success": False, "tool": name, "error": str(e)})


async def cmd_tools(fw: Framework, args: list[str]) -> None:
    """List all available tools."""
    tools = fw._registry.list_tools()
    _json_out({
        "tools": [
            {"name": t.name, "phase": t.phase.name, "description": t.description,
             "isolated": t.isolated, "capabilities": list(t.capabilities)}
            for t in sorted(tools, key=lambda t: t.name)
        ],
        "count": len(tools),
    })


async def cmd_goal(fw: Framework, args: list[str]) -> None:
    """Execute a natural language goal."""
    if not args:
        _json_out({"error": "Usage: goal '<natural language goal>'"})
        return
    goal_text = " ".join(args)
    state = await fw.run(goal_text)
    _json_out({
        "goal_id": state.goal_id,
        "goal": state.goal_text,
        "status": state.status.name,
        "subtasks": [
            {"id": st.id, "tool": st.tool_name or "claude", "status": st.status,
             "elapsed_us": st.elapsed_us, "error": st.error,
             "result": _safe(st.result)}
            for st in state.subtasks
        ],
        "completed": sum(1 for st in state.subtasks if st.status == "completed"),
        "total": len(state.subtasks),
    })


async def cmd_status(fw: Framework, args: list[str]) -> None:
    """Show framework status."""
    _json_out(fw.status())


async def cmd_memory(fw: Framework, args: list[str]) -> None:
    """Show memory status + learned patterns + strategies."""
    _json_out({
        "status": fw._memory.status(),
        "patterns": fw.learned_patterns(),
        "strategies": fw.learned_strategies(),
    })


async def cmd_pipeline(fw: Framework, args: list[str]) -> None:
    """Run a supervised pipeline. Format: name:tool:arg name:tool:arg ..."""
    if not args:
        _json_out({"error": "Usage: pipeline name:tool:arg [name:tool:arg ...]"})
        return
    steps = []
    for spec in args:
        parts = spec.split(":", 2)
        if len(parts) < 2:
            _json_out({"error": f"Invalid step format: {spec}. Use name:tool:arg"})
            return
        name = parts[0]
        tool = parts[1]
        tool_args = tuple(parts[2:]) if len(parts) > 2 else ()
        steps.append((name, tool, tool_args))

    result = await fw.pipeline(steps)
    _json_out(result)


async def cmd_parallel(fw: Framework, args: list[str]) -> None:
    """Run multiple tools in parallel. Format: tool:arg [tool:arg ...]"""
    if not args:
        _json_out({"error": "Usage: parallel tool:arg [tool:arg ...]"})
        return
    calls = []
    for spec in args:
        parts = spec.split(":", 1)
        tool = parts[0]
        tool_args = (parts[1],) if len(parts) > 1 else ()
        calls.append((tool, tool_args))

    results = await fw.tools(calls)
    _json_out({"results": results, "count": len(results)})


async def cmd_explore(fw: Framework, args: list[str]) -> None:
    """Run exploration rounds to train L3 strategies."""
    import random
    n = int(args[0]) if args else 100

    sync_tools = [
        ("compute", ("sqrt(42)",)),
        ("hash_data", ("test",)),
        ("line_count", (".",)),
    ]

    phase_counts: dict[str, int] = {}
    for i in range(n):
        tool_name, tool_args = sync_tools[i % len(sync_tools)]
        result = await fw.tool(tool_name, *tool_args)
        # We need to get the phase from the raw result
        raw = await fw._registry.execute(tool_name, *tool_args)
        fw._memory.record(raw, tool_name, tool_args)
        key = f"{tool_name}/{raw.phase_used.name}"
        phase_counts[key] = phase_counts.get(key, 0) + 1

    fw._memory.force_learn()

    _json_out({
        "rounds": n,
        "phase_distribution": phase_counts,
        "patterns": fw.learned_patterns(),
        "strategies": fw.learned_strategies(),
        "memory": fw._memory.status(),
    })


async def cmd_self_build(fw: Framework, args: list[str]) -> None:
    """Run self-improvement cycle."""
    result = await fw.self_build(auto_apply="--apply" in args)
    _json_out({
        "introspection": result.get("introspection"),
        "diagnosis_count": len(result.get("diagnosis", [])),
        "proposals": len(result.get("proposals", [])),
        "applied": result.get("applied", 0),
    })


async def cmd_checkpoints(fw: Framework, args: list[str]) -> None:
    """List saved goal checkpoints."""
    _json_out({"checkpoints": fw.checkpoints()})


def _safe(obj):
    """Safely serialize for JSON."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in list(obj.items())[:50]}
    if isinstance(obj, (list, tuple)):
        return [_safe(v) for v in obj[:50]]
    return str(obj)[:500]


COMMANDS = {
    "tool": cmd_tool,
    "tools": cmd_tools,
    "goal": cmd_goal,
    "status": cmd_status,
    "memory": cmd_memory,
    "pipeline": cmd_pipeline,
    "parallel": cmd_parallel,
    "explore": cmd_explore,
    "self-build": cmd_self_build,
    "checkpoints": cmd_checkpoints,
}


async def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        _json_out({
            "commands": list(COMMANDS.keys()),
            "usage": "python3 agents/pfaa_runner.py <command> [args...]",
            "examples": [
                "tool compute 'sqrt(42) * pi'",
                "goal 'search for TODO and count lines'",
                "parallel compute:sqrt(2) hash_data:hello system_info",
                "pipeline search:codebase_search:TODO count:line_count:.",
                "explore 100",
                "status",
                "memory",
                "self-build",
            ],
        })
        return

    cmd_name = sys.argv[1]
    cmd_args = sys.argv[2:]

    if cmd_name not in COMMANDS:
        _json_out({"error": f"Unknown command: {cmd_name}", "available": list(COMMANDS.keys())})
        sys.exit(1)

    fw = Framework()
    try:
        await COMMANDS[cmd_name](fw, cmd_args)
    finally:
        await fw.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
