<p align="center">
  <img src="assets/logo.jpeg" alt="PFAA — Phase-Fluid Agent Architecture" width="280" />
</p>

<h1 align="center">PFAA — Phase-Fluid Agent Architecture</h1>

<p align="center">
  <strong>Enterprise AI agent framework with phase-fluid execution, 6-layer semantic memory, and multi-agent team orchestration. All skills run natively in Claude Code.</strong>
</p>

<p align="center">
  Created by <strong>Jamie</strong> (<a href="https://github.com/bencousins22">@bencousins22</a>)<br/>
  Built with Claude Opus 4.6
</p>

<p align="center">
  <a href="https://github.com/bencousins22/pfaa-engine/actions/workflows/ci.yml"><img src="https://github.com/bencousins22/pfaa-engine/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/badge/python-3.15-green?style=flat-square" alt="Python 3.15" />
  <img src="https://img.shields.io/badge/node-22+-blue?style=flat-square" alt="Node 22+" />
  <img src="https://img.shields.io/badge/agents-10-gold?style=flat-square" alt="10 agents" />
  <img src="https://img.shields.io/badge/skills-27-blue?style=flat-square" alt="27 skills" />
  <img src="https://img.shields.io/badge/tools-48-green?style=flat-square" alt="48 tools" />
  <img src="https://img.shields.io/badge/JMEM-6_layer-purple?style=flat-square" alt="6-layer JMEM" />
  <img src="https://img.shields.io/badge/tests-262-brightgreen?style=flat-square" alt="262 tests" />
  <img src="https://img.shields.io/badge/self--building-✓-brightgreen?style=flat-square" alt="Self-building" />
  <img src="https://img.shields.io/badge/license-Apache_2.0-blue?style=flat-square" alt="Apache 2.0" />
</p>

---

## What Is PFAA?

PFAA is three things in one repo:

1. **A Python agent engine** where agents phase-transition at runtime between coroutine (VAPOR), thread (LIQUID), and subprocess (SOLID) execution
2. **A Claude Code integration** with 10 specialized agents, 27 skills, and 9 hooks that run natively as slash commands
3. **A semantic memory system (JMEM)** with 6 cognitive layers, Q-learning reinforcement, and a Unix socket daemon for <10ms access

```
◆ Aussie · 48t · JMEM 6L · 747m · Qα · main
```

---

## Quick Start

```bash
git clone https://github.com/bencousins22/pfaa-engine.git
cd pfaa-engine
npm install && pip install -e .

# Run tests
python3 -m pytest tests/ -v

# Claude Code — skills auto-route by intent
# "run [goal]"     → /aussie-run
# "swarm [task]"   → /aussie-swarm
# "status"         → /aussie-status
# "memory"         → /aussie-memory
# "self-build"     → /aussie-self-build
```

---

## Architecture

```
pfaa-engine/
├── agent_setup_cli/core/    # Python engine — 27+ tools, phase-fluid execution
├── jmem-mcp-server/         # JMEM semantic memory — MCP server + Unix socket daemon
├── src/                     # TypeScript core — orchestrator, providers, services
│   ├── core/                #   swarm protocol, task dependencies, orchestrator
│   ├── services/            #   autoDream, cronScheduler, toolOrchestration, sessionMemory
│   ├── integrations/a0/     #   Agent Zero bridge — A2A communication
│   └── providers/           #   Claude, Gemini, Claude Agent SDK
├── pfaa-cli/                # Enterprise Node.js CLI with Ink TUI
├── freqtrade_strategy/      # Self-optimizing BTC FreqTrade strategy
├── .claude/                 # 10 agents, 27 skills, 9 hooks, JMEM MCP
│   ├── agents/              #   10 specialized agent definitions
│   ├── skills/              #   27 slash commands (auto-routed by intent)
│   └── hooks/               #   cortex RL processor, JMEM daemon, banner
└── .github/                 # CI/CD — lint, test, security, releases, Dependabot
```

---

## Phase-Fluid Execution

Every agent framework forces you to choose an execution model upfront. PFAA doesn't. Agents transition between three phases at runtime:

| Phase | Implementation | Spawn Cost | Use Case |
|-------|---------------|------------|----------|
| **VAPOR** | `async` coroutine | ~6μs | I/O-bound: file reads, network, API calls |
| **LIQUID** | OS thread | ~10μs | CPU-bound: hashing, parsing, computation |
| **SOLID** | subprocess | ~1ms | Isolation: shell commands, untrusted code |

```
VAPOR ──condense──► LIQUID ──freeze──► SOLID
VAPOR ◄──evaporate── LIQUID ◄──melt──── SOLID
```

---

## JMEM — 6-Layer Semantic Memory

JMEM provides persistent semantic memory with Q-learning reinforcement. Knowledge automatically promotes up the hierarchy as Q-values increase.

| Layer | Name | What It Stores |
|-------|------|---------------|
| **L1** | Episodic | Raw execution traces and session events |
| **L2** | Semantic | Extracted patterns (auto-promoted when Q > 0.8) |
| **L3** | Strategic | Validated principles and rules |
| **L4** | Skill | Executable capabilities from high-Q memories |
| **L5** | Meta-Learning | Learning rate tuning and cross-task transfer |
| **L6** | Emergent | Cross-agent knowledge synthesis and novel insights |

### JMEM Daemon

A long-running Unix socket daemon keeps the JMEM engine warm in memory. Hooks query it in <10ms instead of spawning Python (3-8s).

```
SessionStart → daemon starts → engine warm in memory
Hooks → send JSON over /tmp/pfaa-jmem.sock → <10ms response
Stop hooks → fire in background → UI never blocks
```

### MCP Tools (13)

| Tool | Purpose |
|------|---------|
| `jmem_recall` | Search memories (TF-IDF + BM25 + Q-boost) |
| `jmem_remember` | Store new memories at a cognitive level |
| `jmem_consolidate` | Promote patterns to higher layers |
| `jmem_reflect` | Analyze memory patterns, generate insights |
| `jmem_reward` | Reinforce via Q-learning |
| `jmem_evolve` | Decay stale, promote strong, prune weak |
| `jmem_status` | Memory health and statistics |
| `jmem_decay` | Time-based decay for stale memories |
| `jmem_meta_learn` | L5 — tune learning rates across tasks |
| `jmem_emergent` | L6 — synthesize cross-agent knowledge |
| `jmem_extract_skills` | Extract executable skills from high-Q memories |
| `jmem_recall_cross` | Cross-namespace memory query |
| `jmem_reward_recalled` | Reinforce recently recalled memories |

---

## Claude Code Agents (10)

| Agent | Role | Phase |
|-------|------|-------|
| `pfaa-lead` | Orchestrates full team, goal decomposition | VAPOR |
| `aussie-researcher` | Deep research and synthesis | VAPOR |
| `aussie-planner` | Goal decomposition and planning | VAPOR |
| `aussie-architect` | System design and ADRs | VAPOR |
| `aussie-security` | OWASP vulnerability audits | VAPOR |
| `aussie-tdd` | Test-first development | SOLID |
| `pfaa-rewriter` | Python 3.15 optimization | LIQUID |
| `pfaa-validator` | Read-only QA and validation | SOLID |
| `aussie-deployer` | Zero-downtime deployment | SOLID |
| `aussie-docs` | Documentation sync | VAPOR |

---

## Skills (27)

Skills auto-route by intent — no slash command needed:

| Say... | Skill | What It Does |
|--------|-------|-------------|
| "run [goal]" | `/aussie-run` | Execute any goal with full agent stack |
| "swarm [task]" | `/aussie-swarm` | Parallel multi-agent dispatch |
| "scatter [tool] across [inputs]" | `/aussie-scatter` | Fan-out tool execution |
| "pipeline [steps]" | `/aussie-pipeline` | Sequential step execution |
| "spawn team" | `/pfaa-team` | Full 10-agent team |
| "generate code for [X]" | `/aussie-generate` | Code generation from natural language |
| "self-build" | `/aussie-self-build` | Automated self-improvement cycle |
| "learn" | `/aussie-learn` | Full JMEM cognitive cycle |
| "evolve memory" | `/aussie-evolve` | Memory cleanup and skill evolution |
| "status" | `/aussie-status` | System health check |
| "benchmark" | `/aussie-bench` | Performance benchmarks |
| "memory" | `/aussie-memory` | JMEM operations |
| "analyze python" | `/aussie-analyze` | Python 3.15 code analysis |
| "search tools" | `/aussie-search` | Tool and capability search |
| "ask [question]" | `/aussie-ask` | Smart question answering |
| "chat" | `/aussie-chat` | Interactive agent loop |

Plus 11 more: checkpoint, session, config, exec, tools, audit, loop, warmup, explore, build, a0-bridge.

---

## Aussie Cortex — Self-Improving Hook Processor

The cortex is an RL-driven hook processor that observes every Claude Code event and makes decisions:

- **S1 Fast Path** — L4 JMEM skills loaded as frozen decision tables (<1ms)
- **S2 Full Path** — Per-handler logic with JMEM recall, phase detection, cross-agent context
- **Circuit breaker** — Auto-disables failing handlers after 3 errors, re-enables on success
- **Dream cycle** — Consolidates + decays + extracts skills when pressure threshold reached
- **Self-assessment** — Adjusts intervention level based on decision accuracy

### Hook Events Processed

| Event | What Cortex Does |
|-------|-----------------|
| `SubagentStart` | Detect phase, inject context, check L4 rules |
| `SubagentStop` | Reward/penalize recalled memories, detect repeated failure |
| `PostToolUseFailure` | Classify error, store episode, escalate on pattern |
| `TaskCompleted` | Silent reinforcement, pressure accumulation |
| `UserPromptSubmit` | JMEM auto-recall, inject relevant context |
| `FileChanged` | Python 3.15 AST analysis, config tracking |
| `Stop` | Store episode, trigger dream if pressure > threshold |

---

## Services

| Service | Description |
|---------|-------------|
| **AutoDream** | Time+session gated JMEM consolidation with PID lock |
| **ToolOrchestration** | Parallel/serial execution — read-only tools run concurrently |
| **CronScheduler** | 5-field cron with durable persistence, auto-expiry |
| **SessionMemory** | Pattern-based memory extraction from conversations |
| **Swarm Protocol** | Team creation, mailbox messaging, dispatch and collect |
| **Task Manager** | Dependency chains (blocks/blockedBy), auto-unblock |

---

## Agent Zero Integration

PFAA bridges with [Agent Zero](https://github.com/frdel/agent-zero) v1.5+ for cross-framework orchestration:

```typescript
import { A0Bridge } from './src/integrations/a0'

const bridge = new A0Bridge({ a0Url: 'http://localhost:50001', a0ApiKey: '...' })
const result = await bridge.delegateAndWait('analyze this codebase')
```

- Task delegation with polling
- Plugin manifest generation (PFAA skill to A0 plugin)
- Memory sync between JMEM and A0's vector memory
- A2A bidirectional communication

---

## FreqTrade Bitcoin Strategy

A self-optimizing BTC trading strategy designed for the 2024-2026 market:

- Multi-signal approach with PFAA agent team optimization
- Hyperparameter tuning via agent swarm
- CI validates strategy syntax on every PR
- Deployed via Railway with Docker

---

## CI/CD

| Workflow | Trigger | What It Does |
|----------|---------|-------------|
| **CI** | Push/PR | Ruff lint + pytest + tsc type-check |
| **Security** | Push to main + weekly | CodeQL (Python + TS) + pip-audit |
| **Release** | Tag `v*` | Build wheel + TS, GitHub Release with changelog |
| **FreqTrade** | PR touching strategy | Validate syntax, post result as PR comment |
| **Dependabot** | Weekly | PRs for pip, npm, GitHub Actions updates |

---

## Python 3.15 Features

| Feature | PEP | How PFAA Uses It |
|---------|-----|-----------------|
| `lazy import` | [810](https://peps.python.org/pep-0810/) | Deferred heavy deps — ~50% startup savings |
| `frozendict` | [814](https://peps.python.org/pep-0814/) | Immutable agent configs, event payloads |
| `match/case` | [634](https://peps.python.org/pep-0634/) | Cortex event dispatch, interest scoring |
| `def func[T]()` | [695](https://peps.python.org/pep-0695/) | Type parameter syntax (replacing TypeVar) |
| `kqueue` subprocess | — | Event-driven process lifecycle on macOS |

---

## Benchmarks

| Metric | Value |
|--------|-------|
| Agent spawn | **6μs** (50,000 agents in 374ms) |
| Throughput | **57,582 tasks/sec** (swarm) |
| Framework latency | **1.0ms** avg |
| Peak memory | **31 MB** |
| Tests | **262 passing** across 10 suites |

<details>
<summary>Full benchmark comparison vs other frameworks</summary>

| Metric | PFAA | PydanticAI | LangChain | LangGraph |
|--------|------|-----------|-----------|-----------|
| **Latency** | **1.0ms** | 6,592ms | 6,046ms | 10,155ms |
| **Throughput** | **24,607/s** | 4.15/s | 4.26/s | 2.70/s |
| **Memory** | **31 MB** | 4,875 MB | 5,706 MB | 5,570 MB |
| **Agent Spawn** | **6μs** | ~500ms | ~500ms | ~500ms |

> PFAA measures pure framework orchestration overhead. Competitor numbers from published benchmarks include LLM API latency.

</details>

---

## License

[Apache 2.0](LICENSE)
