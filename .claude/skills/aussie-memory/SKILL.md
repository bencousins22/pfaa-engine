# Aussie Memory — JMEM Operations

Manage the 5-layer JMEM semantic memory system using 12 native MCP tools. All operations run directly in Claude Code — no CLI required.

## When the user invokes /aussie-memory

Ask what operation they need, or run `jmem_status` to show current health. For a full learning cycle, point them to `/aussie-evolve`.

## JMEM MCP Tools (12)

### Core Read/Write

#### jmem_recall — Search Memory
Search JMEM semantic memory using TF-IDF + BM25 + Q-boost hybrid search with Zettelkasten graph traversal.

```
mcp__jmem__jmem_recall(query="database optimization", limit=10, min_q=0.5, level=2)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *required* | Search query |
| `limit` | integer | 5 | Max results |
| `min_q` | number | 0 | Minimum Q-value threshold |
| `level` | integer | — | Filter by layer (1=episode, 2=concept, 3=principle, 4=skill) |

#### jmem_remember — Store Memory
Store a memory at a cognitive level with optional keywords and tags.

```
mcp__jmem__jmem_remember(content="Pattern: always validate input before DB write", level=2, keywords=["validation", "database"], tags=["best-practice"])
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `content` | string | *required* | Memory content |
| `level` | integer | 1 | Cognitive level (1=episode, 2=concept, 3=principle, 4=skill) |
| `context` | string | — | Contextual metadata |
| `keywords` | string[] | — | Keywords for indexing |
| `tags` | string[] | — | Tags for categorization |

#### jmem_evolve — Mutate Memory Content
Update a memory's content while preserving its metadata, Q-value, and graph links.

```
mcp__jmem__jmem_evolve(note_id="abc123", new_content="updated pattern reflecting current state")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `note_id` | string | *required* | Memory ID to evolve |
| `new_content` | string | *required* | Updated content |

### Reinforcement Learning

#### jmem_reward — Targeted Reward/Penalty
Reinforce or weaken a specific memory via Q-learning.

```
mcp__jmem__jmem_reward(note_id="abc123", reward=0.8, context="led to successful deployment")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `note_id` | string | *required* | Memory ID to reinforce |
| `reward` | number | *required* | Signal from -1 (weaken) to 1 (strengthen) |
| `context` | string | — | Reward context |

#### jmem_reward_recalled — Bulk Auto-Reward
Reinforce all memories that were recently recalled. Call after successful task completion.

```
mcp__jmem__jmem_reward_recalled(reward=0.7)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `reward` | number | 0.7 | Reward signal (0-1) |

#### jmem_decay — Time-Based Q-Decay
Apply Q-decay to memories idle beyond a threshold. Prevents stale knowledge from blocking the promotion pipeline.

```
mcp__jmem__jmem_decay(hours_threshold=24)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hours_threshold` | number | 24 | Hours of inactivity before decay |

### Knowledge Synthesis

#### jmem_consolidate — Link, Promote, Cluster
Link related memories via keyword clustering, auto-promote high-Q episodes to concepts, and merge near-duplicates.

```
mcp__jmem__jmem_consolidate()
```

No parameters. Runs linking, promotion, and deduplication in one pass.

#### jmem_meta_learn — L4 Meta-Learning
Analyze the learning process itself: Q-distribution, promotion velocity, keyword diversity, reward patterns. Auto-stores insights as META memories.

```
mcp__jmem__jmem_meta_learn()
```

No parameters. Results stored automatically at L4.

#### jmem_emergent — L5 Emergent Synthesis
Discover cross-cutting patterns across all layers: keyword clusters, promotion chains, knowledge gaps, graph density. Auto-stores discoveries as EMERGENT memories.

```
mcp__jmem__jmem_emergent()
```

No parameters. Results stored automatically at L5.

#### jmem_extract_skills — Crystallize Skills from Principles
Auto-extract high-Q principles (Q >= 0.92, retrievals >= 5) into structured SKILL memories at L4.

```
mcp__jmem__jmem_extract_skills()
```

No parameters. Only promotes principles that meet both the Q and retrieval thresholds.

### Diagnostics

#### jmem_status — Health Report
Get memory counts by level, average Q-value, and database size.

```
mcp__jmem__jmem_status()
```

No parameters.

#### jmem_reflect — Full Cognitive Cycle
Run statistics, health assessment, and knowledge summary in a single pass.

```
mcp__jmem__jmem_reflect()
```

No parameters.

## Memory Layers

| Layer | Name | What It Stores | Promotion Trigger |
|-------|------|---------------|-------------------|
| L1 | Episodic | Raw execution traces | Auto-created per tool run |
| L2 | Semantic | Statistical patterns per tool | Q > 0.8, retrievals > 3 (via consolidate) |
| L3 | Strategic | Phase optimization strategies | ~3 evolution cycles |
| L4 | Meta-Learning | Learning rate tuning | Via meta_learn / extract_skills |
| L5 | Emergent | Cross-agent knowledge synthesis | Via emergent synthesis |

## CLI Fallback

The Node.js CLI is available as a fallback if MCP tools are unavailable:

```bash
cd pfaa-cli && npx tsx src/cli.ts memory stats        # Status with bar charts
cd pfaa-cli && npx tsx src/cli.ts memory recall "query" # Search memory
cd pfaa-cli && npx tsx src/cli.ts memory consolidate   # Consolidate
cd pfaa-cli && npx tsx src/cli.ts memory dump          # Full JSON dump
cd pfaa-cli && npx tsx src/cli.ts learn                # Learning cycle
```

Prefer the MCP tools above — they are faster and run natively in Claude Code.
