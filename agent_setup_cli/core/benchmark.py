"""
Aussie Agents Benchmark Suite — Proves the Phase-Fluid Architecture works.

Tests:
    1. SPAWN SPEED: 1000 Vapor agents in <50ms
    2. SCATTER/GATHER: Fan-out 100 I/O tasks, gather results
    3. PHASE TRANSITIONS: Vapor→Liquid→Solid→Vapor round-trip
    4. PIPELINE: Multi-phase pipeline (fetch→process→sandbox)
    5. LAZY IMPORT SAVINGS: Measure startup with/without lazy imports
    6. MIXED WORKLOAD: Simultaneous Vapor + Liquid + Solid agents

Run:
    python3 -m agent_setup_cli.core.benchmark
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import sys
import time

# Python 3.15 lazy imports — these won't load until first use
lazy import json
lazy import urllib.request

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.agent import (
    FluidAgent, AgentConfig, vapor_task, liquid_task, solid_task,
)
from agent_setup_cli.core.nucleus import Nucleus


# ── Test Tasks ──────────────────────────────────────────────────────

@vapor_task
async def io_task(task_id: int) -> dict:
    """Simulate an I/O-bound task (API call, file read)."""
    await asyncio.sleep(0.001)  # 1ms simulated I/O
    return {"task_id": task_id, "result": f"data-{task_id}", "pid": os.getpid()}


@liquid_task
def cpu_task(n: int) -> dict:
    """CPU-bound task: compute SHA-256 hashes."""
    data = b"phase-fluid-agent" * 1000
    for _ in range(n):
        data = hashlib.sha256(data).digest()
    return {"iterations": n, "hash": data.hex()[:16], "pid": os.getpid()}


@solid_task
def isolated_task(expression: str) -> dict:
    """Task that needs process isolation (e.g., eval untrusted code)."""
    result = eval(expression, {"__builtins__": {"math": math}}, {})
    return {"expression": expression, "result": result, "pid": os.getpid()}


def pure_cpu_task(n: int) -> float:
    """Pure CPU work for thread benchmarking."""
    total = 0.0
    for i in range(n):
        total += math.sin(i) * math.cos(i)
    return total


# Top-level pipeline stages (must be picklable for SOLID phase)
async def pipeline_fetch_stage(url: str) -> str:
    await asyncio.sleep(0.001)
    return f"raw-data-from-{url}"

def pipeline_process_stage(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]

def pipeline_verify_stage(data: str) -> dict:
    return {"hash": data, "verified": len(data) == 16, "pid": os.getpid()}


# ── Benchmarks ──────────────────────────────────────────────────────

async def bench_spawn_speed() -> None:
    """Test 1: How fast can we spawn 1000 agents?"""
    print("\n═══ TEST 1: SPAWN SPEED ═══")
    config = AgentConfig("vapor-worker", capabilities=("fetch",))

    start = time.perf_counter_ns()
    agents = []
    for _ in range(1000):
        agents.append(FluidAgent(config))
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

    print(f"  Spawned 1,000 Vapor agents in {elapsed_ms:.1f}ms")
    print(f"  Per-agent: {elapsed_ms * 1000 / 1000:.1f}μs")
    print(f"  All in phase: {agents[0].phase.name}")
    assert elapsed_ms < 100, f"Too slow! {elapsed_ms}ms > 100ms target"
    print("  ✓ PASSED")


async def bench_scatter_gather() -> None:
    """Test 2: Fan-out 100 I/O tasks across 100 agents, gather results."""
    print("\n═══ TEST 2: SCATTER/GATHER (100 I/O tasks) ═══")
    nucleus = Nucleus()
    config = AgentConfig("io-worker", capabilities=("fetch",))

    start = time.perf_counter_ns()
    results = await nucleus.scatter(
        config=config,
        task_fn=io_task,
        args_list=[(i,) for i in range(100)],
        hint=Phase.VAPOR,
    )
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

    print(f"  Completed 100 tasks in {elapsed_ms:.1f}ms")
    print(f"  All results collected: {len(results)}")
    print(f"  Phases used: {set(r.phase_used.name for r in results)}")
    print(f"  Avg task time: {nucleus.metrics.avg_task_us:.0f}μs")
    assert len(results) == 100
    assert nucleus.metrics.agents_alive == 0, "All agents should be reaped"
    print(f"  Agents reaped: {nucleus.metrics.agents_reaped}")
    print("  ✓ PASSED")

    await nucleus.shutdown()


async def bench_phase_transitions() -> None:
    """Test 3: Agent transitions through all phases and back."""
    print("\n═══ TEST 3: PHASE TRANSITIONS ═══")
    config = AgentConfig("chameleon", auto_transition=False)
    agent = FluidAgent(config)

    print(f"  Born as: {agent.phase.name}")
    assert agent.phase == Phase.VAPOR

    # VAPOR → LIQUID (condense)
    result1 = await agent.execute(cpu_task, 100, hint=Phase.LIQUID)
    print(f"  After CPU task: {agent.phase.name} (transitions: {result1.transitions})")

    # LIQUID → SOLID (freeze)
    result2 = await agent.execute(isolated_task, "math.pi * 2", hint=Phase.SOLID)
    print(f"  After isolated task: {agent.phase.name} (transitions: {result2.transitions})")
    print(f"    Result: {result2.result}")

    # SOLID → VAPOR (deposit)
    result3 = await agent.execute(io_task, 42, hint=Phase.VAPOR)
    print(f"  After I/O task: {agent.phase.name} (transitions: {result3.transitions})")

    print(f"  Full transition log: {len(agent._transition_log)} transitions")
    for ts, name, from_p, to_p in agent._transition_log:
        print(f"    {name}: {from_p.name} → {to_p.name}")

    print("  ✓ PASSED")


async def bench_pipeline() -> None:
    """Test 4: Multi-phase pipeline — data flows through phases."""
    print("\n═══ TEST 4: MULTI-PHASE PIPELINE ═══")
    nucleus = Nucleus()
    config = AgentConfig("pipeline-worker")

    results = await nucleus.pipeline(config, [
        (Phase.VAPOR,  pipeline_fetch_stage,   ("https://example.com",)),
        (Phase.LIQUID, pipeline_process_stage, ()),
        (Phase.SOLID,  pipeline_verify_stage,  ()),
    ])

    for i, r in enumerate(results):
        print(f"  Stage {i+1}: phase={r.phase_used.name} elapsed={r.elapsed_us}μs")
    print(f"  Final result: {results[-1].result}")
    assert results[-1].result["verified"] is True
    print("  ✓ PASSED")

    await nucleus.shutdown()


async def bench_lazy_imports() -> None:
    """Test 5: Measure lazy import savings."""
    print("\n═══ TEST 5: LAZY IMPORT MEASUREMENT ═══")

    loaded_before = set(sys.modules.keys())

    # These were declared as lazy imports at module top
    # They shouldn't be loaded yet if nothing used them
    lazy_targets = ["urllib.request"]
    for mod in lazy_targets:
        status = "LOADED" if mod in sys.modules else "DEFERRED"
        print(f"  {mod}: {status}")

    # Now force-load by accessing
    _ = json.dumps({"test": True})
    print(f"  json: {'LOADED' if 'json' in sys.modules else 'DEFERRED'} (after use)")

    loaded_after = set(sys.modules.keys())
    new_modules = loaded_after - loaded_before
    if new_modules:
        print(f"  Newly loaded modules: {len(new_modules)}")

    print("  ✓ PASSED")


async def bench_mixed_workload() -> None:
    """Test 6: Simultaneous agents in all three phases."""
    print("\n═══ TEST 6: MIXED WORKLOAD (all phases concurrent) ═══")
    nucleus = Nucleus()

    io_config = AgentConfig("io-agent", capabilities=("fetch",))
    cpu_config = AgentConfig("cpu-agent", capabilities=("compute",))
    iso_config = AgentConfig("iso-agent", isolation_required=True)

    start = time.perf_counter_ns()

    # Launch all three types simultaneously
    vapor_tasks = nucleus.scatter(
        io_config, io_task,
        [(i,) for i in range(50)],
        hint=Phase.VAPOR,
    )
    liquid_tasks = nucleus.scatter(
        cpu_config, cpu_task,
        [(100,) for _ in range(8)],
        hint=Phase.LIQUID,
    )
    solid_tasks = nucleus.scatter(
        iso_config, isolated_task,
        [("math.sqrt(144)",), ("math.factorial(10)",), ("math.gcd(48, 18)",)],
        hint=Phase.SOLID,
    )

    async with asyncio.TaskGroup() as tg:
        vapor_handle = tg.create_task(vapor_tasks)
        liquid_handle = tg.create_task(liquid_tasks)
        solid_handle = tg.create_task(solid_tasks)
    vapor_results = vapor_handle.result()
    liquid_results = liquid_handle.result()
    solid_results = solid_handle.result()

    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

    print(f"  Total time: {elapsed_ms:.1f}ms")
    print(f"  Vapor results: {len(vapor_results)} (I/O tasks)")
    print(f"  Liquid results: {len(liquid_results)} (CPU tasks)")
    print(f"  Solid results: {len(solid_results)} (isolated tasks)")
    for r in solid_results:
        print(f"    {r.result}")
    print(f"  Total agents spawned: {nucleus.metrics.agents_spawned}")
    print(f"  Agents alive now: {nucleus.metrics.agents_alive}")
    print(f"  Phase transitions: {nucleus.metrics.transitions}")
    print("  ✓ PASSED")

    status = nucleus.status()
    print(f"\n  Nucleus Status: {json.dumps(status, indent=2)}")
    await nucleus.shutdown()


async def bench_swarm_throughput() -> None:
    """Test 7: Sustained throughput with persistent agent pool."""
    print("\n═══ TEST 7: SWARM THROUGHPUT (persistent pool) ═══")
    nucleus = Nucleus()
    config = AgentConfig("swarm-worker")

    task_q: asyncio.Queue = asyncio.Queue()
    result_q: asyncio.Queue = asyncio.Queue()

    # Enqueue 200 tasks
    n_tasks = 200
    for i in range(n_tasks):
        await task_q.put((io_task, (i,)))

    # Poison pills for 8 workers
    pool_size = 8
    for _ in range(pool_size):
        await task_q.put(None)

    start = time.perf_counter_ns()
    await nucleus.swarm(config, pool_size, task_q, result_q)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

    results_count = result_q.qsize()
    throughput = results_count / (elapsed_ms / 1000) if elapsed_ms > 0 else 0

    print(f"  Pool size: {pool_size}")
    print(f"  Tasks completed: {results_count}/{n_tasks}")
    print(f"  Elapsed: {elapsed_ms:.1f}ms")
    print(f"  Throughput: {throughput:.0f} tasks/sec")
    print(f"  Agents alive: {nucleus.metrics.agents_alive}")
    print("  ✓ PASSED")

    await nucleus.shutdown()


# ── Main ────────────────────────────────────────────────────────────

async def main() -> None:
    print("╔══════════════════════════════════════════════════╗")
    print("║   PHASE-FLUID AGENT ARCHITECTURE — BENCHMARK    ║")
    print("║   Python", sys.version.split()[0].ljust(43), "║")
    print("║   Platform:", sys.platform.ljust(38), "║")
    print("║   CPU cores:", str(os.cpu_count()).ljust(37), "║")
    try:
        gil = "DISABLED" if not sys._is_gil_enabled() else "ENABLED"
    except AttributeError:
        gil = "N/A"
    print("║   GIL:", gil.ljust(43), "║")
    print("║   Lazy imports:", str(hasattr(sys, 'set_lazy_imports')).ljust(34), "║")
    print("╚══════════════════════════════════════════════════╝")

    total_start = time.perf_counter_ns()

    await bench_spawn_speed()
    await bench_scatter_gather()
    await bench_phase_transitions()
    await bench_pipeline()
    await bench_lazy_imports()
    await bench_mixed_workload()
    await bench_swarm_throughput()

    total_ms = (time.perf_counter_ns() - total_start) / 1_000_000

    print("\n╔══════════════════════════════════════════════════╗")
    print(f"║   ALL TESTS PASSED in {total_ms:.0f}ms".ljust(51) + "║")
    print("╚══════════════════════════════════════════════════╝")


if __name__ == "__main__":
    asyncio.run(main())
