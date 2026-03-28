# @aussie-agents/pfaa

**Phase-Fluid Agent Architecture — AI Agent CLI**

48 tools · 5-layer memory · multi-agent swarms · Python 3.15

```bash
# Install globally
npm install -g @aussie-agents/pfaa

# Or run directly via npx (no install needed)
npx @aussie-agents/pfaa                    # Interactive CLI
npx @aussie-agents/pfaa run "fix auth.py"  # Goal execution
npx @aussie-agents/pfaa exec -c "print(1)" # Python sandbox
npx @aussie-agents/pfaa swarm "find leads" # 8-agent swarm
npx @aussie-agents/pfaa memory stats       # JMEM health
npx @aussie-agents/pfaa --help             # All commands
```

## Commands

```
pfaa run <goal>                    Execute a goal with the agent swarm
pfaa exec -c <code>                Python sandbox execution
pfaa exec -f <file>                Run a Python file in sandbox
pfaa swarm <goal>                  Multi-agent swarm (8 roles)
pfaa tool <name> [args...]         Execute a single PFAA tool
pfaa scatter <tool> <inputs...>    Fan-out tool across inputs
pfaa pipeline <steps...>           Sequential tool pipeline
pfaa team <goal>                   Spawn full agent team (6 or 10)
pfaa explore                       Phase exploration (epsilon-greedy)
pfaa learn                         Force memory learning cycle
pfaa ask <prompt>                  Ask Claude a question
pfaa self-build --apply            Self-improvement cycle

pfaa agent exec <desc> -r <role>   Run a single agent
pfaa agent list                    List agent roles

pfaa memory stats                  Memory status (5 layers)
pfaa memory recall <query>         Search memory
pfaa memory consolidate            Promote validated knowledge
pfaa memory dump                   Full memory dump (JSON)

pfaa py315 analyze <path>          Python 3.15 analysis
pfaa py315 check                   Check runtime availability
pfaa py315 lazy-imports <path>     Suggest PEP 810 conversions

pfaa tools                         List all tools by phase
pfaa bench                         Run 7 performance benchmarks
pfaa status                        Full system status
pfaa checkpoints                   List resumable goals
pfaa resume <id>                   Resume from checkpoint
pfaa init                          Create .pfaa.yaml config
pfaa config set-api-key <key>      Save Anthropic API key
pfaa config show                   Show configuration
```

## Architecture

```
Node.js CLI ──── Agent Orchestrator ──── Enterprise Layer
     │                  │                     │
     │             CSG Swarm:             Rate Limiter
     │          Coordinator               Adaptive Cache
     │          Specialists               Audit Logger
     │          Gatherer                  Auth/Perms
     │                  │
─────┴──────────────────┴──────────────────────────────
              PFAA Bridge (subprocess)
          JSON-over-stdin/stdout protocol
───────────────────────────────────────────────────────
            PFAA Python 3.15 Engine

 Phase-Fluid Execution  │  5-Layer Memory  │  48 Tools
 VAPOR (async) ~6μs     │  L1 Episodic     │  compute
 LIQUID (thread) ~10μs  │  L2 Semantic     │  shell
 SOLID (process) ~1ms   │  L3 Strategic    │  git_*
                        │  L4 Meta-Learn   │  docker_*
                        │  L5 Emergent     │  sandbox
───────────────────────────────────────────────────────
              JMEM MCP Server
 7 tools · 5 cognitive layers · Q-learning reinforcement
```

## Agent Roles

| Role | Phase | Capabilities |
|------|-------|-------------|
| analyzer | VAPOR | code-analysis, py315-detection, security |
| refactorer | LIQUID | code-edit, lazy-import, frozendict |
| tester | SOLID | test-gen, coverage, benchmark |
| deployer | SOLID | docker, ci-cd, rollback |
| researcher | VAPOR | search, web, docs |
| orchestrator | VAPOR | planning, decomposition |
| reviewer | VAPOR | code-review, security-audit |
| builder | SOLID | build, compile, package |

## Configuration

```yaml
# .pfaa.yaml
model: claude-sonnet-4-6
maxConcurrentAgents: 8
timeoutMs: 120000

python:
  interpreterPath: python3.15
  useLazyImports: true
  useFrozenDict: true
  freeThreading: false

enterprise:
  cache:
    enabled: true
    strategy: adaptive
```

## Programmatic API

```typescript
import { createBridge, AgentOrchestrator, JMEMClient, Python315Tools } from '@aussie-agents/pfaa';

const bridge = createBridge({ pythonPath: 'python3.15' });
await bridge.start();

const orchestrator = new AgentOrchestrator(bridge);
const result = await orchestrator.executeGoal('analyze security');

const memory = new JMEMClient();
await memory.connect();
await memory.store('learned pattern', 2);
```

## License

MIT — [Aussie Agents](https://github.com/Aussie-Agents)
