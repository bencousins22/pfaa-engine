#!/usr/bin/env python3
"""
Aussie Agents Comprehensive Benchmark Suite — Industry-Standard Agent Tests

Covers the major categories from popular 2026 agent benchmarks:

    A. FUNCTION CALLING (inspired by BFCL)
       - Tool dispatch accuracy, parameter parsing, error handling
    B. MULTI-STEP REASONING (inspired by AgentBench/MINT)
       - Multi-turn tool chains, conditional branching, DAG execution
    C. FAULT RECOVERY (inspired by TAU2-Bench reliability)
       - Restart policies, graceful degradation, partial failures
    D. TASK DECOMPOSITION (inspired by GAIA multi-step)
       - Natural language → subtask DAGs, parallel execution
    E. MEMORY & PERSISTENCE (inspired by HAL consistency)
       - Cross-session learning, pattern stability, checkpoint resume
    F. CONCURRENCY & SCALE (inspired by AutoAgents benchmarks)
       - Spawn rate, fan-out/fan-in, swarm throughput
    G. SELF-IMPROVEMENT (unique to PFAA)
       - Introspection, code generation, sandbox testing
    H. PHASE-FLUID EXECUTION (unique to PFAA)
       - Phase transitions, exploration, strategy emergence

Created by Jamie (@bencousins22) · March 2026
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time

lazy import json
lazy import random
lazy import hashlib

from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

from agent_setup_cli.core.framework import Framework
from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.agent import FluidAgent, AgentConfig
from agent_setup_cli.core.nucleus import Nucleus
from agent_setup_cli.core.tools import ToolRegistry
from agent_setup_cli.core.persistence import PersistentMemory
from agent_setup_cli.core.delegation import Supervisor, WorkerSpec, RestartPolicy
from agent_setup_cli.core.streaming import EventBus, EventType

import agent_setup_cli.core.tools_extended
try:
    import agent_setup_cli.core.tools_generated
except ImportError:
    pass


@dataclass
class TestResult:
    name: str
    category: str
    passed: bool
    elapsed_ms: float
    details: str = ""


results: list[TestResult] = []


def record(name: str, cat: str, passed: bool, elapsed_ms: float, details: str = ""):
    r = TestResult(name, cat, passed, elapsed_ms, details)
    results.append(r)
    icon = "✓" if passed else "✗"
    print(f"  {icon} {name:45s} {elapsed_ms:8.1f}ms  {details}")
    return r


# ═══════════════════════════════════════════════════════════════════
# A. FUNCTION CALLING (BFCL-inspired)
# ═══════════════════════════════════════════════════════════════════

async def test_A_function_calling():
    print("\n  ═══ A. FUNCTION CALLING (BFCL-inspired) ═══")
    fw = Framework()

    # A1: Simple function dispatch
    t = time.perf_counter_ns()
    r = await fw.tool("compute", "sqrt(144)")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A1: Simple dispatch (compute)", "A", r.get("result") == 12.0, ms, f"result={r.get('result')}")

    # A2: String parameter handling
    t = time.perf_counter_ns()
    r = await fw.tool("hash_data", "hello world", "sha256")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A2: String params (hash)", "A", r.get("success") and len(r.get("digest", "")) == 64, ms)

    # A3: File system tool
    t = time.perf_counter_ns()
    r = await fw.tool("read_file", "/dev/null")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A3: File read (/dev/null)", "A", r.get("success"), ms)

    # A4: Pattern search tool
    t = time.perf_counter_ns()
    r = await fw.tool("glob_search", "*.py", ".")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A4: Glob search (*.py)", "A", r.get("success") and r.get("count", 0) > 0, ms, f"found={r.get('count')}")

    # A5: Subprocess tool (isolated)
    t = time.perf_counter_ns()
    r = await fw.tool("shell", "echo PFAA_TEST")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A5: Shell execution", "A", r.get("success") and "PFAA_TEST" in r.get("stdout", ""), ms)

    # A6: JSON parsing tool
    t = time.perf_counter_ns()
    r = await fw.tool("json_parse", '{"a":1,"b":{"c":2}}', "b.c")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A6: JSON parse + query", "A", r.get("result") == 2, ms)

    # A7: Regex extraction
    t = time.perf_counter_ns()
    r = await fw.tool("regex_extract", "v3.15.0a7 released 2026-03-10", r"\d+\.\d+\.\d+\w*")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A7: Regex extract (version)", "A", "3.15.0a7" in r.get("matches", []), ms)

    # A8: DNS lookup
    t = time.perf_counter_ns()
    r = await fw.tool("dns_lookup", "localhost")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A8: DNS lookup (localhost)", "A", r.get("success") and len(r.get("ips", [])) > 0, ms)

    # A9: Env variable read
    t = time.perf_counter_ns()
    r = await fw.tool("env_get", "HOME")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A9: Env var read (HOME)", "A", r.get("exists") and r.get("value", "").startswith("/"), ms)

    # A10: Git status (subprocess isolation)
    t = time.perf_counter_ns()
    r = await fw.tool("git_status")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("A10: Git status (SOLID phase)", "A", r.get("success"), ms)

    await fw.shutdown()


# ═══════════════════════════════════════════════════════════════════
# B. MULTI-STEP REASONING (AgentBench-inspired)
# ═══════════════════════════════════════════════════════════════════

async def test_B_multi_step():
    print("\n  ═══ B. MULTI-STEP REASONING (AgentBench-inspired) ═══")
    fw = Framework()

    # B1: Sequential pipeline (fetch → process → verify)
    t = time.perf_counter_ns()
    r = await fw.pipeline([
        ("read", "read_file", ("/dev/null",)),
        ("hash", "hash_data", ("pipeline-test",)),
        ("compute", "compute", ("sqrt(42)",)),
    ])
    ms = (time.perf_counter_ns() - t) / 1e6
    record("B1: 3-stage pipeline", "B", r["completed"] == 3, ms, f"{r['completed']}/3")

    # B2: Parallel fan-out (4 tools simultaneously)
    t = time.perf_counter_ns()
    r = await fw.tools([
        ("compute", ("pi * e",)),
        ("hash_data", ("test1",)),
        ("hash_data", ("test2",)),
        ("system_info", ()),
    ])
    ms = (time.perf_counter_ns() - t) / 1e6
    all_ok = all(isinstance(x, dict) and x.get("success", True) for x in r)
    record("B2: 4-way parallel fan-out", "B", all_ok and len(r) == 4, ms)

    # B3: Goal decomposition + execution
    t = time.perf_counter_ns()
    state = await fw.run("compute sqrt(42) and hash test data and check system info")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("B3: NL goal → DAG execution", "B", state.status.name == "COMPLETED", ms, f"{len(state.subtasks)} subtasks")

    # B4: Large fan-out (20 tasks)
    t = time.perf_counter_ns()
    calls = [("compute", (f"sqrt({i})",)) for i in range(20)]
    r = await fw.tools(calls)
    ms = (time.perf_counter_ns() - t) / 1e6
    record("B4: 20-way parallel compute", "B", len(r) == 20, ms)

    # B5: Mixed-phase execution
    t = time.perf_counter_ns()
    state = await fw.run("check disk usage and git status and count lines and compute pi")
    ms = (time.perf_counter_ns() - t) / 1e6
    phases_used = set()
    for st in state.subtasks:
        if st.tool_name:
            entry = fw._registry.get_tool(st.tool_name)
            if entry:
                phases_used.add(entry[0].phase.name)
    record("B5: Mixed-phase goal (V+L+S)", "B", len(phases_used) >= 2, ms, f"phases={phases_used}")

    await fw.shutdown()


# ═══════════════════════════════════════════════════════════════════
# C. FAULT RECOVERY (TAU2-Bench-inspired)
# ═══════════════════════════════════════════════════════════════════

async def test_C_fault_recovery():
    print("\n  ═══ C. FAULT RECOVERY (TAU2-Bench-inspired) ═══")
    nucleus = Nucleus()

    # C1: Retry on transient failure
    call_count = 0
    def transient_fail(n):
        nonlocal call_count; call_count += 1
        if call_count <= 2: raise RuntimeError("transient")
        return {"ok": True, "attempts": call_count}

    t = time.perf_counter_ns()
    sup = Supervisor("c1", nucleus)
    sup.add_worker(WorkerSpec("w", transient_fail, args=(1,), phase=Phase.LIQUID, restart_policy=RestartPolicy.ON_ERROR, max_restarts=3))
    r = await sup.run_all()
    ms = (time.perf_counter_ns() - t) / 1e6
    record("C1: Retry on transient failure", "C", r["completed"] == 1 and r["restarts"] == 2, ms, f"restarts={r['restarts']}")

    # C2: Graceful degradation
    def always_fail(n): raise RuntimeError("permanent")
    def always_ok(n): return {"ok": True}

    t = time.perf_counter_ns()
    sup2 = Supervisor("c2", nucleus)
    sup2.add_worker(WorkerSpec("fail", always_fail, args=(1,), phase=Phase.LIQUID, restart_policy=RestartPolicy.NEVER))
    sup2.add_worker(WorkerSpec("ok1", always_ok, args=(2,), phase=Phase.LIQUID))
    sup2.add_worker(WorkerSpec("ok2", always_ok, args=(3,), phase=Phase.LIQUID))
    r = await sup2.run_all()
    ms = (time.perf_counter_ns() - t) / 1e6
    record("C2: Graceful degradation (1/3 fail)", "C", r["completed"] == 2 and r["failed"] == 1, ms)

    # C3: Max restarts respected
    call_count = 0
    def always_crash(n):
        nonlocal call_count; call_count += 1
        raise RuntimeError(f"crash #{call_count}")

    t = time.perf_counter_ns()
    sup3 = Supervisor("c3", nucleus)
    sup3.add_worker(WorkerSpec("crash", always_crash, args=(1,), phase=Phase.LIQUID, restart_policy=RestartPolicy.ALWAYS, max_restarts=2))
    r = await sup3.run_all()
    ms = (time.perf_counter_ns() - t) / 1e6
    record("C3: Max restarts cap (2)", "C", r["failed"] == 1 and r["restarts"] == 2, ms)

    # C4: Nested supervisor fault isolation
    t = time.perf_counter_ns()
    parent = Supervisor("parent", nucleus)
    parent.add_worker(WorkerSpec("ok", always_ok, args=(1,), phase=Phase.LIQUID))
    child = Supervisor("child", nucleus)
    child.add_worker(WorkerSpec("fail", always_fail, args=(1,), phase=Phase.LIQUID, restart_policy=RestartPolicy.NEVER))
    child.add_worker(WorkerSpec("ok", always_ok, args=(2,), phase=Phase.LIQUID))
    parent.add_child_supervisor(child)
    r = await parent.run_all()
    ms = (time.perf_counter_ns() - t) / 1e6
    parent_ok = r["completed"] == 1
    child_results = r.get("child_results", [{}])
    child_ok = isinstance(child_results[0], dict) and child_results[0].get("completed") == 1
    record("C4: Nested supervisor isolation", "C", parent_ok and child_ok, ms)

    await nucleus.shutdown()


# ═══════════════════════════════════════════════════════════════════
# D. TASK DECOMPOSITION (GAIA-inspired)
# ═══════════════════════════════════════════════════════════════════

async def test_D_decomposition():
    print("\n  ═══ D. TASK DECOMPOSITION (GAIA-inspired) ═══")
    fw = Framework()

    goals = [
        ("D1: Simple 2-task", "count lines and compute sqrt(42)", 2),
        ("D2: 3-tool analysis", "search for TODO and check git and count lines", 3),
        ("D3: System survey", "check system info and disk usage and port check 8000 and dns lookup localhost", 4),
        ("D4: Full codebase review", "analyze code and search for class definitions and count lines and check git status and git log and system info", 5),
        ("D5: Maximum decomposition", "review codebase and find TODO and count lines and compute pi and hash test and check git and system info and disk usage", 6),
    ]

    for name, goal, min_tasks in goals:
        t = time.perf_counter_ns()
        state = await fw.run(goal)
        ms = (time.perf_counter_ns() - t) / 1e6
        ok = len(state.subtasks) >= min_tasks and state.status.name == "COMPLETED"
        record(name, "D", ok, ms, f"{len(state.subtasks)} subtasks, need≥{min_tasks}")

    await fw.shutdown()


# ═══════════════════════════════════════════════════════════════════
# E. MEMORY & PERSISTENCE (HAL-inspired)
# ═══════════════════════════════════════════════════════════════════

async def test_E_memory():
    print("\n  ═══ E. MEMORY & PERSISTENCE (HAL-inspired) ═══")
    registry = ToolRegistry.get()

    with tempfile.TemporaryDirectory() as tmpdir:
        # E1: Episode recording
        t = time.perf_counter_ns()
        mem = PersistentMemory(storage_dir=tmpdir)
        for i in range(50):
            r = await registry.execute("compute", f"sqrt({i})")
            mem.record(r, "compute", (f"sqrt({i})",))
        ms = (time.perf_counter_ns() - t) / 1e6
        record("E1: Record 50 episodes", "E", mem.status()["l1_episodes"] == 50, ms)

        # E2: Pattern extraction
        t = time.perf_counter_ns()
        mem.force_learn()
        ms = (time.perf_counter_ns() - t) / 1e6
        record("E2: L2 pattern extraction", "E", mem.status()["l2_patterns"] > 0, ms, f"patterns={mem.status()['l2_patterns']}")

        # E3: Phase recommendation
        t = time.perf_counter_ns()
        rec = mem.recommend_phase("compute")
        ms = (time.perf_counter_ns() - t) / 1e6
        record("E3: Phase recommendation", "E", rec is not None, ms, f"recommended={rec.name if rec else 'none'}")

        # E4: Disk persistence
        t = time.perf_counter_ns()
        mem.close()
        mem2 = PersistentMemory(storage_dir=tmpdir)
        ms = (time.perf_counter_ns() - t) / 1e6
        record("E4: Cross-session persistence", "E", mem2.status()["l1_episodes"] == 50, ms, f"loaded={mem2.status()['l1_episodes']}")

        # E5: Pattern survives restart
        t = time.perf_counter_ns()
        rec2 = mem2.recommend_phase("compute")
        ms = (time.perf_counter_ns() - t) / 1e6
        record("E5: Recommendation persists", "E", rec2 is not None, ms)
        mem2.close()


# ═══════════════════════════════════════════════════════════════════
# F. CONCURRENCY & SCALE (AutoAgents-inspired)
# ═══════════════════════════════════════════════════════════════════

async def test_F_concurrency():
    print("\n  ═══ F. CONCURRENCY & SCALE (AutoAgents-inspired) ═══")

    # F1: Spawn 1000 agents
    config = AgentConfig("bench")
    t = time.perf_counter_ns()
    agents = [FluidAgent(config) for _ in range(1000)]
    ms = (time.perf_counter_ns() - t) / 1e6
    per_us = ms * 1000 / 1000
    record("F1: Spawn 1,000 agents", "F", ms < 50, ms, f"{per_us:.1f}μs/agent")

    # F2: Spawn 10,000 agents
    t = time.perf_counter_ns()
    agents = [FluidAgent(config) for _ in range(10000)]
    ms = (time.perf_counter_ns() - t) / 1e6
    record("F2: Spawn 10,000 agents", "F", ms < 500, ms, f"{ms*1000/10000:.1f}μs/agent")

    # F3: Scatter/gather 100 tasks
    nucleus = Nucleus()
    async def task(n): await asyncio.sleep(0.0001); return {"n": n}
    t = time.perf_counter_ns()
    r = await nucleus.scatter(config, task, [(i,) for i in range(100)], hint=Phase.VAPOR)
    ms = (time.perf_counter_ns() - t) / 1e6
    record("F3: Scatter/gather 100 tasks", "F", len(r) == 100, ms)

    # F4: Scatter/gather 500 tasks
    t = time.perf_counter_ns()
    r = await nucleus.scatter(config, task, [(i,) for i in range(500)], hint=Phase.VAPOR)
    ms = (time.perf_counter_ns() - t) / 1e6
    throughput = len(r) / (ms / 1000)
    record("F4: Scatter/gather 500 tasks", "F", len(r) == 500, ms, f"{throughput:.0f}/sec")

    # F5: Swarm pool throughput
    task_q: asyncio.Queue = asyncio.Queue()
    result_q: asyncio.Queue = asyncio.Queue()
    for i in range(300):
        await task_q.put((task, (i,)))
    for _ in range(8):
        await task_q.put(None)
    t = time.perf_counter_ns()
    await nucleus.swarm(config, 8, task_q, result_q)
    ms = (time.perf_counter_ns() - t) / 1e6
    count = result_q.qsize()
    throughput = count / (ms / 1000)
    record("F5: Swarm pool 300 tasks / 8 workers", "F", count == 300, ms, f"{throughput:.0f}/sec")

    await nucleus.shutdown()


# ═══════════════════════════════════════════════════════════════════
# G. SELF-IMPROVEMENT (PFAA-unique)
# ═══════════════════════════════════════════════════════════════════

async def test_G_self_improvement():
    print("\n  ═══ G. SELF-IMPROVEMENT (PFAA-unique) ═══")
    from agent_setup_cli.core.self_build import SelfBuilder, SELF_ROOT

    builder = SelfBuilder()

    # G1: Introspection
    t = time.perf_counter_ns()
    analysis = await builder.introspect()
    ms = (time.perf_counter_ns() - t) / 1e6
    record("G1: Self-introspection", "G", analysis.total_lines > 5000, ms, f"{analysis.total_lines} lines")

    # G2: Static diagnosis
    t = time.perf_counter_ns()
    improvements = await builder._static_diagnose()
    ms = (time.perf_counter_ns() - t) / 1e6
    record("G2: Self-diagnosis", "G", len(improvements) > 0, ms, f"{len(improvements)} findings")

    # G3: Sandbox code testing
    t = time.perf_counter_ns()
    test_code = "def test_fn(): return {'ok': True}\nresult = test_fn()\nassert result['ok']"
    r = await builder.test_code(test_code)
    ms = (time.perf_counter_ns() - t) / 1e6
    record("G3: Sandbox code execution", "G", r.get("success"), ms)

    await builder.shutdown()


# ═══════════════════════════════════════════════════════════════════
# H. PHASE-FLUID EXECUTION (PFAA-unique)
# ═══════════════════════════════════════════════════════════════════

async def test_H_phase_fluid():
    print("\n  ═══ H. PHASE-FLUID EXECUTION (PFAA-unique) ═══")

    # H1: Full phase transition cycle (VAPOR → LIQUID → VAPOR)
    # Note: skip SOLID for lambdas (can't pickle), test real tools instead
    config = AgentConfig("phase-test", auto_transition=False)
    agent = FluidAgent(config)
    t = time.perf_counter_ns()

    import math
    r1 = await agent.execute(lambda n: {"r": math.sqrt(n)}, 42, hint=Phase.LIQUID)
    async def io_task(n):
        await asyncio.sleep(0.001)
        return {"n": n}
    r2 = await agent.execute(io_task, 1, hint=Phase.VAPOR)
    ms = (time.perf_counter_ns() - t) / 1e6
    transitions = len(agent._transition_log)
    record("H1: V→L→V transition cycle", "H", transitions >= 1, ms, f"{transitions} transitions")

    # H2: Phase-aware tool dispatch
    registry = ToolRegistry.get()
    t = time.perf_counter_ns()
    tools = registry.list_tools()
    vapor = [t for t in tools if t.phase == Phase.VAPOR]
    liquid = [t for t in tools if t.phase == Phase.LIQUID]
    solid = [t for t in tools if t.phase == Phase.SOLID]
    ms = (time.perf_counter_ns() - t) / 1e6
    record("H2: 3-phase tool distribution", "H", len(vapor) > 0 and len(liquid) > 0 and len(solid) > 0, ms, f"V={len(vapor)} L={len(liquid)} S={len(solid)}")

    # H3: Event streaming
    bus = EventBus.get()
    events = []
    bus.subscribe(EventType.TASK_COMPLETED, lambda e: events.append(e))
    fw = Framework()
    t = time.perf_counter_ns()
    await fw.tool("compute", "42")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("H3: Event streaming works", "H", len(events) > 0, ms, f"{len(events)} events")
    await fw.shutdown()


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  AUSSIE AGENTS BENCHMARK — Industry-Standard Agent Tests        ║")
    print("║  Created by Jamie (@bencousins22) · Python 3.15 · macOS        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    total_start = time.perf_counter_ns()

    await test_A_function_calling()
    await test_B_multi_step()
    await test_C_fault_recovery()
    await test_D_decomposition()
    await test_E_memory()
    await test_F_concurrency()
    await test_G_self_improvement()
    await test_H_phase_fluid()

    total_ms = (time.perf_counter_ns() - total_start) / 1e6

    # Summary
    print(f"\n{'═' * 68}")
    by_cat = {}
    for r in results:
        if r.category not in by_cat:
            by_cat[r.category] = {"passed": 0, "total": 0}
        by_cat[r.category]["total"] += 1
        if r.passed:
            by_cat[r.category]["passed"] += 1

    cat_names = {
        "A": "Function Calling (BFCL)",
        "B": "Multi-Step Reasoning (AgentBench)",
        "C": "Fault Recovery (TAU2-Bench)",
        "D": "Task Decomposition (GAIA)",
        "E": "Memory & Persistence (HAL)",
        "F": "Concurrency & Scale (AutoAgents)",
        "G": "Self-Improvement (PFAA-unique)",
        "H": "Phase-Fluid Execution (PFAA-unique)",
    }

    total_passed = sum(1 for r in results if r.passed)
    total_tests = len(results)

    print(f"\n  {'CATEGORY':<45} {'RESULT':>10}")
    print(f"  {'─' * 56}")
    for cat, data in sorted(by_cat.items()):
        name = cat_names.get(cat, cat)
        p, t = data["passed"], data["total"]
        bar = "█" * (p * 10 // t) + "░" * (10 - p * 10 // t)
        print(f"  {cat}. {name:<42} {p:>2}/{t:<2} {bar}")

    print(f"  {'─' * 56}")
    pct = total_passed * 100 // total_tests
    print(f"  {'TOTAL':<45} {total_passed:>2}/{total_tests}  {pct}%")
    print(f"\n  Completed in {total_ms:.0f}ms")

    # JSON
    print(f"\n{'═' * 68}")
    print(json.dumps({
        "benchmark": "Aussie Agents Comprehensive Benchmark v1.0",
        "date": "2026-03-23",
        "author": "Jamie (@bencousins22)",
        "python": "3.15.0a7",
        "total_passed": total_passed,
        "total_tests": total_tests,
        "percentage": pct,
        "elapsed_ms": round(total_ms),
        "categories": {
            cat: {
                "name": cat_names.get(cat, cat),
                "passed": data["passed"],
                "total": data["total"],
            }
            for cat, data in sorted(by_cat.items())
        },
        "tests": [
            {"name": r.name, "category": r.category, "passed": r.passed,
             "elapsed_ms": round(r.elapsed_ms, 1), "details": r.details}
            for r in results
        ],
    }, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
