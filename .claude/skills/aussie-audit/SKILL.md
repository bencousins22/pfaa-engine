# Aussie Audit — Self-Assessment

Comprehensive audit of the Aussie Agents system for reliability and completeness.

## When the user invokes /aussie-audit

Run all checks below and produce a structured report.

### 1. Skill Registration Audit

```
Glob for .claude/skills/*/SKILL.md to find all skill directories.
Read .claude/settings.json and compare registered skills vs actual skill files.
Flag: unregistered skills, registered skills with missing files.
```

### 2. Agent Registration Audit

```
Glob for .claude/agents/*.md to find all agent specs.
Read .claude/settings.json and compare registered agents vs actual agent files.
Flag: unregistered agents, registered agents with missing files.
```

### 3. Hook Health Check

```
Read .claude/settings.json hooks section.
Verify each hook command is syntactically valid (parse the node -e scripts).
Check for: hardcoded paths that may be stale, missing matchers, unreasonable timeouts.
```

### 4. JMEM Memory Health

```
Use mcp__jmem__jmem_status to check:
- Total memory count across all layers
- Average Q-value (healthy > 0.5)
- Layer distribution (L1 should be largest, L4 smallest)
- Connection status
```

### 5. TypeScript Compilation

```bash
cd pfaa-cli && npx tsc --noEmit 2>&1
```
Flag any type errors.

### 6. Python Syntax Validation

```bash
python3 -m py_compile agent_setup_cli/core/tools.py
python3 -m py_compile agent_setup_cli/core/memory.py
python3 -m py_compile agent_setup_cli/core/framework.py
python3 -m py_compile agents/team/spawn.py
python3 -m py_compile agents/team/remix_spawn.py
```

### 7. Bridge & MCP Server Check

```bash
python3 -c "import jmem; print('JMEM module OK')" 2>&1
```
Verify the JMEM MCP server can be imported.

### 8. Broken Reference Scan

For each skill SKILL.md:
- Extract all `npx tsx src/cli.ts <command>` references
- Verify each command exists in pfaa-cli/src/cli.ts
- Flag commands that don't exist

### Report Format

```
AUSSIE AUDIT REPORT
====================
Skills:     X/Y registered (Z unregistered)
Agents:     X/Y registered (Z unregistered)
Hooks:      X active, Y issues
Memory:     X total, avg Q=Y.YY, status=OK/WARN/DOWN
TypeScript: PASS/FAIL (N errors)
Python:     PASS/FAIL (N errors)
JMEM MCP:   OK/DOWN
References: X broken out of Y total

ISSUES:
- [CRITICAL] ...
- [WARNING] ...
- [INFO] ...
```

### Pass Criteria
- All skills and agents registered
- No broken command references
- TypeScript compiles clean
- Python syntax valid
- Memory avg Q > 0.5
- JMEM MCP reachable
