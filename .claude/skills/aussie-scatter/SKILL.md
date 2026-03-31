# Aussie Scatter — Parallel Fan-Out Execution

Fan-out a single task across multiple inputs in parallel using the Agent tool. Each sub-agent handles one input independently, then results are merged.

## When the user invokes /aussie-scatter

Parse the command for a task and a list of inputs. Format:
```
/aussie-scatter <task> <input1> <input2> ... <inputN>
```

Examples:
```
/aussie-scatter "analyze code quality" src/core/ src/tools/ src/memory/
/aussie-scatter "find security issues" auth.py crypto.py session.py
/aussie-scatter "grep for TODO" "TODO" "FIXME" "HACK" "XXX"
```

### Step 1: Parse Inputs

Extract:
- **Task**: The operation to perform on each input
- **Inputs**: The list of items to fan out across
- **Options**: Any flags (--merge-strategy, --max-parallel)

If fewer than 2 inputs are provided, ask the user for more inputs or suggest splitting the task.

### Step 2: Spawn Parallel Sub-Agents

Use the Agent tool to spawn one sub-agent per input. All sub-agents run in parallel:

```
For each input in inputs:
  Agent(
    prompt="Execute the following task on the given input. Return structured results.
    Task: {task}
    Input: {input}

    Return your results in this format:
    INPUT: {input}
    STATUS: SUCCESS|FAILURE
    RESULT: <your findings>
    DURATION: <time taken>"
  )
```

Important:
- Launch ALL Agent calls simultaneously (do not wait for one to finish before starting the next)
- Each sub-agent is independent and should not reference other sub-agents' work
- Set a reasonable timeout per sub-agent (default: 60 seconds)

### Step 3: Collect Results

As each sub-agent completes, collect its output. Track:
- Which inputs succeeded
- Which inputs failed (and why)
- Duration per input

### Step 4: Merge Results

Combine all sub-agent outputs into a unified report. Merge strategies:
- **concat** (default): Concatenate all results in input order
- **dedupe**: Remove duplicate findings across inputs
- **summary**: Synthesize a single summary from all results

### Step 5: Present Report

```
SCATTER RESULTS
================
Task:    "{task}"
Inputs:  N total (M succeeded, K failed)
Strategy: {merge_strategy}

--- Input 1: {input1} ---
STATUS: SUCCESS
{result1}

--- Input 2: {input2} ---
STATUS: SUCCESS
{result2}

...

MERGED SUMMARY
--------------
{merged findings across all inputs}

Timing: Total {X}ms, Avg {Y}ms/input, Max {Z}ms
```

### Step 6: Store in Memory

```
mcp__jmem__jmem_remember(
  content="Scatter: '{task}' across {N} inputs. {M} succeeded, {K} failed. Avg time: {Y}ms",
  level=1,
  tags=["scatter", "parallel-execution"]
)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| task | *required* | The operation to perform on each input |
| inputs | *required* | Space-separated list of inputs |
| --merge | concat | Merge strategy: concat, dedupe, summary |
| --max-parallel | 8 | Maximum concurrent sub-agents |

## CLI Fallback

```bash
cd pfaa-cli && npx tsx src/cli.ts scatter grep "TODO" "FIXME" "HACK"
```
