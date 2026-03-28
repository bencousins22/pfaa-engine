# Aussie Loop — Automated Learning Cycles

Run continuous learning on a schedule.

## Usage

Single cycle:
```bash
cd pfaa-cli && npx tsx src/cli.ts warmup && npx tsx src/cli.ts learn
```

Full evolution loop:
```bash
cd pfaa-cli && npx tsx src/cli.ts warmup && npx tsx src/cli.ts learn && npx tsx src/cli.ts evolve
```

## Memory Growth Per Cycle
- +23 L1 episodes (one per tool)
- L2 patterns refine (confidence increases)
- L3 strategies discovered after ~3 cycles
- L5 knowledge emerges after ~10 cycles
