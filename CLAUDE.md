# PFAA — Phase-Fluid Agent Architecture

## Project Overview

Enterprise AI agent framework with phase-fluid execution (VAPOR/LIQUID/SOLID), JMEM semantic memory (6 cognitive layers + Q-learning), and multi-agent team orchestration. All skills run natively in Claude Code — no external CLI required.

## Key Commands

```bash
# Claude Code slash commands (preferred — native execution)
/aussie-run "goal"          # Execute any goal with full agent stack
/aussie-build               # Self-improvement cycle
/aussie-evolve              # Memory cleanup + skill evolution
/aussie-audit               # System health check
/aussie-loop                # Learning cycle (warmup + learn)
/aussie-swarm "task"        # Parallel multi-agent dispatch
/aussie-memory              # JMEM memory operations
/aussie-analyze             # Python 3.15 code analysis

# Python team spawners
python3 agents/team/remix_spawn.py "goal"   # Full 10-agent team
python3 agents/team/spawn.py "goal"         # Basic 6-agent team

# Node.js CLI (fallback)
cd pfaa-cli && npx tsx src/cli.ts status
cd pfaa-cli && npx tsx src/cli.ts run "goal"

# JMEM MCP server
python3 -m jmem
```

## Architecture

```
pfaa-engine/
├── agent_setup_cli/core/    # Python PFAA engine (27+ tools, phase-fluid)
├── agents/team/             # Agent team spawners (spawn.py, remix_spawn.py)
├── pfaa-cli/                # Enterprise Node.js CLI (@pfaa/cli)
├── src/                     # TypeScript core (orchestrator, providers, memory)
├── jmem-mcp-server/         # JMEM semantic memory MCP server
├── freqtrade_strategy/      # Self-optimizing BTC FreqTrade strategy
└── .claude/                 # 10 agents, 13 skills, 6 hooks
```

## Claude Code Agents (10)

| Agent | Role | Phase |
|-------|------|-------|
| pfaa-lead | Orchestrates full team | VAPOR |
| aussie-researcher | Deep research & synthesis | VAPOR |
| aussie-planner | Goal decomposition & planning | VAPOR |
| aussie-architect | System design & ADRs | VAPOR |
| aussie-security | OWASP vulnerability audits | VAPOR |
| aussie-tdd | Test-first development | SOLID |
| pfaa-rewriter | Python 3.15 optimization | LIQUID |
| pfaa-validator | Read-only QA & validation | SOLID |
| aussie-deployer | Zero-downtime deployment | SOLID |
| aussie-docs | Documentation sync | VAPOR |

## Memory System

JMEM provides 6-layer cognitive memory with Q-learning reinforcement:
- **L1 Episodic** — Raw execution traces
- **L2 Semantic** — Extracted patterns (auto-promoted when Q > 0.8)
- **L3 Strategic** — Validated principles
- **L4 Skill** — Executable capabilities extracted from high-Q memories
- **L5 Meta-Learning** — Learning rate tuning and cross-task transfer
- **L6 Emergent** — Cross-agent knowledge synthesis and novel insights

MCP tools (13): `jmem_recall`, `jmem_remember`, `jmem_consolidate`, `jmem_reflect`, `jmem_reward`, `jmem_reward_recalled`, `jmem_evolve`, `jmem_status`, `jmem_decay`, `jmem_meta_learn`, `jmem_emergent`, `jmem_extract_skills`, `jmem_recall_cross`

## Hooks (6 event types)

- **SessionStart** — Aussie Agents banner
- **PostToolUse** — TypeScript type-check, console.log detection, Python 3.15 suggestions
- **PreToolUse** — Secret detection (blocks), sensitive file warnings
- **Stop** — Capability scan for unregistered skills/agents
- **PreCompact/PostCompact** — State preservation and compaction logging
