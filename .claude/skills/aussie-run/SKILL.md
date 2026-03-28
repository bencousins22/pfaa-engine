# Aussie Run — Goal Execution

Execute a natural language goal using the full Aussie Agents capability stack.

## When the user invokes /aussie-run [goal]

Execute the goal directly using Claude Code's native capabilities — agents, tools, and JMEM memory.

### Step 1: Recall Context

```
Use mcp__jmem__jmem_recall(query="<goal keywords>") to check for:
- Prior attempts at similar goals
- Relevant learned patterns (L2+)
- Known risks or blockers
```

### Step 2: Decompose the Goal

Break the goal into subtasks. For each subtask, determine:
- **What**: Clear description of the work
- **Who**: Which agent or tool handles it
- **Phase**: VAPOR (I/O), LIQUID (CPU), or SOLID (isolated)
- **Dependencies**: What must complete first

### Step 3: Execute Subtasks

For each subtask, use the appropriate approach:

- **Code analysis** → Use Glob, Grep, Read directly
- **Code changes** → Use Edit, Write with proper testing
- **Research** → Use Agent(subagent_type=Explore) or WebSearch
- **Testing** → Run pytest/vitest via Bash
- **Memory ops** → Use JMEM MCP tools (jmem_recall, jmem_remember, etc.)
- **Complex multi-step** → Spawn Agent workers for parallel execution

### Step 4: Learn from Results

After each subtask completes:
```
Use mcp__jmem__jmem_remember(content="Task: <task>, Result: <outcome>, Success: <bool>", level=1)
```

For the overall goal:
```
Use mcp__jmem__jmem_reward(query="<goal>", reward=<0.0-1.0>) to reinforce successful patterns
```

### Step 5: Report

Produce a pipeline summary:
```
GOAL: [original goal]
STATUS: COMPLETE | PARTIAL | FAILED

Tasks:
  [1] [task] — OK (agent: [who], phase: [phase])
  [2] [task] — OK
  [3] [task] — FAILED: [reason]

Memories stored: N
Patterns reinforced: N
```

## Options (passed as arguments)

- `--dry-run` — Show the decomposition plan without executing
- `--roles <roles>` — Limit to specific agent roles (comma-separated)
- `--parallel` — Execute independent subtasks in parallel via Agent workers

## Fallback: Node.js CLI

If native execution isn't suitable, fall back to:
```bash
cd pfaa-cli && npx tsx src/cli.ts run "the goal"
cd pfaa-cli && npx tsx src/cli.ts run --live "the goal"
```
