# PFAA — Phase-Fluid Agent Architecture

## Project Overview

Enterprise AI agent framework with phase-fluid execution (VAPOR/LIQUID/SOLID), JMEM semantic memory (6 cognitive layers + Q-learning), and multi-agent team orchestration. All skills run natively in Claude Code — no external CLI required.

## Automatic Skill Routing

**IMPORTANT**: When the user makes a request, automatically invoke the matching skill WITHOUT requiring them to type a slash command. Use this routing table:

| User says something like... | Invoke |
|---|---|
| "run/do/execute/build [goal]" | `/aussie-run` |
| "swarm/parallel/fan-out [task]" | `/aussie-swarm` |
| "scatter [tool] across [inputs]" | `/aussie-scatter` |
| "pipeline/chain/sequence [steps]" | `/aussie-pipeline` |
| "spawn team/full team/all agents" | `/pfaa-team` |
| "generate/create/write code for [X]" | `/aussie-generate` |
| "self-build/improve/enhance itself" | `/aussie-self-build` |
| "learn/consolidate/cognitive cycle" | `/aussie-learn` |
| "evolve/cleanup memory/skill evolution" | `/aussie-evolve` |
| "explore/optimize phases" | `/aussie-explore` |
| "status/health/how is the system" | `/aussie-status` |
| "audit/benchmark/test performance" | `/aussie-bench` |
| "warmup/profile tools" | `/aussie-warmup` |
| "memory/recall/remember/jmem" | `/aussie-memory` |
| "analyze python/py315/modernize" | `/aussie-analyze` |
| "search tools/find tool" | `/aussie-search` |
| "ask/question/what is/how does" | `/aussie-ask` |
| "save checkpoint/resume goal" | `/aussie-checkpoint` |
| "save session/list sessions" | `/aussie-session` |
| "config/settings/permissions" | `/aussie-config` |
| "chat/interactive/loop" | `/aussie-chat` |
| "exec/sandbox/run python" | `/aussie-exec` |
| "list tools/show tools" | `/aussie-tools` |
| "audit/self-assess/reliability" | `/aussie-audit` |
| "loop/recurring/schedule learning" | `/aussie-loop` |

If the request is ambiguous or doesn't match, ask the user. If it clearly matches multiple skills, pick the most specific one. Always recall JMEM context before executing any skill.

## Key Commands

```bash
# Claude Code slash commands (also auto-invoked by intent matching above)
/aussie-run "goal"          # Execute any goal with full agent stack
/aussie-build               # Self-improvement cycle (manual, with --apply)
/aussie-self-build          # Automated self-improvement (JMEM-driven, end-to-end)
/aussie-evolve              # Memory cleanup + skill evolution
/aussie-learn               # Full cognitive cycle (8 steps)
/aussie-swarm "task"        # Parallel multi-agent dispatch
/aussie-memory              # JMEM memory operations
/aussie-analyze             # Python 3.15 code analysis
/aussie-status              # System health check
/aussie-bench               # Performance benchmarks
/pfaa-team                  # Full 10-agent team

# Global CLI (installed via npm link)
pfaa status | run | memory | team | bench | ...

# JMEM MCP server (auto-started by Claude Code)
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
└── .claude/                 # 10 agents, 25 skills, 8 hooks, 13 MCP tools
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
