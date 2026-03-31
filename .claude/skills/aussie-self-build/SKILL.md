---
name: aussie-self-build
description: Automated self-improvement cycle — recall JMEM principles, identify unapplied patterns, apply changes, test, commit, reward
---

# Aussie Self-Build — Automated Self-Improvement

Runs a complete self-build cycle: recall learned patterns from JMEM, identify which ones aren't yet applied to the codebase, apply the improvements, test, commit, and reinforce the memories that led to successful changes.

## Cycle Steps

1. **Recall**: Query JMEM for principles tagged with "claude-code-pattern" or high-Q (>0.7) principles
2. **Analyze**: For each principle, check if it's already applied to the codebase
3. **Plan**: Select the top 3 unapplied patterns with highest Q-values
4. **Apply**: Dispatch parallel agents to implement each improvement
5. **Test**: Run `python3 -m pytest tests/test_cortex.py -v`
6. **Commit**: Git commit with self-build message
7. **Reward**: `jmem_reward_recalled` with +0.9 for successful applications
8. **Consolidate**: Run `jmem_consolidate` to link new memories

## Usage

Invoked automatically by the cortex dream cycle (Phase B `suggest_self_improvements`), or manually:
```
/aussie-build
```

## When the user invokes /aussie-self-build (or auto-routed via "self-build/improve/enhance")

Execute the full automated self-improvement cycle below. No user confirmation needed between steps — run end to end.

### Step 1: Recall High-Q Principles

```
mcp__jmem__jmem_recall(query="claude-code-pattern self-improvement principle", top_k=20)
```

Filter results to only those with Q-value > 0.7. If the JMEM server is unavailable, fall back to reading known patterns from `.claude/skills/` and `agent_setup_cli/core/`.

### Step 2: Analyze Codebase Against Principles

For each recalled principle:
1. Read the relevant target files (Glob + Read)
2. Check if the principle is already applied
3. Score applicability: HIGH (clear gap), MEDIUM (partial), LOW (already done)

Build a list of unapplied principles sorted by Q-value descending.

### Step 3: Plan Top 3 Improvements

Select the top 3 unapplied patterns with highest Q-values. For each one:
- Identify the target file(s) — max 3 files per pattern
- Define the specific change to make
- Estimate risk: LOW (additive), MEDIUM (modifies existing), HIGH (structural)

Skip any HIGH-risk changes. If fewer than 3 qualify, proceed with what's available.

### Step 4: Apply via Parallel Agents

For each unapplied pattern, spawn a focused agent:
```
Agent(prompt="Self-build: apply [pattern name] to [target file]. Read the file first. Make minimal changes. Add tests if appropriate. Run tests.")
```

Use the Parallel Self-Build Pattern (JMEM SKILL, Q=0.8):
- Spawn agents simultaneously (one per improvement)
- Each targets different files (no conflicts)
- Each agent must Read before Write/Edit

If parallel dispatch is unavailable, apply sequentially.

### Step 5: Test

Run the test suite after all agents complete:
```bash
python3 -m pytest tests/test_cortex.py -v
```

If tests fail:
1. Identify which change caused the failure
2. Revert that specific change (git checkout the affected file)
3. Re-run tests to confirm the revert fixed it
4. Mark that pattern as "failed" for negative reward

### Step 6: Commit

If any improvements were successfully applied and tests pass:
```bash
git add -A
git commit -m "feat(self-build): apply [N] JMEM patterns — [brief description of changes]"
```

Each improvement should ideally be an atomic commit. If multiple succeed, commit them together with a summary message.

### Step 7: Reward

For each principle that was successfully applied:
```
mcp__jmem__jmem_reward_recalled(query="[principle content]", reward=0.9)
```

For each principle that failed:
```
mcp__jmem__jmem_reward_recalled(query="[principle content]", reward=-0.3)
```

### Step 8: Consolidate

Link new memories and promote high-Q patterns:
```
mcp__jmem__jmem_consolidate()
mcp__jmem__jmem_remember(content="Self-build cycle: [N] patterns recalled, [M] applied, [K] tests passed, [F] failed", level=2)
```

## Zero-Pattern Handling

If Step 2 finds 0 unapplied patterns:
1. Output "System is up to date — all recalled patterns are applied"
2. Run `mcp__jmem__jmem_consolidate()` to strengthen existing links
3. Run `mcp__jmem__jmem_evolve()` to check for emergent patterns
4. Exit cleanly

## Self-Build Report Format

```
AUTOMATED SELF-BUILD CYCLE
============================
Principles recalled:  N (Q > 0.7)
Already applied:      N
Unapplied (planned):  N
Successfully applied: N
Failed (reverted):    N
Tests:                PASS/FAIL

APPLIED:
1. [Pattern] → [File] — [Change summary] (Q=X.XX → rewarded +0.9)
2. ...

FAILED:
1. [Pattern] → [File] — [Error reason] (Q=X.XX → penalized -0.3)

SKIPPED (high risk):
1. [Pattern] — [Risk reason]
```

## Safety Rules

- Never skip tests — if tests fail, revert the change
- Never modify more than 3 files per agent
- Always read before writing
- Commit each improvement separately when possible (atomic commits)
- Skip HIGH-risk structural changes — only LOW and MEDIUM risk
- If 0 unapplied patterns found, output "System is up to date" and run jmem_consolidate only
- Never modify `.claude/settings.json` or hook files during self-build
- Never delete files — only add or edit

## Agent Dispatch Pattern

Each agent receives a focused prompt:
```
Self-build: apply "[pattern name]" to [target file].
1. Read the file first
2. Make minimal, targeted changes
3. Add a test if the change is testable
4. Run: python3 -m pytest tests/test_cortex.py -v
5. If tests fail, revert your changes
```

Agents target different files to avoid merge conflicts. If two patterns target the same file, serialize them (apply one, commit, then the other).
