#!/usr/bin/env python3
"""
Aussie Agents Benchmark — Standardized agent capability assessment.

Tests 8 categories that measure what matters for an agent framework:

    1. SPAWN LATENCY       — How fast can agents be created?
    2. PARALLEL THROUGHPUT  — How many concurrent tasks per second?
    3. TOOL DIVERSITY       — How many distinct tool types available?
    4. TASK DECOMPOSITION   — Can NL goals be broken into subtask DAGs?
    5. MEMORY & LEARNING    — Does the agent learn from execution?
    6. FAULT TOLERANCE      — Does it recover from failures?
    7. SELF-IMPROVEMENT     — Can it analyze and extend itself?
    8. PERSISTENCE          — Does state survive across sessions?

Scoring: Each category is 0-125 points. Maximum score: 1000.

This benchmark is designed to be runnable against ANY agent framework
by implementing the same test interface. Aussie Agents results are the baseline.

Created by Jamie (@bencousins22)
Python 3.15
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time

lazy import json
lazy import random

from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

from agent_setup_cli.core.framework import Framework
from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.agent import FluidAgent, AgentConfig
from agent_setup_cli.core.nucleus import Nucleus
from agent_setup_cli.core.delegation import Supervisor, WorkerSpec, RestartPolicy
from agent_setup_cli.core.persistence import PersistentMemory

import agent_setup_cli.core.tools_extended
try:
    import agent_setup_cli.core.tools_generated
except ImportError:
    pass


@dataclass(slots=True)
class BenchResult:
    category: str
    score: int
    max_score: int
    metrics: dict
    notes: str = ""



# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 1: SPAWN LATENCY
# ═══════════════════════════════════════════════════════════════════

async def bench_spawn_latency() -> BenchResult:
    """How fast can we create agents?"""
    config = AgentConfig("bench-spawn")

    # Spawn 1000 agents and measure
    start = time.perf_counter_ns()
    agents = [FluidAgent(config) for _ in range(1000)]
    elapsed_us = (time.perf_counter_ns() - start) // 1000
    per_agent_us = elapsed_us / 1000

    # Scoring: <10μs = 125, <50μs = 100, <100μs = 75, <1ms = 50, <10ms = 25, else 0
    if per_agent_us < 10:
        score = 125
    elif per_agent_us < 50:
        score = 100
    elif per_agent_us < 100:
        score = 75
    elif per_agent_us < 1000:
        score = 50
    elif per_agent_us < 10000:
        score = 25
    else:
        score = 0

    return BenchResult(
        category="1. SPAWN LATENCY",
        score=score, max_score=125,
        metrics={
            "agents_spawned": 1000,
            "total_us": elapsed_us,
            "per_agent_us": round(per_agent_us, 1),
        },
        notes=f"{per_agent_us:.1f}μs per agent",
    )


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 2: PARALLEL THROUGHPUT
# ═══════════════════════════════════════════════════════════════════

async def bench_parallel_throughput() -> BenchResult:
    """How many tasks per second can we sustain?"""
    nucleus = Nucleus()
    config = AgentConfig("bench-throughput")

    async def dummy_task(n: int) -> dict:
        await asyncio.sleep(0.0001)  # 0.1ms simulated work
        return {"n": n}

    start = time.perf_counter_ns()
    results = await nucleus.scatter(
        config=config,
        task_fn=dummy_task,
        args_list=[(i,) for i in range(500)],
        hint=Phase.VAPOR,
    )
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    throughput = len(results) / (elapsed_ms / 1000)

    await nucleus.shutdown()

    # Scoring: >5000 = 125, >2000 = 100, >500 = 75, >100 = 50, >10 = 25, else 0
    if throughput > 5000:
        score = 125
    elif throughput > 2000:
        score = 100
    elif throughput > 500:
        score = 75
    elif throughput > 100:
        score = 50
    elif throughput > 10:
        score = 25
    else:
        score = 0

    return BenchResult(
        category="2. PARALLEL THROUGHPUT",
        score=score, max_score=125,
        metrics={
            "tasks": 500,
            "elapsed_ms": round(elapsed_ms, 1),
            "throughput_per_sec": round(throughput),
        },
        notes=f"{throughput:.0f} tasks/sec",
    )


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 3: TOOL DIVERSITY
# ═══════════════════════════════════════════════════════════════════

async def bench_tool_diversity() -> BenchResult:
    """How many distinct tool types are available?"""
    from agent_setup_cli.core.tools import ToolRegistry
    registry = ToolRegistry.get()
    tools = registry.list_tools()

    by_phase = {}
    capabilities = set()
    for t in tools:
        by_phase[t.phase.name] = by_phase.get(t.phase.name, 0) + 1
        capabilities.update(t.capabilities)

    # Scoring: >25 tools = 125, >15 = 100, >10 = 75, >5 = 50, >1 = 25, else 0
    count = len(tools)
    if count > 25:
        score = 125
    elif count > 15:
        score = 100
    elif count > 10:
        score = 75
    elif count > 5:
        score = 50
    elif count > 1:
        score = 25
    else:
        score = 0

    return BenchResult(
        category="3. TOOL DIVERSITY",
        score=score, max_score=125,
        metrics={
            "total_tools": count,
            "by_phase": by_phase,
            "unique_capabilities": len(capabilities),
            "capability_list": sorted(capabilities),
        },
        notes=f"{count} tools across {len(by_phase)} phases",
    )


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 4: TASK DECOMPOSITION
# ═══════════════════════════════════════════════════════════════════

async def bench_task_decomposition() -> BenchResult:
    """Can goals be decomposed into parallel subtask DAGs?"""
    fw = Framework()

    test_goals = [
        ("count lines and check git status", 2),
        ("search for TODO and analyze code and check disk", 3),
        ("compute sqrt(42) and hash test and system info and git log", 4),
        ("review codebase and find patterns and count lines and check status and disk usage and dns lookup", 5),
    ]

    results = []
    for goal, expected_min in test_goals:
        state = await fw.run(goal)
        decomposed = len(state.subtasks)
        completed = sum(1 for st in state.subtasks if st.status == "completed")
        results.append({
            "goal": goal[:50],
            "subtasks": decomposed,
            "completed": completed,
            "expected_min": expected_min,
            "passed": decomposed >= expected_min and completed == decomposed,
        })

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    await fw.shutdown()

    # Scoring: 4/4 = 125, 3/4 = 100, 2/4 = 75, 1/4 = 50, else 0
    score = min(125, passed * 31)

    return BenchResult(
        category="4. TASK DECOMPOSITION",
        score=score, max_score=125,
        metrics={"passed": passed, "total": total, "details": results},
        notes=f"{passed}/{total} decomposition tests passed",
    )


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 5: MEMORY & LEARNING
# ═══════════════════════════════════════════════════════════════════

async def bench_memory_learning() -> BenchResult:
    """Does the agent learn from execution?"""
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = PersistentMemory(storage_dir=tmpdir)
        from agent_setup_cli.core.tools import ToolRegistry
        registry = ToolRegistry.get()
        random.seed(42)

        # Run 100 executions
        sync_tools = [("compute", ("sqrt(42)",)), ("hash_data", ("test",))]
        for i in range(100):
            name, args = sync_tools[i % len(sync_tools)]
            result = await registry.execute(name, *args)
            mem.record(result, name, args)

        mem.force_learn()
        status = mem.status()

        has_episodes = status["l1_episodes"] >= 100
        has_patterns = status["l2_patterns"] >= 2
        has_persistence = status["db_size_kb"] > 0

        # Check pattern quality
        patterns = mem.memory.l2_semantic._patterns
        has_perf_data = all(
            p.avg_elapsed_us > 0 and p.success_rate > 0
            for p in patterns.values()
        )

        # Check recommendations work
        rec = mem.recommend_phase("compute")
        has_recommendations = rec is not None

        checks = [has_episodes, has_patterns, has_persistence, has_perf_data, has_recommendations]
        passed = sum(checks)

        mem.close()

    score = min(125, passed * 25)

    return BenchResult(
        category="5. MEMORY & LEARNING",
        score=score, max_score=125,
        metrics={
            "episodes": status["l1_episodes"],
            "patterns": status["l2_patterns"],
            "strategies": status["l3_strategies"],
            "has_recommendations": has_recommendations,
            "db_size_kb": status["db_size_kb"],
            "checks_passed": passed,
        },
        notes=f"{passed}/5 learning checks passed",
    )


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 6: FAULT TOLERANCE
# ═══════════════════════════════════════════════════════════════════

async def bench_fault_tolerance() -> BenchResult:
    """Does it recover from failures?"""
    nucleus = Nucleus()

    call_count = 0
    def flaky_fn(n: int) -> dict:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError(f"Simulated failure #{call_count}")
        return {"result": n * 2, "attempts": call_count}

    # Test supervisor restart
    sup = Supervisor("fault-test", nucleus)
    sup.add_worker(WorkerSpec(
        name="flaky",
        task_fn=flaky_fn,
        args=(42,),
        phase=Phase.LIQUID,
        restart_policy=RestartPolicy.ON_ERROR,
        max_restarts=3,
    ))

    result = await sup.run_all()
    recovered = result["completed"] == 1 and result["restarts"] > 0

    # Test graceful degradation — one worker fails permanently, others succeed
    def always_fail(n: int) -> dict:
        raise RuntimeError("permanent failure")

    def always_succeed(n: int) -> dict:
        return {"result": n}

    sup2 = Supervisor("degradation-test", nucleus)
    sup2.add_worker(WorkerSpec("fail", always_fail, args=(1,), phase=Phase.LIQUID,
                               restart_policy=RestartPolicy.NEVER))
    sup2.add_worker(WorkerSpec("ok1", always_succeed, args=(2,), phase=Phase.LIQUID))
    sup2.add_worker(WorkerSpec("ok2", always_succeed, args=(3,), phase=Phase.LIQUID))

    result2 = await sup2.run_all()
    graceful = result2["completed"] == 2 and result2["failed"] == 1

    await nucleus.shutdown()

    checks = [recovered, graceful]
    passed = sum(checks)
    score = min(125, passed * 62)

    return BenchResult(
        category="6. FAULT TOLERANCE",
        score=score, max_score=125,
        metrics={
            "restart_recovery": recovered,
            "graceful_degradation": graceful,
            "restarts_used": result.get("restarts", 0),
        },
        notes=f"{passed}/2 fault tolerance checks passed",
    )


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 7: SELF-IMPROVEMENT
# ═══════════════════════════════════════════════════════════════════

async def bench_self_improvement() -> BenchResult:
    """Can the agent analyze and extend itself?"""
    from agent_setup_cli.core.self_build import SelfBuilder, SELF_ROOT

    builder = SelfBuilder()
    try:
        # Can it introspect its own code?
        analysis = await builder.introspect()
        can_introspect = analysis.total_lines > 0 and analysis.total_files > 0

        # Can it find improvements?
        improvements = await builder._static_diagnose()
        can_diagnose = len(improvements) > 0

        # Can it sandbox-test code?
        test_code = "@registry.register(ToolSpec(name='bench_test', description='test', phase=Phase.LIQUID, capabilities=('test',)))\ndef tool_bench_test(): return {'ok': True}"
        test_result = await builder.test_code(test_code)
        can_test = test_result.get("success", False)

    finally:
        await builder.shutdown()

    checks = [can_introspect, can_diagnose, can_test]
    passed = sum(checks)
    score = min(125, passed * 42)

    return BenchResult(
        category="7. SELF-IMPROVEMENT",
        score=score, max_score=125,
        metrics={
            "can_introspect": can_introspect,
            "can_diagnose": can_diagnose,
            "can_sandbox_test": can_test,
            "lines_analyzed": analysis.total_lines if can_introspect else 0,
            "improvements_found": len(improvements) if can_diagnose else 0,
        },
        notes=f"{passed}/3 self-improvement checks passed",
    )


# ═══════════════════════════════════════════════════════════════════
# BENCHMARK 8: PERSISTENCE
# ═══════════════════════════════════════════════════════════════════

async def bench_persistence() -> BenchResult:
    """Does state survive across sessions?"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from agent_setup_cli.core.tools import ToolRegistry
        registry = ToolRegistry.get()

        # Session 1: Write data
        mem1 = PersistentMemory(storage_dir=tmpdir)
        for i in range(50):
            result = await registry.execute("compute", f"sqrt({i})")
            mem1.record(result, "compute", (f"sqrt({i})",))
        mem1.force_learn()
        s1_episodes = mem1.status()["l1_episodes"]
        s1_patterns = mem1.status()["l2_patterns"]
        mem1.close()

        # Session 2: Read data back
        mem2 = PersistentMemory(storage_dir=tmpdir)
        s2_episodes = mem2.status()["l1_episodes"]
        s2_patterns = mem2.status()["l2_patterns"]
        rec = mem2.recommend_phase("compute")
        mem2.close()

        episodes_persist = s2_episodes >= s1_episodes
        patterns_persist = s2_patterns >= s1_patterns
        recommendations_persist = rec is not None

    checks = [episodes_persist, patterns_persist, recommendations_persist]
    passed = sum(checks)
    score = min(125, passed * 42)

    return BenchResult(
        category="8. PERSISTENCE",
        score=score, max_score=125,
        metrics={
            "session1_episodes": s1_episodes,
            "session2_episodes": s2_episodes,
            "episodes_survived": episodes_persist,
            "patterns_survived": patterns_persist,
            "recommendations_survived": recommendations_persist,
        },
        notes=f"{passed}/3 persistence checks passed",
    )


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  AUSSIE AGENTS BENCHMARK — Standardized Assessment       ║")
    print("║  Created by Jamie (@bencousins22)                        ║")
    print("║  Python 3.15.0a7 · macOS · Phase-Fluid Architecture      ║")
    print("╚════════════════════════════════════════════════════════════╝")

    benchmarks = [
        bench_spawn_latency,
        bench_parallel_throughput,
        bench_tool_diversity,
        bench_task_decomposition,
        bench_memory_learning,
        bench_fault_tolerance,
        bench_self_improvement,
        bench_persistence,
    ]

    results: list[BenchResult] = []
    total_start = time.perf_counter_ns()

    for bench_fn in benchmarks:
        name = bench_fn.__doc__.strip().split("\n")[0] if bench_fn.__doc__ else bench_fn.__name__
        print(f"\n{'─' * 60}")
        print(f"  {name}")
        start = time.perf_counter_ns()

        try:
            result = await bench_fn()
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            results.append(result)
            bar = "█" * (result.score * 20 // result.max_score) + "░" * (20 - result.score * 20 // result.max_score)
            print(f"  {result.category}: {result.score}/{result.max_score} {bar}")
            print(f"  {result.notes}  ({elapsed:.0f}ms)")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append(BenchResult(
                category=bench_fn.__name__,
                score=0, max_score=125,
                metrics={"error": str(e)},
                notes=f"Failed: {e}",
            ))

    total_ms = (time.perf_counter_ns() - total_start) / 1_000_000
    total_score = sum(r.score for r in results)
    max_score = sum(r.max_score for r in results)

    print(f"\n{'═' * 60}")
    print(f"\n  FINAL SCORECARD")
    print(f"  {'─' * 50}")
    for r in results:
        pct = r.score * 100 // r.max_score if r.max_score > 0 else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"  {r.category:30s} {r.score:4d}/{r.max_score:4d} {bar} {pct}%")
    print(f"  {'─' * 50}")
    total_pct = total_score * 100 // max_score if max_score > 0 else 0
    print(f"  {'TOTAL':30s} {total_score:4d}/{max_score:4d}              {total_pct}%")
    print(f"\n  Completed in {total_ms:.0f}ms")

    # JSON output
    print(f"\n{'═' * 60}")
    print(json.dumps({
        "benchmark": "Aussie Agents Benchmark v1.0",
        "framework": "Aussie Agents — Phase-Fluid Agent Architecture",
        "python": "3.15.0a7",
        "total_score": total_score,
        "max_score": max_score,
        "percentage": total_pct,
        "elapsed_ms": round(total_ms),
        "categories": [
            {
                "name": r.category,
                "score": r.score,
                "max": r.max_score,
                "pct": r.score * 100 // r.max_score if r.max_score > 0 else 0,
                "notes": r.notes,
                "metrics": r.metrics,
            }
            for r in results
        ],
    }, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
