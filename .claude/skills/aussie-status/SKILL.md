# Aussie Status — Full System Health

Show comprehensive PFAA engine status: bridge health, tool count, memory stats, agent count, skill count, hook count, and phase distribution.

## When the user invokes /aussie-status

Execute all diagnostic steps below and present a unified status report.

### Step 1: JMEM Memory Health

Run the JMEM diagnostic tools:
```
mcp__jmem__jmem_status()
mcp__jmem__jmem_reflect()
```

Extract from the results:
- Total memory count by layer (L1-L5)
- Average Q-value per layer
- Database size
- Last consolidation timestamp

### Step 2: Agent and Skill Census

Read the settings file to count registered components:
```
Read .claude/settings.json
```

Count and list:
- **Agents**: All entries under the `agents` key (name + description)
- **Skills**: All entries under the `skills` key (name + description)
- **Hooks**: Count hooks by event type (PreToolUse, PostToolUse, SessionStart, Stop, PreCompact, PostCompact)
- **MCP Servers**: All entries under `mcpServers`

### Step 3: Tool Inventory

Count tools by phase using the tool registry:
```bash
cd /Users/borris/Desktop/pfaa-engine/pfaa-cli && npx tsx src/cli.ts tools 2>/dev/null || echo "CLI unavailable"
```

If the CLI is unavailable, read the tool definitions directly:
```
Grep for phase definitions in agent_setup_cli/core/ and src/
```

Categorize tools into:
- **VAPOR** (async I/O) -- file reads, HTTP, DNS
- **LIQUID** (CPU-bound) -- grep, compute, hash
- **SOLID** (isolated) -- shell, git, docker, sandbox

### Step 4: Bridge Health Check

Test MCP connectivity:
```
mcp__jmem__jmem_status()
```

If this succeeds, bridge is healthy. If it fails, report MCP server as unreachable.

### Step 5: Present Report

Format output as:

```
PFAA ENGINE STATUS
==================
Bridge:     [HEALTHY|DEGRADED|OFFLINE]
MCP Server: jmem @ localhost:3100

Agents:     N registered
Skills:     N registered
Hooks:      N total (PreToolUse: X, PostToolUse: Y, SessionStart: Z, Stop: W, PreCompact: A, PostCompact: B)

Tools by Phase:
  VAPOR:  N tools (async I/O)
  LIQUID: N tools (CPU-bound)
  SOLID:  N tools (isolated)
  Total:  N tools

JMEM Memory:
  L1 Episodic:     N memories (avg Q: X.XX)
  L2 Semantic:     N memories (avg Q: X.XX)
  L3 Strategic:    N memories (avg Q: X.XX)
  L4 Meta-Learning: N memories (avg Q: X.XX)
  L5 Emergent:     N memories (avg Q: X.XX)
  Total:           N memories
  Database size:   X KB
```

## CLI Fallback

```bash
cd pfaa-cli && npx tsx src/cli.ts status
```
