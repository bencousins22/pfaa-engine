# Aussie Agent Team — Claude Code Skill

Spawn and orchestrate the full Aussie Agents team with JMEM semantic memory.

## Usage

When asked to run agents, optimize strategies, or self-build:

### Remix Mode (Full Power)
```bash
python3 agents/team/remix_spawn.py "your goal here"
```

### Basic Team
```bash
python3 agents/team/spawn.py "your goal here"
```

### FreqTrade Bitcoin Optimization
```bash
python3 agents/team/spawn.py --freqtrade
```

### Node.js CLI
```bash
cd pfaa-cli && npx tsx src/cli.ts run "your goal"
cd pfaa-cli && npx tsx src/cli.ts agent swarm "goal" --roles analyzer,reviewer,tester
cd pfaa-cli && npx tsx src/cli.ts py315 analyze ./src/core/agent.py
```

## Agent Roles

| Role | Specialty |
|------|-----------|
| Lead | Goal decomposition, team coordination |
| Researcher | Data analysis, trend detection |
| Strategist | Signal generation, parameter design |
| Optimizer | Hyperopt tuning, backtest optimization |
| Validator | OOS testing, overfitting detection |
| Risk Manager | Position sizing, drawdown protection |
| Deployer | Config generation, deployment |
| Rewriter | Python 3.15 performance optimization |
| Modernizer | Language idiom modernization |
| Skill Writer | Extract skills from high-Q memories |

## Memory System

JMEM provides 6-layer persistent semantic memory across sessions:
- **L1 Episodic**: Raw task results and execution traces
- **L2 Semantic**: Patterns extracted from episodes (auto-promoted when Q > 0.8)
- **L3 Strategic**: Validated rules and principles
- **L4 Skill**: Executable capabilities extracted from high-Q memories
- **L5 Meta-Learning**: Learning rate tuning and cross-task transfer
- **L6 Emergent**: Cross-agent knowledge synthesis and novel insights

Knowledge automatically promotes up the hierarchy as Q-values increase through reinforcement learning.

### MCP Tools (13)

| Tool | Purpose |
|------|---------|
| `jmem_recall` | Retrieve relevant memories by semantic query |
| `jmem_remember` | Store new memories at a given level |
| `jmem_consolidate` | Promote patterns to higher cognitive layers |
| `jmem_reflect` | Analyze memory patterns and generate insights |
| `jmem_reward` | Reinforce a memory via Q-learning |
| `jmem_reward_recalled` | Reinforce memories retrieved during recall |
| `jmem_evolve` | Evolve memory store (decay, promote, prune) |
| `jmem_status` | Report memory store health and statistics |
| `jmem_decay` | Apply time-based decay to stale memories |
| `jmem_meta_learn` | L5 meta-learning — tune learning rates across tasks |
| `jmem_emergent` | L6 emergent — synthesize cross-agent knowledge |
| `jmem_extract_skills` | Extract executable skills from high-Q memories |
| `jmem_recall_cross` | Cross-agent recall — query memories from other agents |

## Self-Build

The team can recursively improve itself:
1. Analyze the codebase for gaps
2. Generate new tools to fill gaps
3. Test in sandbox
4. Apply validated changes
5. Store learnings as principles/skills
