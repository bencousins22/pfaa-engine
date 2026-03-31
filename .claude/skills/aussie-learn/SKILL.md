# Aussie Learn — Full JMEM Cognitive Cycle

Run the complete 8-step JMEM self-learning cycle in one shot. This skill recalls recent knowledge, reinforces it, consolidates and promotes memories, runs meta-learning and emergent synthesis, extracts skills, decays stale entries, and verifies health.

## When the user invokes /aussie-learn

Execute all 8 steps below **in order**, waiting for each to complete before proceeding to the next. Use the JMEM MCP tools directly — no CLI fallback.

### Step 1: RECALL

Retrieve recent task outcomes and learnings to seed the cycle.

```
mcp__jmem__jmem_recall(query="recent tasks outcomes learnings", limit=5)
```

Note the number of memories returned and their Q-values. These become the working set for reinforcement.

### Step 2: REWARD

Reinforce the recalled memories with a positive reward signal.

```
mcp__jmem__jmem_reward_recalled(reward=0.8)
```

Record how many memories were reinforced.

### Step 3: CONSOLIDATE

Link related memories via keyword clustering, auto-promote high-Q episodes to concepts, and merge near-duplicates.

```
mcp__jmem__jmem_consolidate()
```

Record promotions count and links created.

### Step 4: META-LEARN

Analyze the learning process: Q-distribution, promotion velocity, keyword diversity, reward patterns. Insights are auto-stored as L4 META memories.

```
mcp__jmem__jmem_meta_learn()
```

Record any meta-insights discovered.

### Step 5: EMERGENT

Discover cross-cutting patterns across all layers: keyword clusters, promotion chains, knowledge gaps, graph density. Discoveries are auto-stored as L5 EMERGENT memories.

```
mcp__jmem__jmem_emergent()
```

Record emergent discoveries found.

### Step 6: EXTRACT

Crystallize high-Q principles (Q >= 0.92, retrievals >= 5) into structured SKILL memories at L4.

```
mcp__jmem__jmem_extract_skills()
```

Record how many skills were extracted.

### Step 7: DECAY

Weaken memories that have been idle for more than 48 hours. Prevents stale knowledge from blocking the promotion pipeline.

```
mcp__jmem__jmem_decay(hours_threshold=48)
```

Record how many memories were decayed.

### Step 8: STATUS

Verify overall memory health after the cycle.

```
mcp__jmem__jmem_status()
```

Capture the full status output for the report.

## Output Format

After all 8 steps complete, print this formatted report:

```
====================================
  JMEM COGNITIVE CYCLE — COMPLETE
====================================

MEMORY INVENTORY
  L1 Episodic .... <count>
  L2 Semantic .... <count>
  L3 Strategic ... <count>
  L4 Meta ........ <count>
  L5 Emergent .... <count>
  Total .......... <count>

CYCLE METRICS
  Avg Q-value ......... <value>
  Memories recalled ... <count>
  Memories rewarded ... <count>
  Promotions .......... <count>
  Emergent discoveries  <count>
  Skills extracted .... <count>
  Memories decayed .... <count>

HEALTH STATUS
  <health status from jmem_status>

====================================
```

If any step fails, log the error for that step and continue with the remaining steps. Include failures in the report under a WARNINGS section.

## When NOT to use this skill

- For individual memory operations (recall, remember, reward) use `/aussie-memory`
- For a broader evolution cycle that includes instinct updates and skill file generation, use `/aussie-evolve`
- For scheduled/recurring learning, use `/aussie-loop`
