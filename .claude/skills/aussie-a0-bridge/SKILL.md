---
name: aussie-a0-bridge
description: Bridge between PFAA Aussie Agents and Agent Zero v1.5+ — plugin creation, A2A communication, memory sync, and tool interop
---

# Aussie A0 Bridge — Agent Zero Integration

Connect PFAA's 10 Aussie Agents with Agent Zero v1.5+ for cross-framework orchestration.

## Capabilities

### 1. Create A0 Plugin from PFAA Skill

Convert any Aussie skill into an Agent Zero plugin:

```bash
# Structure mapping
.claude/skills/{skill}/SKILL.md  ->  usr/plugins/{skill}/plugin.yaml + tools/
```

**Steps:**
1. Read the PFAA skill's SKILL.md
2. Generate plugin.yaml manifest:
   ```yaml
   name: pfaa_{skill_name}
   title: "PFAA: {Skill Title}"
   description: "{skill description}"
   version: 1.0.0
   settings_sections:
     - agent
   ```
3. Create tool implementation in tools/ that calls the PFAA skill via subprocess or A2A
4. Create prompts/ with the skill's instructions adapted for A0's prompt format
5. Test with `python execute.py` in A0's Docker container

### 2. A2A Communication (Agent-to-Agent)

Enable bidirectional communication between Claude Code agents and Agent Zero:

**A0 -> PFAA:**
- A0 exposes A2A server (Settings -> MCP/A2A -> A0 A2A Server)
- PFAA agents connect via MCP client to A0's A2A endpoint
- Use jmem_remember to store A0 findings in PFAA's memory

**PFAA -> A0:**
- Call A0's API endpoint: `POST http://localhost:PORT/api/agent`
- Send task with context from JMEM recall
- Parse A0's response and store as JMEM episode

### 3. Memory Sync

Synchronize knowledge between JMEM (6-layer) and A0's VectorDB:

| JMEM Level | A0 Equivalent |
|---|---|
| L1 Episode | Conversation Fragment |
| L2 Concept | Memory (tagged) |
| L3 Principle | Solution |
| L4 Skill | Custom Knowledge (.md file) |
| L5 Meta | Behavior Rule |
| L6 Emergent | Cross-agent Knowledge |

**Export JMEM -> A0:**
```python
# Recall high-Q memories and write as A0 knowledge files
memories = await engine.recall("*", limit=50, min_q=0.7)
for m in memories:
    path = f"/a0/knowledge/custom/pfaa/{m.id}.md"
    write(path, f"# {m.level.name}\n\n{m.content}\n\nQ-value: {m.q_value}")
```

**Import A0 -> JMEM:**
```python
# Read A0 memory entries and store as JMEM episodes
for entry in a0_memories:
    await engine.remember(
        content=entry["content"],
        level=MemoryLevel.EPISODE,
        tags=["agent-zero", "imported"],
    )
```

### 4. Tool Interop

Map PFAA's 44 tools to A0's tool system:

| PFAA Tool | A0 Equivalent | Bridge |
|---|---|---|
| shell (SOLID) | code_execution_tool | Direct — both execute commands |
| read_file | File browser API | A0 API call |
| web_fetch | search_engine (SearXNG) | A0's SearXNG is more privacy-focused |
| jmem_recall | memory_tool (load) | Memory sync bridge |
| jmem_remember | memory_tool (save) | Memory sync bridge |

### 5. A0 Plugin for PFAA Cortex

Create an A0 plugin that exposes the cortex as a tool inside Agent Zero:

```yaml
# plugin.yaml
name: pfaa_cortex
title: PFAA Cortex Bridge
description: Access PFAA's RL cortex, JMEM memory, and 10 specialized agents from Agent Zero
version: 1.0.0
```

Tool implementation:
```python
# tools/pfaa_cortex.py
class PFAACortex(Tool):
    async def execute(self, agent, task):
        # Call cortex via subprocess
        result = subprocess.run(
            ["python3", CORTEX_PATH, "SubagentStart"],
            input=json.dumps({"agent_type": agent, "task": task}),
            capture_output=True, text=True
        )
        return result.stdout
```

## Setup

1. Ensure Agent Zero is running (Docker or local)
2. Enable A2A server in A0 Settings
3. Configure A0 URL in PFAA: `export A0_URL=http://localhost:PORT`
4. Run: `/aussie-a0-bridge setup`

## Usage

```
/aussie-a0-bridge sync-memory     # Sync JMEM <-> A0 VectorDB
/aussie-a0-bridge create-plugin   # Convert PFAA skill to A0 plugin
/aussie-a0-bridge a2a-test        # Test A2A communication
/aussie-a0-bridge status          # Check A0 connection status
```
