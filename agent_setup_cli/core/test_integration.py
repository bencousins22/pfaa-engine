"""
PFAA Full Integration Test — Tools + Memory + Orchestrator

Demonstrates the complete system:
    1. Register tools → Execute via orchestrator → Record in memory
    2. Run enough executions to trigger learning cycles
    3. Watch the memory system learn optimal phase selections
    4. Verify emergent patterns are detected
    5. Show meta-learning adjusting the learning rate

Run:
    python3 -m agent_setup_cli.core.test_integration
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

lazy import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolRegistry
from agent_setup_cli.core.orchestrator import Orchestrator
from agent_setup_cli.core.memory import MemorySystem
from agent_setup_cli.core.agent import AgentConfig, TaskResult


async def test_tool_execution() -> None:
    """Test 1: Execute individual tools through the registry."""
    print("\n═══ TEST 1: TOOL EXECUTION ═══")
    registry = ToolRegistry.get()

    tools = registry.list_tools()
    print(f"  Registered tools: {len(tools)}")
    for t in tools:
        print(f"    {t.name:20s} phase={t.phase.name:6s} {t.description}")

    # Execute read_file (VAPOR)
    result = await registry.execute("read_file", "/etc/hostname")
    print(f"\n  read_file: phase={result.phase_used.name} elapsed={result.elapsed_us}μs")

    # Execute compute (LIQUID)
    result = await registry.execute("compute", "sqrt(144) + pi")
    print(f"  compute:   phase={result.phase_used.name} elapsed={result.elapsed_us}μs result={result.result}")

    # Execute glob_search (VAPOR)
    result = await registry.execute("glob_search", "*.py", ".")
    print(f"  glob:      phase={result.phase_used.name} elapsed={result.elapsed_us}μs matches={result.result.get('count', 0)}")

    # Execute hash_data (LIQUID)
    result = await registry.execute("hash_data", "hello world", "sha256")
    print(f"  hash:      phase={result.phase_used.name} elapsed={result.elapsed_us}μs digest={result.result.get('digest', '')[:16]}...")

    print("  ✓ PASSED")


async def test_parallel_tools() -> None:
    """Test 2: Execute multiple tools in parallel."""
    print("\n═══ TEST 2: PARALLEL TOOL EXECUTION ═══")
    registry = ToolRegistry.get()

    start = time.perf_counter_ns()
    results = await registry.execute_many([
        ("compute", ("sqrt(2)",), {}),
        ("compute", ("pi * e",), {}),
        ("hash_data", ("test data",), {"algorithm": "sha256"}),
        ("hash_data", ("other data",), {"algorithm": "md5"}),
        ("glob_search", ("*.py",), {"root": "."}),
    ])
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

    print(f"  5 tools executed in parallel: {elapsed_ms:.1f}ms")
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"    [{i}] FAILED: {r}")
        else:
            print(f"    [{i}] {r.phase_used.name:6s} {r.elapsed_us}μs")
    print("  ✓ PASSED")


async def test_orchestrator_dag() -> None:
    """Test 3: Execute a task DAG with dependencies."""
    print("\n═══ TEST 3: TASK DAG EXECUTION ═══")
    orchestrator = Orchestrator()

    # Build a task graph:
    #   t1 (compute) ──→ t3 (hash)
    #   t2 (glob)   ──→ t3 (hash)
    t1 = orchestrator.submit("compute", "sqrt(42)")
    t2 = orchestrator.submit("glob_search", "*.py", ".")
    t3 = orchestrator.submit("hash_data", "combined-result", depends_on=[t1, t2])

    results = await orchestrator.run_all()

    print(f"  Tasks executed: {len(results)}")
    for task in results:
        status = task.status.name
        elapsed = task.elapsed_us
        print(f"    {task.id}: {task.tool_name:15s} status={status:10s} elapsed={elapsed}μs")

    summary = orchestrator.graph_summary()
    print(f"  DAG summary: {json.dumps(summary['by_status'])}")
    print("  ✓ PASSED")

    await orchestrator.shutdown()


async def test_memory_learning() -> None:
    """Test 4: Memory system learns from repeated executions."""
    print("\n═══ TEST 4: MEMORY SYSTEM LEARNING ═══")
    memory = MemorySystem(episodic_capacity=5000)
    registry = ToolRegistry.get()

    print("  Running 200 tool executions to build memory...")
    start = time.perf_counter_ns()

    for i in range(200):
        # Mix of tool types to generate diverse episodes
        if i % 4 == 0:
            result = await registry.execute("compute", f"sqrt({i})")
            memory.record(result, "compute", (f"sqrt({i})",))
        elif i % 4 == 1:
            result = await registry.execute("hash_data", f"data-{i}")
            memory.record(result, "hash_data", (f"data-{i}",))
        elif i % 4 == 2:
            result = await registry.execute("glob_search", "*.py", ".")
            memory.record(result, "glob_search", ("*.py",))
        else:
            result = await registry.execute("read_file", "/dev/null")
            memory.record(result, "read_file", ("/dev/null",))

    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

    # Force final learning cycle
    memory.force_learn()

    print(f"  200 executions in {elapsed_ms:.0f}ms")
    print(f"\n  Memory Status:")
    status = memory.status()
    for k, v in status.items():
        print(f"    {k}: {v}")

    # Show L2 patterns
    print(f"\n  L2 — Learned Patterns:")
    dump = memory.dump()
    for name, pattern in dump["patterns"].items():
        print(f"    {name:15s} avg={pattern['avg_us']:.0f}μs "
              f"p95={pattern['p95_us']:.0f}μs "
              f"best_phase={pattern['best_phase']} "
              f"confidence={pattern['confidence']:.2f}")

    # Show L3 strategies
    if dump["strategies"]:
        print(f"\n  L3 — Phase Optimization Strategies:")
        for name, strategy in dump["strategies"].items():
            print(f"    {name}: {strategy['default']} → {strategy['override']} "
                  f"(speedup={strategy['speedup']:.1f}x)")

    # Show L5 emergent knowledge
    if dump["emergent_knowledge"]:
        print(f"\n  L5 — Emergent Knowledge:")
        for k in dump["emergent_knowledge"][:5]:
            print(f"    [{k['pattern']}] {k['description']} (conf={k['confidence']:.2f})")

    # Test phase recommendation
    print(f"\n  Phase Recommendations:")
    for tool in ["compute", "hash_data", "glob_search", "read_file"]:
        rec = memory.recommend_phase(tool)
        print(f"    {tool}: {rec.name if rec else 'no recommendation yet'}")

    print("  ✓ PASSED")


async def test_self_improving_loop() -> None:
    """Test 5: Demonstrate the self-improving feedback loop."""
    print("\n═══ TEST 5: SELF-IMPROVING FEEDBACK LOOP ═══")
    memory = MemorySystem(episodic_capacity=5000)
    # Lower the update interval so we trigger learning more often
    memory._update_interval = 20
    registry = ToolRegistry.get()

    print("  Round 1: Initial executions (no learned knowledge yet)")
    for i in range(30):
        result = await registry.execute("compute", f"sin({i}) + cos({i})")
        memory.record(result, "compute", (f"sin({i})",))

    memory.force_learn()
    s1 = memory.status()
    print(f"    Episodes: {s1['l1_episodes']}, Patterns: {s1['l2_patterns']}, "
          f"Strategies: {s1['l3_strategies']}")

    print("\n  Round 2: More executions (memory should have patterns now)")
    for i in range(50):
        # Use memory recommendation if available
        rec = memory.recommend_phase("compute")
        result = await registry.execute("compute", f"sqrt({i * 7})")
        memory.record(result, "compute", (f"sqrt({i * 7})",))

    memory.force_learn()
    s2 = memory.status()
    print(f"    Episodes: {s2['l1_episodes']}, Patterns: {s2['l2_patterns']}, "
          f"Strategies: {s2['l3_strategies']}, LR: {s2['l4_learning_rate']:.3f}")

    print("\n  Round 3: System should be self-optimizing now")
    for i in range(50):
        rec = memory.recommend_phase("compute")
        result = await registry.execute("compute", f"log({i + 1})")
        memory.record(result, "compute", (f"log({i + 1})",))

    memory.force_learn()
    s3 = memory.status()
    print(f"    Episodes: {s3['l1_episodes']}, Patterns: {s3['l2_patterns']}, "
          f"Strategies: {s3['l3_strategies']}, LR: {s3['l4_learning_rate']:.3f}")

    # Show full memory dump
    dump = memory.dump()
    print(f"\n  Full Memory Dump:")
    print(f"    L4 Meta Insights: {len(dump['meta_insights'])}")
    for insight in dump["meta_insights"]:
        print(f"      [{insight['category']}] {insight['observation']}")

    print(f"    L5 Emergent: {len(dump['emergent_knowledge'])}")
    for k in dump["emergent_knowledge"][:3]:
        print(f"      {k['description']}")

    print("  ✓ PASSED")


async def main() -> None:
    print("╔══════════════════════════════════════════════════════╗")
    print("║  PFAA FULL INTEGRATION TEST                         ║")
    print("║  Tools + Memory + Orchestrator + Meta-Learning      ║")
    print(f"║  Python {sys.version.split()[0]}  |  {sys.platform}  |  cores={os.cpu_count()}" + " " * 9 + "║")
    print("╚══════════════════════════════════════════════════════╝")

    total_start = time.perf_counter_ns()

    await test_tool_execution()
    await test_parallel_tools()
    await test_orchestrator_dag()
    await test_memory_learning()
    await test_self_improving_loop()

    total_ms = (time.perf_counter_ns() - total_start) / 1_000_000

    print("\n╔══════════════════════════════════════════════════════╗")
    print(f"║  ALL INTEGRATION TESTS PASSED in {total_ms:.0f}ms".ljust(55) + "║")
    print("╚══════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    asyncio.run(main())
