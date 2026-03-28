"""
Aussie Agents Claude Code Agent Definitions.

These functions are designed to be called from Claude Code's Agent tool.
Each function is a self-contained agent that:
    1. Imports Aussie Agents lazily (Python 3.15)
    2. Executes a specific capability
    3. Returns structured JSON results
    4. Records execution in persistent memory

Usage from Claude Code (via Bash tool):
    python3 -c "from agents.claude_agents import analyst; analyst('search for security issues')"

Or via the runner:
    python3 agents/pfaa_runner.py goal "search for security issues"
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

lazy import json


def _run(coro):
    return asyncio.run(coro)


def analyst(goal: str) -> str:
    """
    Aussie Agents Analyst — Decomposes and executes natural language goals.

    Spawned by Claude Code when a complex analysis task needs to be
    broken into parallel subtasks across multiple tools.

    Example goals:
        "analyze codebase and find security issues"
        "search for TODO and count lines and check git"
        "review code structure and find hardcoded secrets"
    """
    async def _go():
        from agent_setup_cli.core.framework import Framework
        fw = Framework()
        try:
            state = await fw.run(goal)
            return json.dumps({
                "agent": "pfaa-analyst",
                "goal": goal,
                "status": state.status.name,
                "subtasks": [
                    {"tool": st.tool_name or "claude", "status": st.status,
                     "elapsed_us": st.elapsed_us}
                    for st in state.subtasks
                ],
                "completed": sum(1 for st in state.subtasks if st.status == "completed"),
                "total": len(state.subtasks),
                "memory_episodes": fw.status()["memory"]["episodes"],
            }, indent=2, default=str)
        finally:
            await fw.shutdown()

    result = _run(_go())
    print(result)
    return result


def searcher(pattern: str, root: str = ".", context: int = 2) -> str:
    """
    Aussie Agents Searcher — Code pattern search with context lines.

    Runs in LIQUID phase (threaded) for CPU-parallel file scanning.
    """
    async def _go():
        from agent_setup_cli.core.framework import Framework
        fw = Framework()
        try:
            result = await fw.tool("codebase_search", pattern, root, context, "*.py")
            return json.dumps({
                "agent": "pfaa-searcher",
                "pattern": pattern,
                "matches": result.get("total_matches", 0),
                "files_searched": result.get("files_searched", 0),
                "results": result.get("results", [])[:20],
            }, indent=2, default=str)
        finally:
            await fw.shutdown()

    result = _run(_go())
    print(result)
    return result


def git_ops(repo: str = ".") -> str:
    """
    Aussie Agents Git Agent — Parallel git operations (status + log + diff + branches).

    All run in SOLID phase (subprocess isolation) simultaneously.
    """
    async def _go():
        from agent_setup_cli.core.framework import Framework
        fw = Framework()
        try:
            results = await fw.tools([
                ("git_status", (repo,)),
                ("git_log", (repo, 10)),
                ("git_diff", (repo,)),
                ("git_branch", (repo,)),
            ])
            return json.dumps({
                "agent": "pfaa-git",
                "status": results[0],
                "log": results[1],
                "diff": results[2],
                "branches": results[3],
            }, indent=2, default=str)
        finally:
            await fw.shutdown()

    result = _run(_go())
    print(result)
    return result


def system_check() -> str:
    """
    Aussie Agents System Agent — Parallel system diagnostics.

    Runs system_info + disk_usage + port_check + process_list in VAPOR phase.
    """
    async def _go():
        from agent_setup_cli.core.framework import Framework
        fw = Framework()
        try:
            results = await fw.tools([
                ("system_info", ()),
                ("disk_usage", (".",)),
                ("port_check", ("localhost", 8000)),
                ("line_count", (".", ".py")),
            ])
            return json.dumps({
                "agent": "pfaa-system",
                "system": results[0],
                "disk": results[1],
                "port_8000": results[2],
                "code_lines": results[3],
            }, indent=2, default=str)
        finally:
            await fw.shutdown()

    result = _run(_go())
    print(result)
    return result


def pipeline_agent(*steps: str) -> str:
    """
    Aussie Agents Pipeline Agent — Supervised parallel execution with restart policies.

    Steps format: "name:tool:arg"
    Example: pipeline_agent("search:codebase_search:TODO", "count:line_count:.", "git:git_status")
    """
    async def _go():
        from agent_setup_cli.core.framework import Framework
        fw = Framework()
        try:
            parsed = []
            for spec in steps:
                parts = spec.split(":", 2)
                name = parts[0]
                tool = parts[1] if len(parts) > 1 else parts[0]
                args = tuple(parts[2:]) if len(parts) > 2 else ()
                parsed.append((name, tool, args))

            result = await fw.pipeline(parsed)
            return json.dumps({
                "agent": "pfaa-pipeline",
                "result": result,
            }, indent=2, default=str)
        finally:
            await fw.shutdown()

    result = _run(_go())
    print(result)
    return result


def explorer(rounds: int = 100) -> str:
    """
    Aussie Agents Explorer Agent — Trains L3 strategies via epsilon-greedy exploration.

    Runs N tool executions with phase exploration to discover optimal
    phase selections. Results persist to ~/.pfaa/memory.db.
    """
    async def _go():
        from agent_setup_cli.core.framework import Framework
        fw = Framework()
        try:
            sync_tools = [
                ("compute", ("sqrt(42)",)),
                ("hash_data", ("test",)),
                ("line_count", (".",)),
            ]
            for i in range(rounds):
                name, args = sync_tools[i % len(sync_tools)]
                result = await fw._registry.execute(name, *args)
                fw._memory.record(result, name, args)

            fw._memory.force_learn()
            return json.dumps({
                "agent": "pfaa-explorer",
                "rounds": rounds,
                "patterns": fw.learned_patterns(),
                "strategies": fw.learned_strategies(),
                "memory": fw._memory.status(),
            }, indent=2, default=str)
        finally:
            await fw.shutdown()

    result = _run(_go())
    print(result)
    return result


def self_builder(auto_apply: bool = False) -> str:
    """
    Aussie Agents Self-Builder Agent — Introspects and improves its own codebase.

    1. Analyzes own source code
    2. Diagnoses improvements
    3. Generates new tools (optional: auto-applies)
    4. Records learning
    """
    async def _go():
        from agent_setup_cli.core.framework import Framework
        fw = Framework()
        try:
            result = await fw.self_build(auto_apply=auto_apply)
            return json.dumps({
                "agent": "pfaa-self-builder",
                "introspection": result.get("introspection"),
                "diagnosis_count": len(result.get("diagnosis", [])),
                "diagnosis": result.get("diagnosis", [])[:10],
                "proposals": len(result.get("proposals", [])),
                "applied": result.get("applied", 0),
            }, indent=2, default=str)
        finally:
            await fw.shutdown()

    result = _run(_go())
    print(result)
    return result


# ── CLI dispatch ────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Available agents: analyst, searcher, git_ops, system_check, pipeline, explorer, self_builder")
        sys.exit(0)

    agent = sys.argv[1]
    args = sys.argv[2:]

    agents = {
        "analyst": lambda: analyst(" ".join(args)),
        "searcher": lambda: searcher(args[0] if args else "TODO", args[1] if len(args) > 1 else "."),
        "git": lambda: git_ops(args[0] if args else "."),
        "system": lambda: system_check(),
        "pipeline": lambda: pipeline_agent(*args),
        "explorer": lambda: explorer(int(args[0]) if args else 100),
        "self-builder": lambda: self_builder("--apply" in args),
    }

    if agent not in agents:
        print(f"Unknown agent: {agent}. Available: {list(agents.keys())}")
        sys.exit(1)

    agents[agent]()
