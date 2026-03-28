#!/usr/bin/env python3
"""
PFAA Bridge — Python-side JSON-over-stdin/stdout bridge.

This is the entry point that the Node.js CLI spawns as a subprocess.
It receives JSON commands on stdin and returns JSON responses on stdout.

The bridge exposes the full PFAA engine:
- Tool execution (27+ tools, phase-aware)
- Goal decomposition and autonomous execution
- Memory operations (5-layer meta-learning)
- Claude Code integration
- Self-build cycles
- Benchmarks

Protocol:
  → {"action": "execute_tool", "args": {"name": "compute", "args": ["sqrt(42)"]}, "id": "cmd_1"}
  ← {"id": "cmd_1", "success": true, "data": {...}, "elapsed_us": 42, "phase": "VAPOR"}

Python 3.15: lazy import, frozendict, kqueue subprocess.
"""

from __future__ import annotations

import asyncio
import sys
import os
import time

lazy import json
lazy import traceback

# Add parent directory to path for PFAA engine imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def handle_command(cmd: dict) -> dict:
    """Route a bridge command to the appropriate PFAA engine function."""
    action = cmd.get("action", "")
    args = cmd.get("args", {})
    cmd_id = cmd.get("id", "unknown")
    start_ns = time.perf_counter_ns()

    try:
        if action == "status":
            from agent_setup_cli.core.framework import Framework
            fw = Framework()
            data = fw.status()
            return _ok(cmd_id, data, start_ns)

        elif action == "list_tools":
            from agent_setup_cli.core.tools import ToolRegistry
            import agent_setup_cli.core.tools_extended  # noqa: F401
            try:
                import agent_setup_cli.core.tools_generated  # noqa: F401
            except ImportError:
                pass

            registry = ToolRegistry.get()
            tools = [
                {
                    "name": t.name,
                    "phase": t.phase.name,
                    "description": t.description,
                    "capabilities": list(t.capabilities),
                    "isolated": t.isolated,
                }
                for t in registry.list_tools()
            ]
            return _ok(cmd_id, tools, start_ns)

        elif action == "execute_tool":
            from agent_setup_cli.core.tools import ToolRegistry
            from agent_setup_cli.core.persistence import PersistentMemory
            import agent_setup_cli.core.tools_extended  # noqa: F401

            registry = ToolRegistry.get()
            mem = PersistentMemory()

            tool_name = args.get("name", "")
            tool_args = tuple(args.get("args", []))

            result = await registry.execute(tool_name, *tool_args)
            mem.record(result, tool_name, tool_args)
            mem.close()

            return _ok(
                cmd_id,
                result.result,
                start_ns,
                phase=result.phase_used.name,
                elapsed_us=result.elapsed_us,
            )

        elif action == "run_goal":
            from agent_setup_cli.core.framework import Framework
            fw = Framework()
            goal = args.get("goal", "")
            state = await fw.run(goal)
            data = {
                "goal_id": state.goal_id,
                "status": state.status.value,
                "subtasks": [
                    {
                        "description": st.description,
                        "status": st.status,
                        "tool": st.tool,
                    }
                    for st in state.subtasks
                ],
                "completed": sum(1 for st in state.subtasks if st.status == "completed"),
                "failed": sum(1 for st in state.subtasks if st.status == "failed"),
            }
            await fw.shutdown()
            return _ok(cmd_id, data, start_ns)

        elif action == "scatter":
            from agent_setup_cli.core.tools import ToolRegistry
            import agent_setup_cli.core.tools_extended  # noqa: F401

            registry = ToolRegistry.get()
            tool_name = args.get("tool", "")
            inputs = args.get("inputs", [])

            results = await registry.execute_many([
                (tool_name, (inp,), {}) for inp in inputs
            ])

            data = []
            for inp, result in zip(inputs, results):
                if isinstance(result, Exception):
                    data.append({"input": inp, "success": False, "error": str(result)})
                else:
                    data.append({
                        "input": inp,
                        "success": True,
                        "result": result.result,
                        "phase": result.phase_used.name,
                        "elapsed_us": result.elapsed_us,
                    })

            return _ok(cmd_id, data, start_ns)

        elif action == "memory_status":
            from agent_setup_cli.core.persistence import PersistentMemory
            mem = PersistentMemory()
            status = mem.status()
            mem.close()
            return _ok(cmd_id, {
                "l1Episodes": status["l1_episodes"],
                "l2Patterns": status["l2_patterns"],
                "l3Strategies": status["l3_strategies"],
                "l4LearningRate": status["l4_learning_rate"],
                "l5Knowledge": status["l5_knowledge"],
                "dbSizeKb": status["db_size_kb"],
            }, start_ns)

        elif action == "force_learn":
            from agent_setup_cli.core.persistence import PersistentMemory
            mem = PersistentMemory()
            mem.force_learn()
            mem.close()
            return _ok(cmd_id, {"learned": True}, start_ns)

        elif action == "ask_claude":
            from agent_setup_cli.core.claude_bridge import ClaudeBridge, ClaudeConfig
            bridge = ClaudeBridge(config=ClaudeConfig(
                model=args.get("model", "sonnet"),
            ))
            result = await bridge.ask(args.get("prompt", ""))
            return _ok(cmd_id, {
                "success": result.success,
                "output": result.output,
                "elapsedMs": result.elapsed_ms,
            }, start_ns)

        elif action == "generate_code":
            from agent_setup_cli.core.claude_bridge import ClaudeBridge, ClaudeConfig
            bridge = ClaudeBridge(config=ClaudeConfig())
            result = await bridge.generate_code(
                description=args.get("description", ""),
                language=args.get("language", "python"),
                output_file=args.get("output_file"),
            )
            return _ok(cmd_id, {
                "success": result.success,
                "code": result.output,
                "file": args.get("output_file"),
            }, start_ns)

        elif action == "list_checkpoints":
            from agent_setup_cli.core.autonomous import AutonomousAgent
            agent = AutonomousAgent()
            checkpoints = agent.checkpoints()
            return _ok(cmd_id, checkpoints, start_ns)

        elif action == "resume_goal":
            from agent_setup_cli.core.autonomous import AutonomousAgent
            agent = AutonomousAgent()
            goal_id = args.get("goal_id", "")
            state = await agent.resume(goal_id)
            return _ok(cmd_id, {
                "goal_id": state.goal_id,
                "status": state.status.value,
                "completed": sum(1 for st in state.subtasks if st.status == "completed"),
            }, start_ns)

        elif action == "get_memory":
            from agent_setup_cli.core.persistence import PersistentMemory
            mem = PersistentMemory()
            dump = mem.dump()
            mem.close()
            return _ok(cmd_id, dump, start_ns)

        elif action == "pipeline":
            from agent_setup_cli.core.tools import ToolRegistry
            import agent_setup_cli.core.tools_extended  # noqa: F401

            registry = ToolRegistry.get()
            steps = args.get("steps", [])
            results = []
            for step in steps:
                tool_name = step.get("tool", "")
                tool_args = tuple(step.get("args", []))
                try:
                    result = await registry.execute(tool_name, *tool_args)
                    results.append({
                        "tool": tool_name,
                        "success": True,
                        "result": result.result,
                        "phase": result.phase_used.name,
                        "elapsed_us": result.elapsed_us,
                    })
                except Exception as e:
                    results.append({
                        "tool": tool_name,
                        "success": False,
                        "result": str(e),
                        "phase": "ERROR",
                        "elapsed_us": 0,
                    })
            return _ok(cmd_id, results, start_ns)

        elif action == "explore":
            from agent_setup_cli.core.framework import Framework
            fw = Framework()
            rounds = args.get("rounds", 200)
            epsilon = args.get("epsilon", 0.3)
            # Run exploration
            results = {}
            for i in range(rounds):
                for tool_name in ["compute", "hash_data", "json_parse", "regex_extract", "line_count"]:
                    try:
                        result = await fw.tool(tool_name, "test")
                        results.setdefault(tool_name, []).append({
                            "phase": result.phase_used.name,
                            "elapsed_us": result.elapsed_us,
                        })
                    except Exception:
                        pass
            # Summarize
            summary = {}
            for tool_name, runs in results.items():
                by_phase = {}
                for r in runs:
                    by_phase.setdefault(r["phase"], []).append(r["elapsed_us"])
                summary[tool_name] = {
                    phase: {"avg_us": sum(times) // len(times), "count": len(times)}
                    for phase, times in by_phase.items()
                }
            await fw.shutdown()
            return _ok(cmd_id, {"rounds": rounds, "epsilon": epsilon, "tools": summary}, start_ns)

        elif action == "spawn_team":
            import subprocess as sp
            goal = args.get("goal", "")
            mode = args.get("mode", "basic")
            script = "agents/team/remix_spawn.py" if mode == "remix" else "agents/team/spawn.py"
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), script)

            if not os.path.exists(script_path):
                return _err(cmd_id, f"Team script not found: {script_path}", start_ns)

            proc = sp.run(
                [sys.executable, script_path, goal],
                capture_output=True, text=True, timeout=600,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            )
            return _ok(cmd_id, {
                "mode": mode,
                "goal": goal,
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-2000:] if proc.stdout else "",
                "stderr": proc.stderr[-1000:] if proc.stderr else "",
            }, start_ns)

        elif action == "self_build":
            from agent_setup_cli.core.self_build import SelfBuilder
            builder = SelfBuilder()
            try:
                result = await builder.build_self(
                    auto_apply=args.get("auto_apply", False),
                )
                return _ok(cmd_id, {
                    k: v for k, v in result.items() if k != "proposals"
                }, start_ns)
            finally:
                await builder.shutdown()

        elif action == "benchmark":
            from agent_setup_cli.core.benchmark import main as bench_main
            # Capture benchmark output
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                await bench_main()
                output = sys.stdout.getvalue()
            finally:
                sys.stdout = old_stdout
            return _ok(cmd_id, {"output": output}, start_ns)

        else:
            return _err(cmd_id, f"Unknown action: {action}", start_ns)

    except Exception as e:
        return _err(cmd_id, f"{type(e).__name__}: {e}", start_ns)


def _ok(cmd_id: str, data: any, start_ns: int, **extra) -> dict:
    elapsed_us = (time.perf_counter_ns() - start_ns) // 1000
    return {"id": cmd_id, "success": True, "data": data, "elapsed_us": elapsed_us, **extra}


def _err(cmd_id: str, error: str, start_ns: int) -> dict:
    elapsed_us = (time.perf_counter_ns() - start_ns) // 1000
    return {"id": cmd_id, "success": False, "data": None, "error": error, "elapsed_us": elapsed_us}


async def main():
    """Main bridge loop — read JSON commands from stdin, write responses to stdout."""
    # Signal ready
    sys.stdout.write(json.dumps({"id": "ready", "success": True, "data": "PFAA bridge ready"}) + "\n")
    sys.stdout.flush()

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            line = await reader.readline()
            if not line:
                break  # EOF

            line_str = line.decode("utf-8").strip()
            if not line_str:
                continue

            cmd = json.loads(line_str)
            response = await handle_command(cmd)

            sys.stdout.write(json.dumps(response, default=str) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            sys.stderr.write(f"Invalid JSON: {e}\n")
            sys.stderr.flush()
        except Exception as e:
            sys.stderr.write(f"Bridge error: {e}\n")
            sys.stderr.flush()
            sys.stdout.write(json.dumps({
                "id": "error",
                "success": False,
                "error": str(e),
            }) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    asyncio.run(main())
