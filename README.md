# PFAA — Phase-Fluid Agent Architecture

**A Python 3.15 agent framework where agents phase-transition at runtime between coroutine, thread, and subprocess execution modes based on task demands.**

Created by **Jamie** ([@bencousins22](https://github.com/bencousins22))

Built with Claude Opus 4.6 · March 2026

---

## What Makes This Different

Every agent framework forces you to choose an execution model upfront. PFAA doesn't. Agents exist in three **phases** and transition between them at runtime:

| Phase | Implementation | Spawn Cost | Use Case |
|-------|---------------|------------|----------|
| **VAPOR** | `async` coroutine | ~6μs | I/O-bound: file reads, network, async waits |
| **LIQUID** | OS thread | ~10μs | CPU-bound: hashing, parsing, computation |
| **SOLID** | subprocess | ~1ms | Isolation: shell commands, untrusted code |

An agent starts as VAPOR. If its task needs CPU parallelism, it **condenses** to LIQUID. If it needs crash isolation, it **freezes** to SOLID. When the work is done, it **evaporates** back. The transitions are named after phase changes in matter:

```
VAPOR ──condense──► LIQUID ──freeze──► SOLID
VAPOR ◄──evaporate── LIQUID ◄──melt──── SOLID
VAPOR ──sublimate──────────────────────► SOLID
VAPOR ◄──deposit───────────────────────── SOLID
```

## Key Metrics (Benchmarked)

| Metric | Value |
|--------|-------|
| Agent spawn | **6μs** (1,000 agents in 6ms) |
| Sustained throughput | **6,000+ tasks/sec** |
| Scatter/gather 100 tasks | **6.5ms** |
| Tools available | **27** across 3 phases |
| Memory layers | **5** (episodic → emergent) |
| Test coverage | **31 tests** across 4 suites |

## Python 3.15 Features Used

| Feature | PEP | How PFAA Uses It |
|---------|-----|-----------------|
| `lazy import` | [810](https://peps.python.org/pep-0810/) | Every module defers heavy deps — ~50% startup savings |
| `frozendict` | [814](https://peps.python.org/pep-0814/) | Immutable agent configs, event payloads, state snapshots |
| `kqueue` subprocess | — | Event-driven process lifecycle on macOS (258→2 context switches) |
| `sys._is_gil_enabled()` | — | Runtime GIL detection for free-threading awareness |

## Quick Start

```bash
# Requires Python 3.15
python3 --version  # 3.15.0a7+

# Clone
git clone https://github.com/bencousins22/pfaa-engine.git
cd pfaa-engine

# Install deps
pip install typer rich

# Run benchmarks
python3 -m agent_setup_cli.core.benchmark

# Run all tests
python3 -m agent_setup_cli.core.test_full_system

# Execute a goal
python3 -m agent_setup_cli.core.autonomous "analyze code and count lines and check git status"
```

## Framework API

```python
from agent_setup_cli.core.framework import Framework

async def main():
    fw = Framework()

    # Execute a natural language goal (decomposes → parallel DAG → learn)
    state = await fw.run("search for TODO and count lines and check git status")

    # Direct tool execution
    result = await fw.tool("compute", "sqrt(42) * pi")

    # Parallel tools
    results = await fw.tools([
        ("compute", ("sqrt(2)",)),
        ("hash_data", ("hello",)),
        ("system_info", ()),
    ])

    # Supervised pipeline with restart policies
    result = await fw.pipeline([
        ("search", "codebase_search", ("TODO",)),
        ("count",  "line_count",      (".",)),
        ("status", "git_status",      ()),
    ])

    # Event streaming
    fw.on_event(lambda e: print(e.to_json()))

    # Introspection
    print(fw.status())
    print(fw.learned_patterns())
    print(fw.learned_strategies())

    await fw.shutdown()
```

## CLI

```bash
# List all 27 tools
python3 -m agent_setup_cli.cli.__main__ pfaa tools

# Execute a tool
python3 -m agent_setup_cli.cli.__main__ pfaa run compute "sqrt(42) * pi"
python3 -m agent_setup_cli.cli.__main__ pfaa run git_status
python3 -m agent_setup_cli.cli.__main__ pfaa run system_info

# Fan-out parallel execution
python3 -m agent_setup_cli.cli.__main__ pfaa scatter hash_data hello world foo bar

# Show engine status + memory
python3 -m agent_setup_cli.cli.__main__ pfaa status

# Show learned patterns and strategies
python3 -m agent_setup_cli.cli.__main__ pfaa memory

# Force a learning cycle
python3 -m agent_setup_cli.cli.__main__ pfaa learn

# Run self-improvement cycle
python3 -m agent_setup_cli.cli.__main__ pfaa self-build

# Run benchmarks
python3 -m agent_setup_cli.cli.__main__ pfaa bench

# Execute a goal
python3 -m agent_setup_cli.core.autonomous "your goal here"
```

## WebSocket Server

```bash
# Start the server
python3 -m agent_setup_cli.core.server

# Endpoints:
#   WS  /ws/agent      — Real-time goal execution with event streaming
#   GET /api/status     — Framework status
#   GET /api/tools      — List all tools
#   GET /api/memory     — Learned patterns + strategies
#   POST /api/tool      — Execute a single tool
#   POST /api/goal      — Execute a natural language goal
#   GET /api/checkpoints — Saved goal checkpoints
```

WebSocket message protocol:

```json
// Client sends:
{"type": "goal", "text": "analyze codebase and find TODO items"}
{"type": "tool", "name": "compute", "args": ["sqrt(42)"]}
{"type": "status"}

// Server sends:
{"type": "event", "event_type": "TASK_COMPLETED", "data": {"tool": "compute", "elapsed_us": 300}}
{"type": "result", "goal_id": "goal-abc123", "status": "COMPLETED", "subtasks": [...]}
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical deep-dive.

## Available Tools

### VAPOR Phase (I/O-bound, ~6μs spawn)
| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Write content to file |
| `glob_search` | Find files matching glob pattern |
| `http_fetch` | Fetch content from URL |
| `system_info` | OS, CPU, Python, GIL status |
| `disk_usage` | Disk space for a path |
| `port_check` | Check if port is open |
| `dns_lookup` | DNS resolution |
| `env_get` | Read environment variable |
| `file_stats` | File/directory statistics |

### LIQUID Phase (CPU-bound, ~10μs spawn)
| Tool | Description |
|------|-------------|
| `compute` | Mathematical expression evaluation |
| `hash_data` | Cryptographic hashing (SHA-256, MD5, etc.) |
| `grep` | Regex search across files |
| `codebase_search` | Pattern search with context lines |
| `line_count` | Count lines of code by extension |
| `json_parse` | Parse and query JSON |
| `regex_extract` | Extract regex matches from text |

### SOLID Phase (Isolated subprocess, ~1ms spawn)
| Tool | Description |
|------|-------------|
| `shell` | Execute shell command |
| `sandbox_exec` | Run Python in isolated subprocess |
| `parallel_shell` | Multiple shell commands in parallel |
| `git_status` | Git repository status |
| `git_log` | Recent git commits |
| `git_diff` | Staged/unstaged changes |
| `git_branch` | List/create branches |
| `docker_ps` | List Docker containers |
| `docker_images` | List Docker images |
| `process_list` | List OS processes |

## 5-Layer Memory System

The memory system creates a self-improving feedback loop:

| Layer | Name | What It Does |
|-------|------|-------------|
| **L1** | Episodic | Raw execution traces (tool, phase, elapsed, success) |
| **L2** | Semantic | Extracted patterns (avg latency, success rate, best phase per tool) |
| **L3** | Strategic | Learned phase optimizations (e.g., "compute is 557x faster in VAPOR than SOLID") |
| **L4** | Meta | Learning rate tuning (adjusts how fast L3 learns based on prediction accuracy) |
| **L5** | Emergent | Cross-agent knowledge (tool co-occurrence, sequential patterns, transition overhead) |

Memory persists to SQLite at `~/.pfaa/memory.db` and survives across sessions.

### Epsilon-Greedy Exploration

The engine discovers optimal phases through exploration:
- **15% of sync tool executions** try a random alternative phase
- Async tools are locked to their declared phase (VAPOR and LIQUID are functionally identical for coroutines)
- Isolated tools always stay SOLID (safety constraint)
- Once confidence > 0.5, exploration stops and the learned best phase is locked in

## Self-Building

The engine can analyze its own source code, generate new tools, sandbox-test them, and apply them:

```bash
python3 -m agent_setup_cli.cli.__main__ pfaa self-build --apply
```

The self-build cycle:
1. **Introspect** — Analyzes its own 6,600 lines using its own tools
2. **Diagnose** — Finds improvements via static analysis or Claude
3. **Propose** — Generates new tool code following PFAA patterns
4. **Test** — Sandbox-tests in an isolated subprocess
5. **Apply** — Writes validated code to `tools_generated.py`
6. **Learn** — Records the cycle in persistent memory

## License

MIT
