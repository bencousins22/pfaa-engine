# PFAA — Phase-Fluid Agent Architecture

## Project Overview

Enterprise AI agent framework with phase-fluid execution (VAPOR/LIQUID/SOLID), JMEM semantic memory (5 cognitive layers + Q-learning), and multi-agent team orchestration.

## Key Commands

```bash
# Spawn full remix agent team (all 10 roles, all capabilities)
python3 agents/team/remix_spawn.py "goal"

# Spawn basic 6-agent team
python3 agents/team/spawn.py "goal"

# Node.js CLI
cd pfaa-cli && npx tsx src/cli.ts status
cd pfaa-cli && npx tsx src/cli.ts run "goal"
cd pfaa-cli && npx tsx src/cli.ts py315 analyze <file>

# JMEM MCP server
python3 -m jmem_mcp_server.jmem.server

# FreqTrade BTC optimization
python3 agents/team/spawn.py --freqtrade
```

## Architecture

```
pfaa-engine/
├── agent_setup_cli/core/    # Python 3.15 PFAA engine (27+ tools)
├── agents/team/             # Agent team spawners (spawn.py, remix_spawn.py)
├── pfaa-cli/                # Enterprise Node.js CLI (@pfaa/cli)
├── jmem-mcp-server/         # JMEM semantic memory MCP server
├── freqtrade_strategy/      # Self-optimizing BTC FreqTrade strategy
└── .claude/                 # Claude Code agents, skills, hooks
```

## Agent Team Roles

Lead, Researcher, Strategist, Optimizer, Validator, Risk Manager, Deployer, Rewriter, Modernizer, Skill Writer

## Memory System

JMEM provides 5-layer cognitive memory: Episode → Concept → Principle → Skill. Knowledge promotes automatically via Q-learning reinforcement. Shared across all agents in the team.

## Python 3.15 Features

- `lazy import` (PEP 810) — deferred module loading
- `frozendict` (PEP 814) — immutable hashable dicts
- `kqueue` subprocess — kernel event queues on macOS
- Free-threading — GIL-free execution
