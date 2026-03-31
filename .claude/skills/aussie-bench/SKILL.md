# Aussie Bench — Performance Benchmarks

Run performance benchmarks across the Aussie Agents stack. Measures JMEM recall speed, tool execution latency, memory consolidation throughput, and overall system responsiveness. Stores results as episodes for historical tracking.

## When the user invokes /aussie-bench [suite]

Run the requested benchmark suite. If no suite is specified, run all suites.

### Benchmark Suites

#### all (default)

Run every benchmark suite below and produce a combined report.

#### jmem

Benchmark JMEM memory operations.

1. **Recall latency** — Time a series of recall queries:
```bash
# Time each operation using shell timing
time_start=$(date +%s%N)
```

Run 5 recall queries with varying complexity:
```
Use mcp__jmem__jmem_recall(query="simple keyword", limit=5)
Use mcp__jmem__jmem_recall(query="multi word complex query about system architecture", limit=10)
Use mcp__jmem__jmem_recall(query="pattern", limit=20)
Use mcp__jmem__jmem_recall(query="checkpoint session goal", min_q=0.5, limit=5)
Use mcp__jmem__jmem_recall(query="deployment strategy optimization", level=3, limit=5)
```

Record the wall-clock time for each query.

2. **Write latency** — Time storing a test memory:
```
Use mcp__jmem__jmem_remember(content="BENCH: benchmark test memory — safe to delete", level=1, keywords=["benchmark", "test"], tags=["bench", "ephemeral"])
```

3. **Status latency** — Time the status check:
```
Use mcp__jmem__jmem_status()
```

4. **Consolidation throughput** — Time a full consolidation pass:
```
Use mcp__jmem__jmem_consolidate()
```

5. **Reflect latency** — Time a full reflection cycle:
```
Use mcp__jmem__jmem_reflect()
```

6. **Cleanup** — Decay the test memory:
```
Use mcp__jmem__jmem_reward(note_id="<bench_test_id>", reward=-1.0, context="benchmark cleanup")
```

#### tools

Benchmark core Claude Code tool operations.

1. **Glob speed** — Time file pattern matching:
```
Time: Glob for "**/*.ts" in pfaa-cli/
Time: Glob for "**/*.py" in agent_setup_cli/
Time: Glob for "**/*.md" in .claude/
```

2. **Grep speed** — Time content search:
```
Time: Grep for "function" in pfaa-cli/src/
Time: Grep for "class" in agent_setup_cli/
Time: Grep for "jmem" across the entire repo
```

3. **Read speed** — Time file reads of varying sizes:
```
Time: Read .claude/settings.json
Time: Read pfaa-cli/src/cli.ts
Time: Read a large file (find the biggest .ts or .py file)
```

4. **Bash speed** — Time shell command execution:
```
Time: echo "hello"
Time: git status
Time: python3 --version
Time: node --version
```

#### compile

Benchmark build and compilation times.

1. **TypeScript type-check**:
```bash
cd pfaa-cli && time npx tsc --noEmit
```

2. **Python syntax check**:
```bash
time python3 -m py_compile agent_setup_cli/core/tools.py
time python3 -m py_compile agent_setup_cli/core/memory.py
```

3. **JMEM import time**:
```bash
time python3 -c "import jmem"
```

### Timing Method

For each operation, record wall-clock elapsed time using Bash date commands:
```bash
start=$(python3 -c "import time; print(time.time())")
# ... run operation ...
end=$(python3 -c "import time; print(time.time())")
elapsed=$(python3 -c "print(round($end - $start, 3))")
```

### Report Format

```
AUSSIE BENCH REPORT
====================
Date: [datetime]
Platform: [os/arch]

JMEM MEMORY
  Recall (simple):      [X.XXX]s
  Recall (complex):     [X.XXX]s
  Recall (filtered):    [X.XXX]s
  Write:                [X.XXX]s
  Status:               [X.XXX]s
  Consolidate:          [X.XXX]s
  Reflect:              [X.XXX]s
  Avg recall:           [X.XXX]s

TOOL OPERATIONS
  Glob (*.ts):          [X.XXX]s
  Glob (*.py):          [X.XXX]s
  Grep (function):      [X.XXX]s
  Grep (cross-repo):    [X.XXX]s
  Read (small):         [X.XXX]s
  Read (large):         [X.XXX]s
  Bash (echo):          [X.XXX]s
  Bash (git status):    [X.XXX]s

COMPILATION
  TS type-check:        [X.XXX]s
  Python syntax:        [X.XXX]s
  JMEM import:          [X.XXX]s

SUMMARY
  Total time:           [X.XXX]s
  Fastest operation:    [name] ([X.XXX]s)
  Slowest operation:    [name] ([X.XXX]s)
  Avg operation:        [X.XXX]s
```

### Store Results

After running benchmarks, store the results as an episode for historical tracking:

```
Use mcp__jmem__jmem_remember(
  content="BENCH RESULTS [date]: Avg recall=[X.XXX]s, Avg tool=[X.XXX]s, TS check=[X.XXX]s, Total=[X.XXX]s",
  level=1,
  keywords=["benchmark", "performance", "timing"],
  tags=["bench", "metrics"]
)
```

To compare with previous runs:
```
Use mcp__jmem__jmem_recall(query="BENCH RESULTS", limit=10)
```

Display trend if previous results exist:
```
PERFORMANCE TREND
=================
[date1]: avg recall=[X.XXX]s, total=[X.XXX]s
[date2]: avg recall=[X.XXX]s, total=[X.XXX]s  (delta: +/-X%)
[date3]: avg recall=[X.XXX]s, total=[X.XXX]s  (delta: +/-X%)
```

## Default Behavior

If invoked with no arguments (`/aussie-bench`), run the **all** suite.

## Options

- `--suite [name]` — Run a specific suite: `jmem`, `tools`, `compile`
- `--iterations [N]` — Run each benchmark N times and average (default: 1)
- `--no-store` — Skip storing results in JMEM
- `--compare` — Only show comparison with previous benchmark runs
