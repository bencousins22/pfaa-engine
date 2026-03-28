# Aussie Loop — Automated Learning Cycles

Run continuous learning cycles to build up the JMEM memory system.

## When the user invokes /aussie-loop

Execute a learning cycle using Claude Code native tools — no CLI required.

### Single Learning Cycle

**Phase 1: Warmup (Data Collection)**

Profile the available tools and collect baseline data:

1. Read `agent_setup_cli/core/tools.py` and `agent_setup_cli/core/tools_extended.py` to enumerate all registered tools
2. For each tool category, use `mcp__jmem__jmem_recall` to check existing baseline data
3. Run sample tool executions via Python sandbox to collect fresh timing data:
   ```bash
   python3 -c "from agent_setup_cli.core.framework import PFAAFramework; import asyncio; asyncio.run(PFAAFramework().warmup())"
   ```
4. Store results: `mcp__jmem__jmem_remember(content="Tool baseline: [tool] phase=[phase] latency=[ms]", level=1)`

**Phase 2: Learn (Pattern Extraction)**

1. Use `mcp__jmem__jmem_status` to check memory layer counts
2. Use `mcp__jmem__jmem_consolidate` to promote high-confidence episodes to concepts
3. Use `mcp__jmem__jmem_reflect` to analyze patterns across recent memories
4. Store discovered patterns: `mcp__jmem__jmem_remember(content="Pattern: [insight]", level=2)`

### Full Evolution Loop

After completing a single cycle, optionally chain into `/aussie-evolve` for deep analysis:
1. Run warmup + learn (above)
2. Then invoke /aussie-evolve for instinct extraction, memory cleanup, and skill evolution

### Memory Growth Per Cycle
- ~23 L1 episodes (one per profiled tool)
- L2 patterns refine as confidence accumulates
- L3 strategies emerge after ~3 consecutive cycles
- L4 skills crystallize from validated strategies

### When To Run
- After first install to establish baselines
- After adding new tools or agents
- Before running /aussie-evolve (to feed it fresh data)
- On a schedule: use `/loop 10m /aussie-loop` for continuous learning
