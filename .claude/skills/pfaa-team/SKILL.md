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

JMEM provides persistent semantic memory across sessions:
- **L1 Episode**: Raw task results
- **L2 Concept**: Patterns extracted from episodes
- **L3 Principle**: Validated rules
- **L4 Skill**: Executable capabilities

Knowledge automatically promotes up the hierarchy as Q-values increase through reinforcement learning.

## Self-Build

The team can recursively improve itself:
1. Analyze the codebase for gaps
2. Generate new tools to fill gaps
3. Test in sandbox
4. Apply validated changes
5. Store learnings as principles/skills
