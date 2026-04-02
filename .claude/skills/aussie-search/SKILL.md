# Aussie Search — Tool and Capability Search

Search for tools by name, description, phase, or capability. Inspect tool registries and display results with phase and capability information.

## When the user invokes /aussie-search

Parse the command for a search query. Format:
```
/aussie-search "query"
/aussie-search "file" --phase VAPOR
/aussie-search "git" --type mcp
```

### Step 1: Search Tool Registries

Search across all tool definition sources:

#### Python Tools (agent_setup_cli/core/)
```
Grep for tool definitions in agent_setup_cli/core/
Look for function definitions, tool registrations, and phase annotations
```

#### TypeScript Tools (src/ and pfaa-cli/src/)
```
Grep for tool definitions in src/
Grep for tool definitions in pfaa-cli/src/
Look for tool registrations, command definitions, and phase annotations
```

#### MCP Tools (JMEM)
```
Read .claude/settings.json for mcpServers
List known MCP tools: jmem_recall, jmem_remember, jmem_consolidate, jmem_reflect,
  jmem_reward, jmem_reward_recalled, jmem_decay, jmem_evolve, jmem_meta_learn,
  jmem_emergent, jmem_extract_skills, jmem_status, jmem_recall_cross
```

#### Claude Code Native Tools
```
Built-in tools: Read, Write, Edit, Glob, Grep, Bash, Agent, ToolSearch
```

#### Skills and Agents
```
Read .claude/settings.json
List all registered skills and agents as searchable capabilities
```

### Step 2: Filter Results

Apply filters based on the query:
- **Name match**: Tool name contains the query string (case-insensitive)
- **Description match**: Tool description contains the query string
- **Phase filter**: If --phase is specified, only show tools in that phase
- **Type filter**: If --type is specified, only show tools of that type (python, typescript, mcp, native, skill, agent)

### Step 3: Enrich Results

For each matching tool, gather:
- **Name**: Tool identifier
- **Phase**: VAPOR, LIQUID, or SOLID
- **Type**: python, typescript, mcp, native, skill, or agent
- **Description**: What the tool does
- **Source**: File path where the tool is defined
- **Parameters**: Input parameters (if available)

### Step 4: Present Results

```
SEARCH RESULTS: "{query}"
===========================
Found {N} matches

  Name                Phase    Type         Description
  ----                -----    ----         -----------
  file_read           VAPOR    python       Read file contents
  jmem_recall         VAPOR    mcp          Search JMEM semantic memory
  grep_search         LIQUID   native       Search file contents with regex
  ...

PHASE DISTRIBUTION
  VAPOR:  {X} tools
  LIQUID: {Y} tools
  SOLID:  {Z} tools

Type /aussie-status for full system overview.
```

If no results are found:
```
No tools found matching "{query}".
Suggestions:
- Try a broader search term
- Use /aussie-status to see all registered tools
- Check available phases: VAPOR, LIQUID, SOLID
```

### Step 5: Detailed View

If only 1-3 results are found, automatically show detailed info:

```
TOOL: jmem_recall
  Phase:       VAPOR
  Type:        MCP (jmem server)
  Description: Search JMEM semantic memory using TF-IDF + BM25 + Q-boost
  Source:      jmem-mcp-server/jmem/
  Parameters:
    query    (string, required)  — Search query
    limit    (integer, default 5) — Max results
    min_q    (number, default 0) — Minimum Q-value
    level    (integer, optional) — Filter by layer
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| query | *required* | Search term (name, description, or capability) |
| --phase | all | Filter by phase: VAPOR, LIQUID, SOLID |
| --type | all | Filter by type: python, typescript, mcp, native, skill, agent |
| --detailed | auto | Show full parameter info (auto-enabled for 1-3 results) |

## CLI Fallback

```bash
cd pfaa-cli && npx tsx src/cli.ts tool-search "query"
cd pfaa-cli && npx tsx src/cli.ts tools
```
