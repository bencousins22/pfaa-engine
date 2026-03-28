# Aussie Evolve — Continuous Learning & Memory Management

Automated learning, memory cleanup, and skill evolution.

## Usage

Full evolution cycle:
```bash
cd pfaa-cli && npx tsx src/cli.ts evolve
```

Memory cleanup only:
```bash
cd pfaa-cli && npx tsx src/cli.ts clean
```

View extracted instincts:
```bash
cd pfaa-cli && npx tsx src/cli.ts instincts
```

## What Each Cycle Does

1. **Extract Instincts** — find recurring patterns in memory (tools used together, phase preferences, success rates)
2. **Clean Memory** — prune dead memories (Q < 0.2), merge duplicates (cosine > 0.95), VACUUM SQLite
3. **Evolve Skills** — cluster high-confidence instincts (Q > 0.8) → auto-generate new SKILL.md files
4. **Learn** — force L2/L3/L4 pattern extraction

## Memory Growth
- L1 Episodes accumulate per tool execution
- L2 Patterns extracted every 50 episodes
- L3 Strategies discovered after ~3 warmup cycles
- L5 Knowledge emerges after ~10 cycles with consolidation
