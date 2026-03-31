# Aussie Explore — Epsilon-Greedy Phase Exploration

Run epsilon-greedy phase exploration to self-optimize tool execution strategies. This is the core self-optimization loop that discovers which phases perform best for each tool.

## When the user invokes /aussie-explore

Execute the exploration cycle below. Accept an optional epsilon parameter (default 0.3 = 30% random exploration, 70% exploitation of known-best phases).

### Step 1: Recall Current Knowledge

Query JMEM for existing phase performance data:
```
mcp__jmem__jmem_recall(query="phase performance tool execution timing", limit=20, min_q=0.3)
```

Build a map of known tool-phase performance from recalled memories.

### Step 2: Select Exploration Targets

Choose 5-10 tools to explore. For each tool, apply epsilon-greedy selection:
- With probability epsilon (default 0.3): **Explore** -- pick a random phase (VAPOR, LIQUID, or SOLID)
- With probability 1-epsilon (default 0.7): **Exploit** -- pick the phase with the best known performance

Tools to explore include common operations:
- File operations (read, write, glob, grep)
- Shell commands (ls, git status, find)
- Compute operations (hash, parse, transform)
- Network operations (if available)

### Step 3: Execute Trials

For each selected tool-phase combination, run a timed execution:

```bash
# Example: time a file read in VAPOR phase
time_start=$(date +%s%N)
# ... execute the tool ...
time_end=$(date +%s%N)
elapsed=$(( (time_end - time_start) / 1000000 ))  # milliseconds
```

Record for each trial:
- Tool name
- Phase used
- Execution time (ms)
- Success/failure
- Output size

### Step 4: Reward/Penalize

For each trial result, compute a reward signal and store it:

```
# Fast execution = positive reward, slow = negative
# Scale: -1 (terrible) to +1 (excellent)
mcp__jmem__jmem_remember(
  content="Tool [name] in [phase]: [time]ms, [success/fail]",
  level=1,
  tags=["exploration", "phase-trial"]
)
```

If a trial beat the previous best for that tool:
```
mcp__jmem__jmem_reward(note_id="[best_memory_id]", reward=0.8, context="new best phase discovered")
```

If a trial was slower than average:
```
mcp__jmem__jmem_reward(note_id="[slow_memory_id]", reward=-0.3, context="underperforming phase")
```

### Step 5: Consolidate Learnings

After all trials complete:
```
mcp__jmem__jmem_consolidate()
```

This will auto-promote high-Q episodes (Q > 0.8) to L2 semantic patterns.

### Step 6: Present Results

Format output as:

```
EXPLORATION RESULTS (epsilon=0.30)
===================================
Trials: N total (M explored, K exploited)

Tool             Phase    Time(ms)  Result   Reward
-----------      ------   -------   ------   ------
file_read        VAPOR    12ms      OK       +0.8
shell_exec       SOLID    45ms      OK       +0.2
grep_search      LIQUID   8ms       OK       +0.9
...

Discoveries:
- [tool] performs 2.3x faster in [phase] than [other_phase]
- [tool] fails in [phase] but succeeds in [other_phase]

Memories updated: N new, M rewarded, K penalized
Consolidation: N promotions, M links created
```

### Step 7: Store Meta-Learning

```
mcp__jmem__jmem_remember(
  content="Exploration cycle: N trials, M discoveries, epsilon=0.30, best_phase_distribution={VAPOR: X, LIQUID: Y, SOLID: Z}",
  level=2,
  tags=["exploration-summary", "meta"]
)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| epsilon | 0.3 | Exploration rate (0=pure exploit, 1=pure explore) |
| trials | 10 | Number of tool-phase combinations to test |
| --verbose | false | Show detailed timing for each trial |

## CLI Fallback

```bash
cd pfaa-cli && npx tsx src/cli.ts explore
cd pfaa-cli && npx tsx src/cli.ts explore --epsilon 0.5
```
