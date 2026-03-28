# Aussie Warmup — Tool Profiling

Profile every tool to populate memory with baseline performance data.

## Usage

```bash
cd pfaa-cli && npx tsx src/cli.ts warmup
```

## What It Does

1. Iterates through all registered tools (32+)
2. Executes each with safe default arguments
3. Records phase used and execution time
4. Forces a learning cycle after profiling
5. Populates L1 episodes for L2/L3 pattern extraction

## When To Run

- After first install to establish baselines
- After adding new tools
- After changing Python version or environment
- Before running `explore` for phase optimization
