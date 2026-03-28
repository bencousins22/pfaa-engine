# Aussie Evolve — Continuous Learning & Memory Management

Automated learning, memory cleanup, and skill evolution using Claude Code native tools.

## When the user invokes /aussie-evolve

Run the full evolution cycle directly — no CLI required.

### Step 1: Recall & Analyze Memory State

```
Use mcp__jmem__jmem_status to get current memory stats.
Use mcp__jmem__jmem_recall with broad queries to sample memory health:
  - jmem_recall(query="tool performance patterns")
  - jmem_recall(query="recurring errors or failures")
  - jmem_recall(query="successful strategies")
```

### Step 2: Extract Instincts (Recurring Patterns)

Analyze recalled memories for:
- **Tool co-occurrence** — which tools are always used together?
- **Phase preferences** — which phases consistently perform best?
- **Success patterns** — what approaches have Q > 0.8?
- **Failure patterns** — what approaches have Q < 0.2?

Use `mcp__jmem__jmem_reflect` to synthesize observations into higher-level insights.

### Step 3: Clean Memory

Use `mcp__jmem__jmem_consolidate` to:
- Promote validated L1 episodes to L2 concepts (Q > 0.8, retrieval_count > 3)
- Merge near-duplicate memories (cosine similarity > 0.95)
- Flag low-value memories (Q < 0.2) for pruning

### Step 4: Evolve Skills

Scan `.claude/skills/` for all SKILL.md files. For each:
1. Read the skill file
2. Check if referenced commands/tools still exist
3. If broken references found, rewrite to use working alternatives
4. If high-confidence instincts suggest a new skill, draft a new SKILL.md

Use `mcp__jmem__jmem_evolve` to trigger L2/L3/L4 pattern extraction.

### Step 5: Reinforce & Learn

Use `mcp__jmem__jmem_reward` to reinforce memories that led to successful outcomes.
Store the evolution cycle results: `mcp__jmem__jmem_remember(content="Evolution cycle completed: [summary]", level=3)`

## Memory Growth Expectations
- L1 Episodes accumulate per tool execution
- L2 Patterns extracted when episodes cluster (every ~50 episodes)
- L3 Strategies crystallize after ~3 evolution cycles
- L4 Skills emerge from validated L3 strategies

## What Makes This Different from /aussie-loop
- `/aussie-loop` runs warmup + learn (data collection)
- `/aussie-evolve` runs analysis + cleanup + skill synthesis (intelligence extraction)
- Run loop first to collect data, then evolve to extract knowledge
