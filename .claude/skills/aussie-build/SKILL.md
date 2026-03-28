# Aussie Build — Self-Improvement

Run a self-improvement cycle where the PFAA engine analyzes and extends itself.

## When the user invokes /aussie-build

Execute the self-build cycle using Claude Code's native capabilities.

### Step 1: Introspect

Analyze the PFAA engine's own codebase:
```
1. Glob for all Python files in agent_setup_cli/core/
2. Glob for all TypeScript files in src/ and pfaa-cli/src/
3. Read each core module and assess:
   - Code quality (complexity, duplication, dead code)
   - Missing capabilities (tools that should exist but don't)
   - Performance bottlenecks (sync where async needed, missing caching)
   - Python 3.15 opportunities (PEP 695 type params, match/case, TaskGroup)
```

### Step 2: Diagnose

Run static analysis:
```bash
# TypeScript
cd pfaa-cli && npx tsc --noEmit 2>&1

# Python syntax
python3 -m py_compile agent_setup_cli/core/tools.py
python3 -m py_compile agent_setup_cli/core/memory.py
```

Review findings with JMEM context:
```
mcp__jmem__jmem_recall(query="self-build diagnosis previous")
```

### Step 3: Propose Improvements

For each finding, propose a specific change:
- New tool → define name, phase, input/output schema
- Bug fix → identify root cause and minimal fix
- Performance → measure before/after
- Python modernization → specific PEP reference

### Step 4: Implement (with --apply)

If the user passed `--apply` or confirms:
1. Write changes using Edit tool (prefer edits over full rewrites)
2. Run tests after each change
3. Revert if tests fail

Without `--apply`, produce a report only.

### Step 5: Learn

```
mcp__jmem__jmem_remember(content="Self-build cycle: [N] improvements proposed, [M] applied, [K] tests passed", level=2)
```

### Step 6: Evolve Skills

If new tools were created:
1. Create a new SKILL.md in `.claude/skills/` if warranted
2. Update `.claude/settings.json` to register it
3. Run /aussie-audit to verify everything is consistent

## Self-Build Report Format

```
SELF-BUILD CYCLE
=================
Modules analyzed: N
Issues found: N (critical: X, enhancement: Y, style: Z)
Improvements proposed: N
Applied: N (with --apply)
Tests: PASS/FAIL

PROPOSALS:
1. [Category] [File:Line] — [Description]
   Status: PROPOSED | APPLIED | SKIPPED
```

## Safety
- Never auto-apply without explicit user consent
- Always run tests after each change
- Keep a list of all changes for easy revert
- Store outcomes in JMEM for learning across cycles

## Fallback: Node.js CLI
```bash
cd pfaa-cli && npx tsx src/cli.ts self-build
cd pfaa-cli && npx tsx src/cli.ts self-build --apply
```
