# Aussie Evolve — Self-Learning & Memory Evolution

Full JMEM self-learning cycle: recall, reinforce, consolidate, meta-learn, synthesize, extract, decay, verify. Uses all 12 JMEM MCP tools to turn raw experience into crystallized knowledge.

## When the user invokes /aussie-evolve

Run the complete 8-step evolution cycle below. Every step uses native JMEM MCP tools — no CLI required.

### Step 1: Recall Relevant Memories (jmem_recall)

Sample memory across domains to assess what the system knows and where the gaps are.

```
mcp__jmem__jmem_recall(query="tool performance patterns", limit=10)
mcp__jmem__jmem_recall(query="recurring errors or failures", limit=10)
mcp__jmem__jmem_recall(query="successful strategies and principles", limit=10, min_q=0.7)
mcp__jmem__jmem_recall(query="phase execution preferences", limit=5)
```

Analyze the recalled results:
- **High-Q memories (Q > 0.8)** — validated knowledge, candidates for promotion
- **Low-Q memories (Q < 0.3)** — stale or wrong, candidates for decay
- **Gaps** — domains with few or no memories indicate blind spots

### Step 2: Auto-Reward Recalled Memories (jmem_reward_recalled)

Reinforce every memory that was just recalled in Step 1. This is a bulk reward — it assumes that memories surfaced during an evolution cycle are contextually relevant.

```
mcp__jmem__jmem_reward_recalled(reward=0.7)
```

If specific memories from Step 1 were clearly wrong or outdated, downgrade them individually:

```
mcp__jmem__jmem_reward(note_id="<id>", reward=-0.5, context="outdated pattern — no longer valid")
```

### Step 3: Consolidate (jmem_consolidate)

Link related memories via keyword clustering, auto-promote high-Q episodes to concepts, and merge near-duplicates.

```
mcp__jmem__jmem_consolidate()
```

This performs:
- Keyword-based linking across the Zettelkasten graph
- Promotion of L1 episodes to L2 concepts when Q > 0.8 and retrieval_count > 3
- Clustering of semantically similar memories (cosine similarity > 0.95)

### Step 4: Meta-Learning (jmem_meta_learn)

Analyze the learning process itself. Examines Q-value distribution, promotion velocity, keyword diversity, and reward patterns.

```
mcp__jmem__jmem_meta_learn()
```

Review the auto-stored META insights for:
- Whether promotion thresholds need adjustment
- Whether certain memory layers are starved or bloated
- Reward distribution skew (too generous or too harsh)

### Step 5: Emergent Synthesis (jmem_emergent)

Discover cross-cutting patterns across all memory layers. Finds keyword clusters, promotion chains, knowledge gaps, and graph density.

```
mcp__jmem__jmem_emergent()
```

Review the auto-stored EMERGENT discoveries for:
- Cross-domain principles that span multiple skills
- Structural patterns in how knowledge flows through layers
- Unexpected connections between previously unlinked memories

### Step 6: Extract Skills (jmem_extract_skills)

Auto-extract high-Q principles (Q >= 0.92, retrievals >= 5) into structured SKILL memories at L4. These represent crystallized, battle-tested knowledge.

```
mcp__jmem__jmem_extract_skills()
```

After extraction, scan `.claude/skills/` for all SKILL.md files:
1. Read each skill file
2. Check if referenced commands/tools still exist
3. If broken references found, rewrite to use working alternatives
4. If new extracted skills suggest a missing SKILL.md, draft one

Use `mcp__jmem__jmem_evolve` to mutate any memories whose content is outdated:

```
mcp__jmem__jmem_evolve(note_id="<id>", new_content="updated content reflecting current state")
```

### Step 7: Time-Decay Idle Memories (jmem_decay)

Apply time-based Q-decay to memories that have not been accessed recently. Prevents stale knowledge from clogging the promotion pipeline.

```
mcp__jmem__jmem_decay(hours_threshold=24)
```

This weakens memories that have been idle for 24+ hours, making room for fresher, more relevant knowledge to surface in recall.

### Step 8: Status Check & Verification (jmem_status + jmem_reflect)

Verify overall memory health after the evolution cycle.

```
mcp__jmem__jmem_status()
mcp__jmem__jmem_reflect()
```

Report the following to the user:
- Memory counts by level (L1 through L5)
- Average Q-value per level
- How many memories were promoted, decayed, or extracted
- Any warnings or anomalies from the reflect cycle

Store the evolution summary:

```
mcp__jmem__jmem_remember(
  content="Evolution cycle completed: [summary of promotions, extractions, decays, and insights]",
  level=3,
  keywords=["evolution", "self-learning", "cycle-report"],
  tags=["aussie-evolve"]
)
```

## JMEM Tools Used in This Cycle

| Step | Tool | Purpose |
|------|------|---------|
| 1 | `jmem_recall` | Search memory across domains |
| 2 | `jmem_reward_recalled` | Bulk-reinforce recalled memories |
| 2 | `jmem_reward` | Targeted reward/penalty for specific memories |
| 3 | `jmem_consolidate` | Link, promote, cluster memories |
| 4 | `jmem_meta_learn` | Analyze Q-distribution and learning dynamics |
| 5 | `jmem_emergent` | Discover cross-cutting patterns |
| 6 | `jmem_extract_skills` | Crystallize principles into L4 skills |
| 6 | `jmem_evolve` | Mutate outdated memory content |
| 7 | `jmem_decay` | Weaken idle memories |
| 8 | `jmem_status` | Health report (counts, Q-values, size) |
| 8 | `jmem_reflect` | Full cognitive cycle and summary |
| 8 | `jmem_remember` | Store evolution cycle report |

## Memory Growth Expectations

- **L1 Episodes** accumulate per tool execution
- **L2 Concepts** extracted when episodes cluster (every ~50 episodes, or when Q > 0.8)
- **L3 Principles** crystallize after ~3 evolution cycles
- **L4 Skills** emerge from validated L3 principles (Q >= 0.92, retrievals >= 5)
- **L5 Emergent** synthesized automatically by `jmem_emergent`

## What Makes This Different from /aussie-loop

- `/aussie-loop` runs warmup + learn (data collection phase)
- `/aussie-evolve` runs the full 8-step self-learning cycle (intelligence extraction)
- Run loop first to collect data, then evolve to extract knowledge
- Evolve is idempotent — safe to run repeatedly; decay and consolidation are incremental
