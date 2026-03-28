#!/usr/bin/env python3
"""
Aussie Agents Bridge — Python-side JSON-over-stdin/stdout bridge.

This is the entry point that the Node.js CLI spawns as a subprocess.
It receives JSON commands on stdin and returns JSON responses on stdout.

The bridge exposes the full Aussie Agents engine:
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

# Add parent directory to path for Aussie Agents engine imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def handle_command(cmd: dict) -> dict:
    """Route a bridge command to the appropriate Aussie Agents engine function."""
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

        elif action == "deferred_tool_search":
            from agent_setup_cli.core.tools import ToolRegistry
            import agent_setup_cli.core.tools_extended  # noqa: F401
            try:
                import agent_setup_cli.core.tools_generated  # noqa: F401
            except ImportError:
                pass

            registry = ToolRegistry.get()
            query = args.get("query", "").lower()
            limit = args.get("limit", 5)

            all_tools = registry.list_tools()
            scored = []
            for t in all_tools:
                name_lower = t.name.lower()
                desc_lower = (t.description or "").lower()
                # Score: exact name match > name contains > description contains
                if query == name_lower:
                    score = 100
                elif query in name_lower:
                    score = 50
                elif query in desc_lower:
                    score = 10
                else:
                    # Check individual query words
                    words = query.split()
                    score = sum(
                        3 if w in name_lower else 1 if w in desc_lower else 0
                        for w in words
                    )
                if score > 0:
                    scored.append((score, t))

            scored.sort(key=lambda x: x[0], reverse=True)
            matches = [
                {
                    "name": t.name,
                    "description": t.description,
                    "phase": t.phase.name,
                    "capabilities": list(t.capabilities),
                }
                for _, t in scored[:limit]
            ]
            return _ok(cmd_id, matches, start_ns)

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

        elif action == "save_session":
            # Save current session state
            import os, json, time
            session_dir = os.path.expanduser("~/.pfaa/sessions")
            os.makedirs(session_dir, exist_ok=True)
            session_id = args.get("session_id", f"session_{int(time.time())}")
            state = args.get("state", {})
            state["timestamp"] = time.time()
            path = os.path.join(session_dir, f"{session_id}.json")
            with open(path, "w") as f:
                json.dump(state, f, indent=2, default=str)
            return _ok(cmd_id, {"saved": path}, start_ns)

        elif action == "load_session":
            import os, json, glob
            session_dir = os.path.expanduser("~/.pfaa/sessions")
            session_id = args.get("session_id")
            if session_id:
                path = os.path.join(session_dir, f"{session_id}.json")
                if os.path.exists(path):
                    with open(path) as f:
                        return _ok(cmd_id, json.load(f), start_ns)
                return _err(cmd_id, f"Session not found: {session_id}", start_ns)
            # List all sessions
            sessions = []
            for f in sorted(glob.glob(os.path.join(session_dir, "*.json")), reverse=True)[:20]:
                with open(f) as fh:
                    data = json.load(fh)
                    sessions.append({"id": os.path.basename(f).replace(".json",""), "timestamp": data.get("timestamp"), "goals": data.get("goals_count", 0)})
            return _ok(cmd_id, {"sessions": sessions}, start_ns)

        elif action == "extract_instincts":
            import subprocess as sp
            script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python", "swarm", "instinct_learner.py")
            proc = sp.run([sys.executable, script], capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                return _ok(cmd_id, json.loads(proc.stdout), start_ns)
            return _err(cmd_id, proc.stderr or "instinct extraction failed", start_ns)

        elif action == "clean_memory":
            import subprocess as sp
            script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python", "swarm", "memory_cleaner.py")
            proc = sp.run([sys.executable, script], capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                return _ok(cmd_id, json.loads(proc.stdout), start_ns)
            return _err(cmd_id, proc.stderr or "memory cleanup failed", start_ns)

        elif action == "evolve_skills":
            import subprocess as sp
            script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python", "swarm", "skill_evolver.py")
            proc = sp.run([sys.executable, script], capture_output=True, text=True, timeout=30,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if proc.returncode == 0:
                return _ok(cmd_id, json.loads(proc.stdout), start_ns)
            return _err(cmd_id, proc.stderr or "skill evolution failed", start_ns)

        elif action == "auto_learn":
            # Run all three in sequence
            results = {}
            import subprocess as sp
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for name, script_name in [("instincts", "instinct_learner.py"), ("cleanup", "memory_cleaner.py"), ("evolution", "skill_evolver.py")]:
                script = os.path.join(base, "python", "swarm", script_name)
                try:
                    proc = sp.run([sys.executable, script], capture_output=True, text=True, timeout=30, cwd=base)
                    results[name] = json.loads(proc.stdout) if proc.returncode == 0 else {"error": proc.stderr}
                except Exception as e:
                    results[name] = {"error": str(e)}
            return _ok(cmd_id, results, start_ns)

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
    sys.stdout.write(json.dumps({"id": "ready", "success": True, "data": "Aussie Agents bridge ready"}) + "\n")
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
