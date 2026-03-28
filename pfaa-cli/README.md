# @pfaa/cli — Enterprise AI Agent CLI

**Phase-Fluid Agent Architecture CLI for Python 3.15**

A Claude Code-class enterprise CLI that orchestrates multi-agent swarms with JMEM semantic memory, adaptive caching, full audit logging, and deep Python 3.15 code analysis.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     @pfaa/cli (Node.js)                       │
│                                                              │
│  CLI (Commander) ─── Agent Orchestrator ─── Enterprise Layer │
│       │                    │                    │            │
│       │               CSG Swarm:            Rate Limiter     │
│       │            Coordinator              Adaptive Cache   │
│       │            Specialists              Audit Logger     │
│       │            Gatherer                 Auth/Perms       │
│       │                    │                                 │
├───────┴────────────────────┴─────────────────────────────────┤
│                    PFAA Bridge (subprocess)                   │
│              JSON-over-stdin/stdout protocol                  │
├──────────────────────────────────────────────────────────────┤
│                 PFAA Python 3.15 Engine                       │
│                                                              │
│  Phase-Fluid Execution    │  5-Layer Memory    │  27+ Tools  │
│  VAPOR (async) ~6μs       │  L1 Episodic       │  compute    │
│  LIQUID (thread) ~10μs    │  L2 Semantic        │  shell      │
│  SOLID (subprocess) ~1ms  │  L3 Strategic       │  git_*      │
│                           │  L4 Meta-Learning   │  docker_*   │
│                           │  L5 Emergent        │  sandbox    │
├──────────────────────────────────────────────────────────────┤
│                    JMEM MCP Server                           │
│  17 tools · 5 cognitive layers · Q-learning reinforcement    │
├──────────────────────────────────────────────────────────────┤
│              Claude Agent SDK + AI SDK 6                      │
│  Tool calling · Agent abstraction · Streaming · MCP          │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Install
npm install -g @pfaa/cli

# Check Python 3.15 runtime
pfaa py315 check

# Initialize project config
pfaa init

# Run a goal with the agent swarm
pfaa run "analyze this codebase for security issues and suggest Python 3.15 optimizations"

# Check full system status
pfaa status
```

## Commands

### Goal Execution

```bash
# Run any natural language goal
pfaa run "refactor auth module to use lazy imports and frozendict"

# Ask Claude directly
pfaa ask "explain the phase-fluid execution model"
```

### Agent Swarm

```bash
# Multi-agent swarm with specific roles
pfaa agent swarm "optimize database queries" --roles analyzer,refactorer,tester

# Single agent execution
pfaa agent exec "find all TODO comments" --role researcher

# List available agents
pfaa agent list
```

### Python 3.15 Tools

```bash
# Full code analysis
pfaa py315 analyze ./src/core/agent.py

# Suggest PEP 810 lazy imports
pfaa py315 lazy-imports ./src/core/framework.py

# Check runtime availability
pfaa py315 check
```

### Memory Operations

```bash
# View memory status (5 cognitive layers)
pfaa memory status

# Recall relevant memories
pfaa memory recall "database optimization patterns"

# Consolidate (promote validated knowledge)
pfaa memory consolidate
```

### System

```bash
# Full system status
pfaa status

# Run benchmarks
pfaa bench

# Self-improvement cycle
pfaa self-build --apply

# List all PFAA tools
pfaa tools
```

## Enterprise Features

| Feature | Description |
|---------|-------------|
| **Rate Limiting** | Token bucket with burst allowance — prevents runaway costs |
| **Adaptive Cache** | LRU/TTL/adaptive strategy — caches expensive analysis |
| **Audit Logging** | JSON-L audit trail with secret redaction |
| **Auth** | API key, OAuth, SAML provider support |
| **Permissions** | read/write/execute/deploy/admin granularity |
| **Concurrent Agents** | Configurable max with queue management |

## Configuration

### Project Config (`.pfaa.yaml`)

```yaml
model: claude-sonnet-4-6
maxConcurrentAgents: 8
timeoutMs: 120000

python:
  interpreterPath: python3.15
  useLazyImports: true
  useFrozenDict: true
  freeThreading: false

memory:
  layers: 5
  persistence: sqlite

enterprise:
  cache:
    enabled: true
    strategy: adaptive
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `PFAA_MODEL` | Claude model to use |
| `PFAA_PYTHON_PATH` | Python 3.15 interpreter path |
| `PFAA_MAX_AGENTS` | Max concurrent agents |
| `PFAA_TIMEOUT` | Global timeout (ms) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `PFAA_TEAM_ID` | Enterprise team ID |
| `PFAA_FREE_THREADING` | Enable free-threading |

## Programmatic API

```typescript
import {
  createBridge,
  AgentOrchestrator,
  JMEMClient,
  Python315Tools,
} from '@pfaa/cli';

// Create bridge to Python engine
const bridge = createBridge({ pythonPath: 'python3.15' });
await bridge.start();

// Orchestrate agents
const orchestrator = new AgentOrchestrator(bridge);
const result = await orchestrator.executeGoal('analyze security');

// Memory operations
const memory = new JMEMClient();
await memory.connect();
await memory.store('learned pattern', 2);

// Python 3.15 analysis
const py315 = new Python315Tools({ interpreterPath: 'python3.15' });
const analysis = py315.analyzeFile('./app.py');
```

## Tech Stack

- **Node.js 20+** — CLI runtime
- **AI SDK 6** — Agent abstraction, tool calling, MCP
- **Claude Agent SDK** — Subprocess agent management
- **Commander** — CLI framework
- **JMEM MCP Server** — Semantic memory (17 tools, Q-learning)
- **Python 3.15** — Engine runtime (lazy import, frozendict, kqueue)

## License

MIT — Created by Jamie ([@bencousins22](https://github.com/bencousins22))
