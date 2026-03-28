# Aussie Run — Goal Execution

Execute a natural language goal using the Aussie Agents engine.

## Usage

When the user asks to run a goal, task, or objective:

```bash
cd pfaa-cli && npx tsx src/cli.ts run "the user's goal here"
```

With live Claude API:
```bash
cd pfaa-cli && npx tsx src/cli.ts run --live "the user's goal here"
```

## What It Does

1. Decomposes the goal into subtasks
2. Assigns specialist agents (analyzer, refactorer, tester, etc.)
3. Executes tasks in parallel where possible
4. Recalls relevant JMEM memories before each task
5. Learns from results (L1→L2→L3 promotion)
6. Returns a pipeline summary with success/failure per agent

## Options

- `--live` — Use real Claude API (requires ANTHROPIC_API_KEY)
- `--roles <roles>` — Comma-separated agent roles to use
- `--dry-run` — Show plan without executing
