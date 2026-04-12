<p align="center">
  <img src="assets/logo.jpeg" alt="PFAA" width="180" />
</p>

# PFAA Architecture — Technical Deep-Dive

Created by **Jamie** ([@bencousins22](https://github.com/bencousins22))

**6,614 lines of Python 3.15 · 19 core modules · 27 tools · 31 tests**

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRAMEWORK                               │
│  fw.run("goal") / fw.tool("name") / fw.pipeline([...])          │
├─────────────┬──────────────┬────────────────┬───────────────────┤
│  AUTONOMOUS │  ORCHESTRATOR│  SUPERVISOR    │  SELF-BUILDER     │
│  AGENT      │  (Task DAG)  │  TREE          │                   │
│             │              │  (Delegation)  │  introspect →     │
│  goal →     │  submit →    │                │  diagnose →       │
│  decompose →│  run_all →   │  parent →      │  generate →       │
│  DAG →      │  parallel    │  children →    │  sandbox test →   │
│  execute →  │  execute     │  restart on    │  apply →          │
│  learn      │              │  failure       │  learn            │
├─────────────┴──────────────┴────────────────┴───────────────────┤
│                        TOOL REGISTRY                            │
│  27 tools · phase-aware · epsilon-greedy exploration            │
├──────────┬──────────┬───────────────────────────────────────────┤
│          │          │                                           │
│  VAPOR   │  LIQUID  │  SOLID                                   │
│  10 tools│  7 tools │  10 tools                                 │
│  async   │  threaded│  subprocess                               │
│  ~6μs    │  ~10μs   │  ~1ms                                     │
│          │          │                                           │
├──────────┴──────────┴───────────────────────────────────────────┤
│                        NUCLEUS                                  │
│  scatter/gather · pipeline · swarm pool · execute_one           │
├─────────────────────────────────────────────────────────────────┤
│                      FLUID AGENT                                │
│  phase transitions · mailbox · auto-evaporate · apoptosis       │
├─────────────────────────────────────────────────────────────────┤
│                    PHASE ENGINE                                 │
│  VAPOR ↔ LIQUID ↔ SOLID · 6 named transitions                  │
├──────────────┬──────────────────────────────────────────────────┤
│  EVENT BUS   │            6-LAYER MEMORY                        │
│              │  L1 Episodic → L2 Semantic → L3 Strategic        │
│  typed events│  → L4 Skill → L5 Meta-Learning                   │
│  WebSocket   │  → L6 Emergent Intelligence                      │
│  streaming   │  SQLite WAL persistence (~/.pfaa/memory.db)      │
├──────────────┴──────────────────────────────────────────────────┤
│                    CLAUDE BRIDGE                                │
│  subprocess invocation · fan-out research · code generation     │
├─────────────────────────────────────────────────────────────────┤
│                    SERVER (FastAPI)                              │
│  WS /ws/agent · GET /api/status · POST /api/goal · POST /api/tool│
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Map

```
agent_setup_cli/
├── core/                          5,971 lines — the engine
│   ├── phase.py            55L    Phase definitions + 6 transitions
│   ├── agent.py           279L    FluidAgent — phase-transitioning worker
│   ├── nucleus.py         269L    Scatter/gather, pipeline, swarm orchestration
│   ├── tools.py           515L    10 core tools + registry + exploration
│   ├── tools_extended.py  501L    16 extended tools (git, docker, system, text)
│   ├── tools_generated.py  50L    Self-generated tools (codebase_search)
│   ├── orchestrator.py    233L    Reactive task DAG with dependencies
│   ├── memory.py          620L    6-layer meta-learning memory
│   ├── persistence.py     402L    SQLite WAL disk-backed memory
│   ├── claude_bridge.py   371L    Claude Code subprocess integration
│   ├── autonomous.py      319L    Goal-driven agent with decomposition
│   ├── self_build.py      542L    Self-improvement loop
│   ├── delegation.py      209L    Supervisor tree with restart policies
│   ├── streaming.py       167L    Async EventBus with typed events
│   ├── framework.py       296L    Unified entry point
│   ├── server.py          267L    FastAPI WebSocket + HTTP API
│   ├── benchmark.py       323L    7-test performance suite
│   ├── test_integration.py 255L   5-test integration suite
│   └── test_full_system.py 298L   8-test system suite
├── cli/                           CLI interface
│   ├── __main__.py                Typer app entry point
│   └── pfaa.py                    PFAA CLI commands
├── ai/                            Legacy AI client (lazy imported)
├── database/                      SQLAlchemy models (legacy)
├── web/server/                    xterm.js terminal (legacy)
└── utils/                         Logger
```

---

## Phase-Fluid Execution Model

### The Three Phases

```
                    ┌─────────────────────────────────────────┐
                    │           PHASE-FLUID AGENT             │
                    │                                         │
    ┌───────┐   CONDENSE    ┌─────────┐    FREEZE    ┌──────────┐
    │ VAPOR │ ──────────►   │ LIQUID  │ ──────────►  │  SOLID   │
    │       │   ◄──────────  │         │  ◄──────────  │          │
    └───────┘    EVAPORATE   └─────────┘    MELT      └──────────┘

    async coroutine       OS thread          subprocess
    ~6μs spawn            ~10μs spawn        ~1ms spawn
    shared memory         shared memory      isolated memory
    I/O-bound             CPU-parallel       crash-safe
    1000s concurrent      N per core         OS-level isolate
```

### Phase Transitions

| Transition | From → To | When |
|-----------|-----------|------|
| **condense** | VAPOR → LIQUID | Task needs CPU parallelism |
| **freeze** | LIQUID → SOLID | Task needs crash isolation |
| **melt** | SOLID → LIQUID | Isolation no longer needed |
| **evaporate** | LIQUID → VAPOR | Task returns to I/O-bound |
| **sublimate** | VAPOR → SOLID | Skip LIQUID, go straight to isolation |
| **deposit** | SOLID → VAPOR | Process done, return to lightest |

### How Phases Execute Functions

| Phase | Sync Function | Async Function |
|-------|--------------|----------------|
| **VAPOR** | `run_in_executor(None, fn)` — shared default pool | `await fn()` — direct await |
| **LIQUID** | `run_in_executor(dedicated_pool, fn)` — own thread | `await fn()` — direct await |
| **SOLID** | `ProcessPoolExecutor` — subprocess via `functools.partial` | Not supported (can't pickle coroutines) |

**Key insight**: For async functions, VAPOR and LIQUID are functionally identical — both just `await fn()`. Exploration is therefore disabled for async tools. Real phase differences only exist for sync functions.

---

## Orchestration Patterns

### 1. Scatter/Gather (Fan-out / Fan-in)

Spawn N agents, execute task variants in parallel, collect all results.

```python
results = await nucleus.scatter(
    config=AgentConfig("worker"),
    task_fn=my_task,
    args_list=[("input1",), ("input2",), ("input3",)],
    hint=Phase.VAPOR,
)
```

**Used by**: AutonomousAgent (parallel subtask execution), ToolRegistry.execute_many

### 2. Pipeline (Sequential Phase Escalation)

Data flows through stages, each in a different phase.

```python
results = await nucleus.pipeline(config, [
    (Phase.VAPOR,  fetch_data,    ("url",)),     # I/O
    (Phase.LIQUID, process_data,  ()),            # CPU
    (Phase.SOLID,  validate,      ()),            # isolation
])
```

Each stage receives the previous stage's result as its first argument.

### 3. Swarm (Persistent Worker Pool)

Long-lived agent pool consuming from a task queue.

```python
await nucleus.swarm(config, pool_size=8, task_queue=q, result_queue=rq)
```

### 4. Task DAG (Dependency-Aware Parallel Execution)

Submit tasks with dependencies. Independent tasks run in parallel automatically.

```python
orch = Orchestrator()
t1 = orch.submit("compute", "sqrt(42)")
t2 = orch.submit("hash_data", "test")
t3 = orch.submit("compute", "pi", depends_on=[t1, t2])  # waits for t1, t2
results = await orch.run_all()
```

### 5. Supervisor Tree (Hierarchical Delegation)

Parent agents manage child agents with automatic restart on failure.

```python
sup = Supervisor("pipeline")
sup.add_worker(WorkerSpec("fetch", fetch_fn, phase=Phase.VAPOR,
                          restart_policy=RestartPolicy.ON_ERROR, max_restarts=3))
sup.add_worker(WorkerSpec("parse", parse_fn, phase=Phase.LIQUID))

child = Supervisor("validators")
child.add_worker(WorkerSpec("check", validate_fn, phase=Phase.SOLID))
sup.add_child_supervisor(child)

result = await sup.run_all()
```

Restart policies: `ALWAYS`, `NEVER`, `ON_ERROR`, `TRANSIENT`

---

## Memory Architecture

### Layer Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                      MEMORY SYSTEM                            │
│                                                               │
│  ┌──────────┐  extract   ┌──────────┐  learn   ┌───────────┐│
│  │ L1       │ ─────────► │ L2       │ ───────► │ L3        ││
│  │ EPISODIC │            │ SEMANTIC │          │ STRATEGIC ││
│  │          │            │          │          │           ││
│  │ Raw      │            │ Patterns │          │ Phase     ││
│  │ traces   │            │ per tool │          │ optim.    ││
│  └──────────┘            └──────────┘          └─────┬─────┘│
│       ▲                                              │      │
│       │                                     extract  │      │
│       │                                              ▼      │
│       │                                      ┌───────────┐  │
│       │                                      │ L4        │  │
│       │                                      │ SKILL     │  │
│       │                                      │           │  │
│       │                                      │ Executable│  │
│       │                                      │ capabil.  │  │
│       │                                      └─────┬─────┘  │
│       │                                    observe │        │
│       │                                            ▼        │
│       │                  ┌──────────┐       ┌───────────┐   │
│       │                  │ L6       │       │ L5        │   │
│       │                  │ EMERGENT │       │ META      │   │
│       │                  │          │       │           │   │
│       └──────────────────│ Cross-   │       │ Learning  │   │
│         influences       │ agent    │       │ rate      │   │
│         future           │ knowledge│       │ tuning    │   │
│         episodes         └──────────┘       └───────────┘   │
│                                                               │
│  Persistence: SQLite WAL at ~/.pfaa/memory.db                 │
└──────────────────────────────────────────────────────────────┘
```

### L1 — Episodic Memory

Ring buffer of raw execution traces. Each episode records:
- Tool name, phase used, elapsed microseconds
- Success/failure, transitions taken
- Args hash (for dedup), truncated result summary

Capacity: 10,000 episodes (LRU eviction).

### L2 — Semantic Memory

Statistical patterns extracted from L1:
- **Per-tool**: avg/p50/p95 latency, success rate
- **Per-phase performance**: avg latency broken down by which phase the tool ran in
- **Best phase**: the phase with lowest average latency
- **Confidence**: `min(1.0, log2(sample_size) / 10.0)` — more data = more confidence

Extraction runs every 50 episodes or on-demand via `force_learn()`.

### L3 — Strategic Memory

Phase optimization strategies derived from L2. A strategy is learned when:
1. A tool has been executed in **2+ different phases** (requires exploration)
2. The confidence is **≥ 0.3**
3. The best phase is **≥ 20% faster** than the worst phase

Example strategies discovered by the engine:
```
compute:    SOLID → VAPOR  (557x faster — subprocess spawn dwarfs the math)
hash_data:  SOLID → VAPOR  (1065x faster — same reason)
line_count: SOLID → VAPOR  (1.4x faster — I/O-bound, subprocess adds overhead)
```

### L4 — Meta-Learning

Observes L3's prediction accuracy and adjusts the learning rate:
- If L3 predictions are **< 30% accurate**: increase learning rate (adapt faster)
- If L3 predictions are **> 80% accurate**: decrease learning rate (stabilize)
- Detects strategy drift when effectiveness drops below 30%

### L5 — Emergent Intelligence

Cross-agent knowledge synthesis from L1 episodes:
- **Tool co-occurrence**: which tools frequently run together (window analysis)
- **Sequential patterns**: which tool typically follows which (bigram analysis)
- **Transition overhead**: quantifies the cost of phase transitions vs staying in-phase

### Epsilon-Greedy Exploration

Phase exploration feeds L2 with cross-phase data, enabling L3 strategy discovery.

```
For each tool execution:
  if tool.isolated:           → always SOLID (safety)
  if tool.is_async:           → always declared phase (VAPOR/LIQUID identical for async)
  if confidence >= 0.5:       → use learned best phase (exploit)
  if random() < 0.15:         → try random alternative phase (explore)
  else:                       → use declared default phase
```

Sync tools explore across all three phases. This is how the engine discovers that `compute` in SOLID is 557x slower than in VAPOR — it tried both and measured.

---

## Autonomous Agent

### Goal → Subtask Decomposition

The AutonomousAgent accepts natural language goals and decomposes them using keyword matching:

```
"analyze codebase and search for TODO and count lines and check git status"
                ↓
┌─────────────────────────────────────────────────┐
│ Keyword Matches:                                 │
│   "analyze" → line_count, file_stats, codebase_search │
│   "search"  → codebase_search                   │
│   "count"   → line_count                         │
│   "lines"   → line_count                         │
│   "git"     → git_status                         │
│   "status"  → git_status, system_info            │
└─────────────────────────────────────────────────┘
                ↓ (deduplicated)
┌─────────────────────────────────────────────────┐
│ Subtasks (all independent → run in parallel):    │
│   [st-1] line_count      phase=LIQUID            │
│   [st-2] file_stats      phase=VAPOR             │
│   [st-3] codebase_search phase=LIQUID            │
│   [st-4] git_status      phase=SOLID             │
│   [st-5] system_info     phase=VAPOR             │
└─────────────────────────────────────────────────┘
```

### Execution Flow

```
1. DECOMPOSE    goal → subtasks via keyword matching
2. CHECKPOINT   save state to ~/.pfaa/checkpoints/{goal_id}.json
3. EXECUTE DAG  find ready tasks (deps met) → parallel asyncio.gather
4. RETRY        failed tasks get retried (max 2 replans)
5. LEARN        force_learn() → update L2/L3/L4/L5
6. CHECKPOINT   save final state
```

### Interrupt/Resume

Goals checkpoint to disk as JSON. Resume from any checkpoint:

```python
agent = AutonomousAgent()
state = await agent.resume("goal-abc123")
```

---

## Event Streaming

The EventBus provides real-time execution visibility.

### Event Types

| Event | When Emitted |
|-------|-------------|
| `GOAL_STARTED` | Framework.run() begins |
| `GOAL_DECOMPOSED` | Subtasks generated |
| `GOAL_COMPLETED` | All subtasks done |
| `GOAL_FAILED` | Subtask failures |
| `TASK_STARTED` | Tool execution begins |
| `TASK_COMPLETED` | Tool execution succeeds |
| `TASK_FAILED` | Tool execution fails |
| `TASK_RETRYING` | Retry after failure |
| `AGENT_SPAWNED` | New FluidAgent created |
| `AGENT_PHASE_TRANSITION` | Phase change |
| `AGENT_REAPED` | Agent destroyed |
| `MEMORY_PATTERN_LEARNED` | L2 pattern extracted |
| `MEMORY_STRATEGY_LEARNED` | L3 strategy discovered |
| `SYSTEM_STATUS` | Status request/shutdown |

### Subscription

```python
# Subscribe to specific event
fw.on(EventType.TASK_COMPLETED, handler)

# Subscribe to all events (for WebSocket streaming)
fw.on_event(lambda e: websocket.send(e.to_json()))
```

Event payloads are `frozendict` — immutable and thread-safe.

---

## Supervisor Tree

### Restart Policies

| Policy | Behavior |
|--------|----------|
| `ALWAYS` | Restart on any exit (normal or error) |
| `NEVER` | Let the worker die permanently |
| `ON_ERROR` | Restart on exception, not on normal completion |
| `TRANSIENT` | Restart only on abnormal exit |

### Backoff

Failed workers wait `10ms * restart_count` before retrying, up to `max_restarts` (default 3).

### Tree Structure

```python
root = Supervisor("pipeline")
root.add_worker(WorkerSpec("fetch", fetch_fn, phase=Phase.VAPOR))
root.add_worker(WorkerSpec("parse", parse_fn, phase=Phase.LIQUID))

validation = Supervisor("validators")
validation.add_worker(WorkerSpec("schema", validate_fn, phase=Phase.LIQUID))
validation.add_worker(WorkerSpec("sandbox", test_fn, phase=Phase.SOLID))

root.add_child_supervisor(validation)
result = await root.run_all()
```

Workers in the same supervisor run in parallel. Child supervisors run in parallel with their parent's workers.

---

## Self-Building

### Cycle

```
1. INTROSPECT  → Uses own tools (line_count, file_stats, glob_search) to analyze itself
2. DIAGNOSE    → Static analysis or Claude review of own source code
3. PROPOSE     → Generate new tool code following PFAA patterns
4. SANDBOX     → Execute generated code in an isolated subprocess (SOLID phase)
5. APPLY       → Write validated code to tools_generated.py
6. LEARN       → Record the cycle in persistent memory
```

### Proven Result

The engine generated a `codebase_search` tool (combining grep + glob with context lines), sandbox-tested it, applied it to its own codebase, then used the new tool to search its own source code — finding 56 `lazy import` patterns across 15 files.

---

## Server API

### WebSocket Protocol

Connect to `ws://host:port/ws/agent`:

```
Client → Server:
  {"type": "goal", "text": "analyze codebase"}
  {"type": "tool", "name": "compute", "args": ["sqrt(42)"]}
  {"type": "status"}
  {"type": "memory"}

Server → Client:
  {"type": "connected", "status": {...}}
  {"type": "event", "event_type": "TASK_COMPLETED", "data": {...}}
  {"type": "result", "goal_id": "...", "status": "COMPLETED", "subtasks": [...]}
  {"type": "tool_result", "tool": "compute", "result": {...}}
  {"type": "status", "status": {...}}
  {"type": "memory", "patterns": {...}, "strategies": {...}}
```

### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/status` | Framework status (tools, memory, uptime) |
| `GET` | `/api/tools` | List all 27 tools with phase + capabilities |
| `GET` | `/api/memory` | Learned patterns + strategies |
| `POST` | `/api/tool` | Execute single tool `{"name": "compute", "args": ["sqrt(42)"]}` |
| `POST` | `/api/goal` | Execute goal `{"text": "analyze codebase"}` |
| `GET` | `/api/checkpoints` | List saved goal checkpoints |

---

## Comparison with Agent Zero

| Feature | Agent Zero | PFAA |
|---------|-----------|------|
| Execution model | Sequential monologue loop (`while True`) | Parallel task DAG with scatter/gather |
| Agent spawn | ~2-5s (Docker + Python boot) | **6μs** (VAPOR coroutine) |
| Concurrency | `nest_asyncio` + `DeferredTask` threads | Native `asyncio.gather` + `ThreadPoolExecutor` + `ProcessPoolExecutor` |
| Isolation | All-or-nothing Docker container | 3 phases — choose per-task |
| Delegation | Flat `call_subordinate` (sequential) | Supervisor tree with restart policies |
| Memory | Vector DB embeddings only | 5-layer meta-learning (L1→L5) |
| Learning | None — static behavior | Epsilon-greedy exploration + L3 strategy discovery |
| Persistence | RAM only | SQLite WAL — survives restarts |
| Self-improvement | Manual tool development | Self-build loop (generate → test → apply) |
| Throughput | ~1 task/sec | **6,000+ tasks/sec** |
| Python version | 3.12 | **3.15** (lazy import, frozendict, kqueue) |
| Event streaming | Log-based | Typed EventBus with WebSocket streaming |
| Checkpoints | None | JSON checkpoint per goal — interrupt/resume |
| Frontend API | Custom WebSocket message loop | Standard FastAPI + WebSocket + REST |

---

## File Storage

```
~/.pfaa/
├── memory.db              SQLite WAL — persistent 5-layer memory
└── checkpoints/
    ├── goal-abc123.json   Checkpoint for each goal execution
    ├── goal-def456.json
    └── ...
```

---

## Dependencies

### Required
- Python 3.15.0a7+
- `typer` — CLI framework
- `rich` — Terminal formatting

### Optional
- `fastapi` + `uvicorn` — WebSocket/HTTP server
- Claude Code CLI — Claude bridge integration

### Standard Library (Python 3.15)
- `asyncio` — Event loop + coroutines
- `concurrent.futures` — ThreadPoolExecutor + ProcessPoolExecutor
- `sqlite3` — Persistent memory storage
- `frozendict` — Immutable configs (PEP 814)
- `lazy import` — Deferred module loading (PEP 810)
- `select.kqueue` — Event-driven subprocess on macOS
- `statistics` — L2 pattern extraction
- `hashlib` — Tool argument deduplication
- `subprocess` — SOLID phase execution
- `json` — Serialization
