#!/usr/bin/env python3
"""
PFAA Stress & Edge Case Benchmark — Push the limits.

    I.  STRESS TESTS — Break things at scale
    J.  LATENCY PROFILING — Sub-millisecond measurements
    K.  REAL WORKLOADS — Actual useful tasks, not synthetics
    L.  EDGE CASES — Weird inputs, boundary conditions
    M.  EXPLORATION & LEARNING — L3 strategy emergence
    N.  CHECKPOINT & RESUME — Interrupt/resume mid-goal

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
from agent_setup_cli.core.autonomous import AutonomousAgent

import agent_setup_cli.core.tools_extended
try:
    import agent_setup_cli.core.tools_generated
except ImportError:
    pass

results: list[dict] = []

def record(name, cat, passed, ms, details=""):
    r = {"name": name, "category": cat, "passed": passed, "ms": round(ms, 1), "details": details}
    results.append(r)
    icon = "✓" if passed else "✗"
    print(f"  {icon} {name:50s} {ms:9.1f}ms  {details}")


# ═══════════════════════════════════════════════════════════════════
# I. STRESS TESTS
# ═══════════════════════════════════════════════════════════════════

async def test_I_stress():
    print("\n  ═══ I. STRESS TESTS — Scale limits ═══")
    config = AgentConfig("stress")

    # I1: 50,000 agent spawn
    t = time.perf_counter_ns()
    agents = [FluidAgent(config) for _ in range(50000)]
    ms = (time.perf_counter_ns() - t) / 1e6
    record("I1: Spawn 50,000 agents", "I", ms < 1000, ms, f"{ms*1000/50000:.1f}μs/agent")
    del agents

    # I2: 2,000 scatter/gather
    nucleus = Nucleus()
    async def tiny(n): return {"n": n}
    t = time.perf_counter_ns()
    r = await nucleus.scatter(config, tiny, [(i,) for i in range(2000)], hint=Phase.VAPOR)
    ms = (time.perf_counter_ns() - t) / 1e6
    tps = len(r) / (ms / 1000)
    record("I2: Scatter/gather 2,000 tasks", "I", len(r) == 2000, ms, f"{tps:.0f}/sec")

    # I3: 50 parallel tools at once
    fw = Framework()
    t = time.perf_counter_ns()
    calls = [("compute", (f"sqrt({i})",)) for i in range(50)]
    r = await fw.tools(calls)
    ms = (time.perf_counter_ns() - t) / 1e6
    record("I3: 50 parallel tool calls", "I", len(r) == 50, ms)

    # I4: Rapid fire single tool (100 sequential)
    t = time.perf_counter_ns()
    for i in range(100):
        await fw.tool("compute", f"sqrt({i})")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("I4: 100 sequential tool calls", "I", True, ms, f"{ms/100:.1f}ms/call")

    # I5: Deep pipeline (10 stages)
    t = time.perf_counter_ns()
    stages = [(f"s{i}", "compute", (f"sqrt({i+1})",)) for i in range(10)]
    r = await fw.pipeline(stages)
    ms = (time.perf_counter_ns() - t) / 1e6
    record("I5: 10-stage pipeline", "I", r["completed"] == 10, ms)

    # I6: Large swarm (16 workers, 1000 tasks)
    task_q: asyncio.Queue = asyncio.Queue()
    result_q: asyncio.Queue = asyncio.Queue()
    for i in range(1000):
        await task_q.put((tiny, (i,)))
    for _ in range(16):
        await task_q.put(None)
    t = time.perf_counter_ns()
    await nucleus.swarm(config, 16, task_q, result_q)
    ms = (time.perf_counter_ns() - t) / 1e6
    count = result_q.qsize()
    record("I6: Swarm 16 workers × 1,000 tasks", "I", count == 1000, ms, f"{count/(ms/1000):.0f}/sec")

    await fw.shutdown()
    await nucleus.shutdown()


# ═══════════════════════════════════════════════════════════════════
# J. LATENCY PROFILING
# ═══════════════════════════════════════════════════════════════════

async def test_J_latency():
    print("\n  ═══ J. LATENCY PROFILING — Microsecond precision ═══")
    fw = Framework()
    registry = ToolRegistry.get()

    # J1-J5: Individual tool latency (best of 5)
    tools_to_bench = [
        ("compute", ("sqrt(42)",), "LIQUID"),
        ("hash_data", ("hello",), "LIQUID"),
        ("glob_search", ("*.py", "."), "VAPOR"),
        ("system_info", (), "VAPOR"),
        ("disk_usage", (".",), "VAPOR"),
    ]

    for name, args, phase in tools_to_bench:
        times = []
        for _ in range(5):
            t = time.perf_counter_ns()
            await registry.execute(name, *args)
            times.append((time.perf_counter_ns() - t) / 1000)  # μs
        best = min(times)
        median = sorted(times)[2]
        p99 = max(times)
        record(f"J: {name} latency", "J", True, median/1000,
               f"best={best:.0f}μs med={median:.0f}μs p99={p99:.0f}μs")

    # J6: Event emission latency
    bus = EventBus.get()
    times = []
    for _ in range(100):
        t = time.perf_counter_ns()
        await bus.emit(EventType.LOG, {"test": True})
        times.append((time.perf_counter_ns() - t) / 1000)
    median = sorted(times)[50]
    record("J: Event emission latency (100x)", "J", median < 100, median/1000, f"med={median:.0f}μs")

    # J7: Agent spawn + destroy cycle
    config = AgentConfig("latency-test")
    times = []
    for _ in range(100):
        t = time.perf_counter_ns()
        a = FluidAgent(config)
        a.apoptosis()
        times.append((time.perf_counter_ns() - t) / 1000)
    median = sorted(times)[50]
    record("J: Agent lifecycle (spawn+destroy)", "J", median < 50, median/1000, f"med={median:.0f}μs")

    await fw.shutdown()


# ═══════════════════════════════════════════════════════════════════
# K. REAL WORKLOADS
# ═══════════════════════════════════════════════════════════════════

async def test_K_real_workloads():
    print("\n  ═══ K. REAL WORKLOADS — Actual useful tasks ═══")
    fw = Framework()

    # K1: Codebase analysis
    t = time.perf_counter_ns()
    r = await fw.tool("line_count", ".", ".py")
    ms = (time.perf_counter_ns() - t) / 1e6
    lines = r.get("total_lines", 0)
    record("K1: Count all Python lines", "K", lines > 5000, ms, f"{lines} lines")

    # K2: Pattern search
    t = time.perf_counter_ns()
    r = await fw.tool("codebase_search", "async def", ".", 0, "*.py")
    ms = (time.perf_counter_ns() - t) / 1e6
    matches = r.get("total_matches", 0)
    record("K2: Find all async functions", "K", matches > 30, ms, f"{matches} matches")

    # K3: Git operations pipeline
    t = time.perf_counter_ns()
    r = await fw.tools([
        ("git_status", ()),
        ("git_log", (".", 5)),
        ("git_diff", ()),
        ("git_branch", ()),
    ])
    ms = (time.perf_counter_ns() - t) / 1e6
    record("K3: Full git status (4 ops parallel)", "K", len(r) == 4, ms)

    # K4: System health check
    t = time.perf_counter_ns()
    r = await fw.tools([
        ("system_info", ()),
        ("disk_usage", (".",)),
        ("port_check", ("localhost", 8000)),
        ("process_list", ("python",)),
    ])
    ms = (time.perf_counter_ns() - t) / 1e6
    record("K4: System health check (4 ops)", "K", len(r) == 4, ms)

    # K5: File analysis
    t = time.perf_counter_ns()
    r = await fw.tool("file_stats", ".")
    ms = (time.perf_counter_ns() - t) / 1e6
    files = r.get("total_files", 0)
    record("K5: Directory analysis", "K", files > 0, ms, f"{files} files")

    # K6: Multi-hash parallel
    t = time.perf_counter_ns()
    r = await fw.tools([
        ("hash_data", (f"data-{i}", "sha256")) for i in range(20)
    ])
    ms = (time.perf_counter_ns() - t) / 1e6
    record("K6: 20 parallel SHA-256 hashes", "K", len(r) == 20, ms)

    # K7: Full goal: security audit
    t = time.perf_counter_ns()
    state = await fw.run("search for TODO and find hardcoded secrets and check git status and count lines and analyze code")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("K7: NL security audit goal", "K", state.status.name == "COMPLETED", ms, f"{len(state.subtasks)} subtasks")

    await fw.shutdown()


# ═══════════════════════════════════════════════════════════════════
# L. EDGE CASES
# ═══════════════════════════════════════════════════════════════════

async def test_L_edge_cases():
    print("\n  ═══ L. EDGE CASES — Boundary conditions ═══")
    fw = Framework()

    # L1: Empty input
    t = time.perf_counter_ns()
    r = await fw.tool("compute", "0")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("L1: Compute zero", "L", r.get("result") == 0, ms)

    # L2: Very large expression
    t = time.perf_counter_ns()
    r = await fw.tool("compute", "factorial(20)")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("L2: Large factorial(20)", "L", r.get("result") == 2432902008176640000, ms)

    # L3: Unicode in hash
    t = time.perf_counter_ns()
    r = await fw.tool("hash_data", "こんにちは世界 🌍")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("L3: Unicode hash (Japanese+emoji)", "L", r.get("success") and len(r.get("digest", "")) == 64, ms)

    # L4: Non-existent file
    t = time.perf_counter_ns()
    r = await fw.tool("read_file", "/nonexistent/path/file.txt")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("L4: Read non-existent file", "L", r.get("success") is False, ms, "correctly failed")

    # L5: Regex with special chars
    t = time.perf_counter_ns()
    r = await fw.tool("regex_extract", "price: $42.99 and $100.00", r"\$\d+\.\d+")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("L5: Regex special chars ($)", "L", len(r.get("matches", [])) == 2, ms, f"matches={r.get('matches')}")

    # L6: JSON nested query
    t = time.perf_counter_ns()
    r = await fw.tool("json_parse", '{"a":{"b":{"c":[1,2,3]}}}', "a.b.c")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("L6: Deep JSON query (3 levels)", "L", r.get("result") == [1, 2, 3], ms)

    # L7: Goal with no matching tools
    t = time.perf_counter_ns()
    state = await fw.run("do something completely unknown and mysterious")
    ms = (time.perf_counter_ns() - t) / 1e6
    # Should still produce subtasks (falls back to Claude or generic)
    record("L7: Unknown goal (fallback)", "L", len(state.subtasks) > 0, ms, f"{len(state.subtasks)} subtasks")

    # L8: Empty glob pattern
    t = time.perf_counter_ns()
    r = await fw.tool("glob_search", "*.nonexistent_extension_xyz", ".")
    ms = (time.perf_counter_ns() - t) / 1e6
    record("L8: Glob with no matches", "L", r.get("success") and r.get("count") == 0, ms)

    await fw.shutdown()


# ═══════════════════════════════════════════════════════════════════
# M. EXPLORATION & LEARNING
# ═══════════════════════════════════════════════════════════════════

async def test_M_exploration():
    print("\n  ═══ M. EXPLORATION & LEARNING — L3 emergence ═══")
    registry = ToolRegistry.get()

    with tempfile.TemporaryDirectory() as tmpdir:
        mem = PersistentMemory(storage_dir=tmpdir)
        random.seed(42)

        # M1: Generate cross-phase data via exploration
        t = time.perf_counter_ns()
        sync_tools = [("compute", ("sqrt(42)",)), ("hash_data", ("test",)), ("line_count", (".",))]
        phase_seen: dict[str, set] = {}
        for i in range(120):
            name, args = sync_tools[i % len(sync_tools)]
            r = await registry.execute(name, *args)
            mem.record(r, name, args)
            phase_seen.setdefault(name, set()).add(r.phase_used.name)
        ms = (time.perf_counter_ns() - t) / 1e6

        multi_phase = sum(1 for phases in phase_seen.values() if len(phases) >= 2)
        record("M1: Generate cross-phase data (120 runs)", "M", multi_phase >= 1, ms, f"{multi_phase} tools explored 2+ phases")

        # M2: L2 pattern extraction quality
        t = time.perf_counter_ns()
        mem.force_learn()
        ms = (time.perf_counter_ns() - t) / 1e6
        patterns = mem.memory.l2_semantic._patterns
        record("M2: L2 pattern quality", "M", len(patterns) >= 3, ms, f"{len(patterns)} patterns")

        # M3: L3 strategy emergence
        strategies = mem.memory.l3_strategic._strategies
        record("M3: L3 strategy emergence", "M", len(strategies) >= 1, 0, f"{len(strategies)} strategies")

        # M4: L5 emergent knowledge
        emergent = mem.memory.l5_emergent.all_knowledge
        record("M4: L5 emergent knowledge", "M", len(emergent) >= 1, 0, f"{len(emergent)} discoveries")

        # M5: Recommendation accuracy (should match L2 best_phase)
        correct = 0
        total = 0
        for name, pattern in patterns.items():
            rec = mem.recommend_phase(name)
            if rec:
                total += 1
                if rec == pattern.best_phase:
                    correct += 1
        accuracy = correct / total if total > 0 else 0
        record("M5: Recommendation accuracy", "M", accuracy >= 0.5, 0, f"{correct}/{total} correct")

        mem.close()


# ═══════════════════════════════════════════════════════════════════
# N. CHECKPOINT & RESUME
# ═══════════════════════════════════════════════════════════════════

async def test_N_checkpoint():
    print("\n  ═══ N. CHECKPOINT & RESUME — Durability ═══")

    # N1: Goal creates checkpoint
    agent = AutonomousAgent()
    t = time.perf_counter_ns()
    state = await agent.pursue("count lines and check git status")
    ms = (time.perf_counter_ns() - t) / 1e6

    checkpoint_dir = os.path.expanduser("~/.pfaa/checkpoints")
    checkpoint_file = os.path.join(checkpoint_dir, f"{state.goal_id}.json")
    record("N1: Checkpoint created", "N", os.path.exists(checkpoint_file), ms)

    # N2: Checkpoint contains valid data
    t = time.perf_counter_ns()
    with open(checkpoint_file) as f:
        data = json.load(f)
    ms = (time.perf_counter_ns() - t) / 1e6
    record("N2: Checkpoint valid JSON", "N", data["goal_id"] == state.goal_id, ms)

    # N3: List checkpoints works
    t = time.perf_counter_ns()
    cps = agent.list_checkpoints()
    ms = (time.perf_counter_ns() - t) / 1e6
    record("N3: List checkpoints", "N", len(cps) >= 1, ms, f"{len(cps)} saved")

    # N4: Multiple goals create separate checkpoints
    state2 = await agent.pursue("compute sqrt(42) and hash test")
    distinct = state.goal_id != state2.goal_id
    both_exist = os.path.exists(os.path.join(checkpoint_dir, f"{state.goal_id}.json")) and \
                 os.path.exists(os.path.join(checkpoint_dir, f"{state2.goal_id}.json"))
    record("N4: Distinct checkpoints per goal", "N", distinct and both_exist, 0)

    await agent.shutdown()


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  PFAA STRESS & EDGE CASE BENCHMARK                             ║")
    print("║  Created by Jamie (@bencousins22) · Python 3.15 · macOS        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    total_start = time.perf_counter_ns()

    await test_I_stress()
    await test_J_latency()
    await test_K_real_workloads()
    await test_L_edge_cases()
    await test_M_exploration()
    await test_N_checkpoint()

    total_ms = (time.perf_counter_ns() - total_start) / 1e6

    # Summary
    by_cat = {}
    for r in results:
        c = r["category"]
        if c not in by_cat:
            by_cat[c] = {"passed": 0, "total": 0}
        by_cat[c]["total"] += 1
        if r["passed"]:
            by_cat[c]["passed"] += 1

    cat_names = {
        "I": "Stress Tests (scale limits)",
        "J": "Latency Profiling (μs precision)",
        "K": "Real Workloads (useful tasks)",
        "L": "Edge Cases (boundary conditions)",
        "M": "Exploration & Learning (L3)",
        "N": "Checkpoint & Resume (durability)",
    }

    total_passed = sum(1 for r in results if r["passed"])
    total_tests = len(results)

    print(f"\n{'═' * 68}")
    print(f"\n  {'CATEGORY':<50} {'RESULT':>10}")
    print(f"  {'─' * 61}")
    for cat in sorted(by_cat):
        data = by_cat[cat]
        name = cat_names.get(cat, cat)
        p, t = data["passed"], data["total"]
        bar = "█" * (p * 10 // t) + "░" * (10 - p * 10 // t)
        print(f"  {cat}. {name:<47} {p:>2}/{t:<2} {bar}")

    print(f"  {'─' * 61}")
    pct = total_passed * 100 // total_tests
    print(f"  {'TOTAL':<50} {total_passed:>2}/{total_tests}  {pct}%")
    print(f"\n  Completed in {total_ms:.0f}ms")

    print(f"\n{'═' * 68}")
    print(json.dumps({
        "benchmark": "PFAA Stress & Edge Case Benchmark v1.0",
        "total_passed": total_passed,
        "total_tests": total_tests,
        "percentage": pct,
        "elapsed_ms": round(total_ms),
        "categories": {c: by_cat[c] for c in sorted(by_cat)},
    }, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
