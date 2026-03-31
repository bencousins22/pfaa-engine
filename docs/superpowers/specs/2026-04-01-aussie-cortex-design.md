# Aussie Cortex: Self-Improving Reinforcement Learning Hook System

**Date:** 2026-04-01
**Status:** Approved for implementation
**Scope:** 6 new Claude Code hooks, unified cortex processor, JMEM-native RL loop

---

## 1. Problem

The Aussie Agents system has 10 agents, 44 tools, and 6-layer JMEM memory, but no feedback loop between execution outcomes and future decisions. Agents spawn blind — no history of prior performance. Tool failures go unrecorded. Memory consolidation only happens manually. Python 3.15 enforcement fires on edit but not on external file changes.

## 2. Solution

A unified Python 3.15 cortex (`cortex.py`) that processes all hook events, stores outcomes in JMEM as L1 episodes, and lets the existing 6-layer promotion pipeline (Episode -> Concept -> Principle -> Skill -> Meta -> Emergent) evolve enforcement rules from experience. The cortex forms a closed reinforcement learning loop: events create memories, memories become rules, rules influence decisions, decisions create outcomes, outcomes reward or penalize the memories.

## 3. Architecture

### 3.1 System Diagram

```
Claude Code Hook Events
    |
    v
[Interest Gate] -- score < 0.1 --> skip
    |
    v  score >= 0.1
[Circuit Breaker] -- handler disabled --> observe only
    |
    v  handler enabled
[S1 Fast Path] -- JMEM L4 skill match, confidence > 0.9 --> decide
    |
    v  no match or low confidence
[S2 Full Path] -- JMEM recall + cross-agent + phase context --> decide
    |
    v
[Decision] -- observe | advise | block | rewrite
    |
    +---> JMEM Store (L1 episode + reward/penalize)
    +---> cortex_state.json (pressure, phase, errors)
    +---> JSON output to Claude Code
    |
    v  (when pressure >= threshold AND hours >= 1)
[Dream Cycle] -- consolidate -> extract_skills -> meta_learn
                  -> emergent -> decay -> self_assess -> suggest_hooks
```

### 3.2 Two Persistence Layers

| Layer | Purpose | Format | Speed |
|---|---|---|---|
| **JMEM** | Semantic memory: what did we learn? | 6-layer cognitive store with Q-learning | ~50ms |
| **cortex_state.json** | Operational state: where are we right now? | Single JSON file at `.claude/hooks/cortex_state.json` | <1ms |

JMEM stores episodes, concepts, principles, skills, meta-insights, and emergent patterns. cortex_state stores pressure counter, phase position, error counts, circuit breaker state, decision metrics, and cache timestamps.

### 3.3 Dual Persistence Rationale

JMEM is the wrong tool for transient operational counters (pressure, error counts). Writing "pressure = 7.5" as an L1 episode would drown JMEM in noise. cortex_state.json is a lightweight file (~500 bytes) read and written atomically on each invocation. It does not participate in Q-learning or promotion.

## 4. Hook Event Specifications

### 4.1 SubagentStart

**Trigger:** Any of the 10 Aussie agents spawns.
**Timeout:** 5 seconds.

**Processing:**
1. Recall this agent's performance history (limit=5, min_q=0.3).
2. Recall cross-agent findings relevant to the task via `recall_cross_namespace`.
3. Detect current coordinator phase (Research/Synthesis/Implementation/Verification).
4. Check dynamic L4 rules for blocking conditions.
5. Store L1 episode: `"{agent} started on {task_summary}"` with tags `[agent-start, {agent}, {domain}]`.

**Decision logic:**
- Prior memories avg Q > 0.7: ADVISE with success context.
- Prior memories avg Q < 0.4 AND failures >= 3: BLOCK with alternative agent suggestion.
- Otherwise: OBSERVE with cross-agent context injected as `additionalContext`.

**Coordinator phase injection:**
- Research phase: "Focus on gathering information, do not implement."
- Implementation phase: inject synthesized spec from prior research agents.
- Verification phase: inject what was implemented and what to validate.

### 4.2 SubagentStop

**Trigger:** Agent completes (success or failure).
**Timeout:** 10 seconds (heaviest JMEM workload).

**Processing (via TaskGroup for concurrency):**
1. Store L1 episode with outcome.
2. Recall matching SubagentStart episode for duration calculation.
3. Reward or penalize all recently recalled memories.

**Success path (reward_signal = +0.8):**
- Store episode: `"{agent} completed {task} in {duration}s -- success"`.
- `reward_recalled(+0.8)`.
- Every 10 successes: trigger `consolidate()`.
- Output: system message with agent name and duration.

**Failure path (reward_signal = -0.5):**
- Store episode: `"{agent} failed {task}: {error}"`.
- `reward_recalled(-0.5)`.
- Count recent failures (last hour) for same agent.
- If 3+ recent failures: store L2 Concept with routing rule JSON, output advisory.
- Every 5 failures: trigger `meta_learn()`.

### 4.3 PostToolUseFailure

**Trigger:** Any tool call fails.
**Timeout:** 5 seconds.

**Processing:**
1. Classify error: permission | timeout | not_found | unknown.
2. Store L1 episode: `"{tool} failed: {error_summary}"` with tags `[tool-failure, {tool}, {error_class}]`.
3. Recall prior failures for this tool (limit=5, min_q=0.0).
4. Penalize memories that recommended this tool usage (-0.3).

**Escalation:**
- 1 failure: OBSERVE.
- 2 failures (same error class): ADVISE with workaround if JMEM has one.
- 3+ failures (same error class): BLOCK tool, suggest alternative from JMEM.

### 4.4 FileChanged

**Trigger:** Watched files change externally.
**Matcher:** `*.py|*.pyi|settings.json|.claude/agents/*.md`
**Timeout:** 10 seconds.

**Processing for .py/.pyi files:**
1. Lazy-import AST analyzer (`analyzers/py315_ast.py`).
2. Parse file AST and scan for:
   - PEP 810: non-lazy imports of heavy modules (AST `Import` nodes).
   - PEP 814: UPPER_CASE dict assignments (AST `Assign` with `Name.id.isupper()`).
   - PEP 695: functions with TypeVar but no type parameters (AST `FunctionDef` with `type_params=[]`).
   - PEP 634: isinstance if/elif chains convertible to match/case.
3. Recall prior suggestions for this file path.
4. Filter: skip suggestions user previously ignored (Q < 0.3), boost acted-on (Q > 0.7).
5. Rank by confidence * prior_q.

**Auto-rewrite decision (all must be true):**
- All suggestions confidence > 0.9.
- All suggestions prior_q > 0.6 (user acted on similar before).
- Git working tree is clean.
- 5 or fewer suggestions (not a mass rewrite).

**Output:** System message with ranked suggestions. If auto-rewrite warranted, `additionalContext` priming Claude to apply the changes.

**Processing for settings.json:** System message noting config change.
**Processing for .claude/agents/*.md:** Store L1 episode noting agent definition update.

### 4.5 TaskCompleted

**Trigger:** A task is marked `completed`.
**Timeout:** 5 seconds.

**Processing:**
1. Store L1 episode: `"Task completed: {subject}"` with tags `[task-completed, {domain}]`.
2. `reward_recalled(+0.7)`.
3. Increment pressure counter.
4. Consolidation triggers: every 10 completions `consolidate()`, every 25 `meta_learn()`, every 50 `emergent_synthesis()`.

**Output:** None (silent reinforcement). This is the primary source of positive reward signal in the system.

### 4.6 UserPromptSubmit

**Trigger:** Every user message, before Claude processes it.
**Timeout:** 3 seconds (user is waiting).

**Processing:**
1. Fast exit: if prompt < 3 words, skip (score < 0.1).
2. Semantic search JMEM with prompt text (limit=3, min_q=0.6).
3. Latency gate: if recall takes > 150ms, skip.
4. Format memories as concise context: `"[LEVEL Q=X.X] content"`.
5. Store L1 episode tracking injection for later reward.

**Output:** `additionalContext` with relevant JMEM memories injected before Claude starts reasoning.

**Throttling:** Cache recall result for 30 seconds. If next prompt has > 50% keyword overlap with cached query, reuse cached result.

### 4.7 Stop (Enhanced)

**Trigger:** Claude finishes responding.
**Timeout:** 10 seconds.

**Processing:**
1. Existing: stop_scan.cjs for capability scanning.
2. New: Store session episode via JMEM (replaces jmem_store_episode.py).
3. New: Check if dream cycle should trigger.

**Dream cycle trigger conditions (both must be true):**
- Cognitive pressure >= threshold (default 10, tuned by L5 Meta).
- Hours since last dream >= 1.0.

**Dream cycle steps (sequential):**
1. `consolidate()` -- link related memories, promote high-Q.
2. `extract_skills()` -- harvest L4 enforcement rules from principles.
3. `meta_learn()` -- tune promotion thresholds and pressure threshold.
4. `emergent_synthesis()` -- cross-agent pattern discovery.
5. `decay_idle(24h)` -- prune stale memories.
6. `self_assess()` -- evaluate cortex accuracy, adjust intervention level.
7. `suggest_hook_evolution()` -- recommend settings.json changes.
8. Reset pressure to 0, update `last_dream_at`.

## 5. Decision Engine

### 5.1 Two-Stage Classification

**S1 (Fast Path, <10ms):** Check JMEM L4 skills loaded as frozen decision tables. If an exact pattern match exists with Q > 0.9, decide immediately. Dynamic rules are reloaded from JMEM every 60 seconds and cached as `frozendict` entries.

**S2 (Full Path, <200ms):** Full JMEM recall with event context. Cross-agent recall via `recall_cross_namespace`. Phase-aware context injection. Stores decision as L1 episode for future learning.

**Disagreement handling:** If S1 returns a decision but S2 disagrees, use S2 (more reasoning) with confidence reduced by 30%. Store the disagreement as an L1 episode tagged `[contested-decision, meta]` for meta-learning.

### 5.2 Confidence Thresholds

| Action | Min Confidence | Additional Requirements |
|---|---|---|
| observe | 0.0 | None |
| advise | 0.5 | None |
| block | 0.85 | Agent has 3+ recent failures |
| rewrite | 0.9 | Clean git tree AND user acted on similar before |

Blocking defaults to ADVISE until the pattern has been reinforced through real outcomes. The cortex earns the right to block through demonstrated accuracy.

### 5.3 Escalation Ladder

All enforcement starts at OBSERVE. Repeated patterns escalate: OBSERVE -> ADVISE -> BLOCK. The escalation is Q-driven: a single failure barely moves Q, but 3+ compound into a signal that gets promoted to L3 Principle, then L4 Skill blocking rule. If the pattern stops being true (agent improves), Q decays and the block lifts automatically.

## 6. Adaptive Attention

### 6.1 Interest Scoring

Every event receives an interest score (0.0-1.0) that determines processing depth:

| Event Pattern | Base Score |
|---|---|
| AgentStop failure | 1.0 |
| AgentStart with prior failures | 0.9 |
| FileChanged .py | 0.8 |
| PromptSubmit substantial (>10 words) | 0.7 |
| AgentStop success | 0.5 |
| TaskCompleted | 0.3 |
| PromptSubmit trivial (<=3 words) | 0.05 |

Novelty boost: events the cortex hasn't seen recently get score * 1.4 (capped at 1.0).

### 6.2 Processing Tiers

| Score Range | Processing | Budget |
|---|---|---|
| < 0.1 | Skip entirely | 0ms |
| 0.1 - 0.3 | Store L1 only | <20ms |
| 0.3 - 0.6 | S1 fast check + store | <50ms |
| 0.6 - 0.8 | S1 + S2 full analysis | <200ms |
| 0.8 - 1.0 | S1 + S2 + cross-agent + dream check | <500ms |

The interest baseline is stored in cortex_state.json and adjusted by self-assessment: if the cortex is wrong too often, baseline rises (less intervention); if accurate, baseline drops (more intervention).

## 7. Self-Improvement Systems

### 7.1 Self-Evaluation

The cortex tracks its own accuracy:
- `total_decisions`: lifetime decision count.
- `correct_blocks`: blocks not overridden by user (validated when agent succeeds on alternative path).
- `overridden_blocks`: blocks where user re-spawned the same agent anyway (detected via subsequent SubagentStart).

Block accuracy = correct / (correct + overridden). During dream cycle, self-assessment adjusts behavior:
- Accuracy < 50%: dial back to advise-only, raise interest baseline.
- Accuracy > 85%: become more proactive, lower interest baseline.

### 7.2 Self-Evolving Rules

JMEM L4 skills become S1 fast-path rules. The promotion pipeline generates these automatically:
- L1 Episode: "aussie-tdd failed on auth module"
- L2 Concept (Q>=0.65, ret>=2): "aussie-tdd struggles with auth tasks"
- L3 Principle (Q>=0.75, ret>=4): "route auth tasks to aussie-security"
- L4 Skill (Q>=0.92, ret>=6): `{"agent":"aussie-tdd","domain":"auth","action":"block","route_to":"aussie-security"}`

The L4 skill is loaded as a frozendict decision rule. The cortex's behavior evolves without code changes.

### 7.3 Self-Suggesting Hook Evolution

During dream cycle, the cortex analyzes its own event history and recommends settings.json changes:
- Hot files that should be added to FileChanged matcher.
- Underused hooks that could be removed (avg interest < 0.2 over 20+ events).
- Tool failure patterns that warrant dedicated handlers.

Suggestions are output as a system message during the Stop hook.

### 7.4 Cognitive Pressure Self-Tuning

The pressure threshold that triggers dream cycles is stored as an L5 Meta memory and adjusted by meta_learn:
- Productive cycles (many promotions, skills extracted): lower threshold (dream more often).
- Empty cycles (nothing promoted): raise threshold (dream less often).
- Default: 10. Range: 5-25.

## 8. Graceful Degradation

Four degradation levels, each strictly simpler than the last:

| Level | State | Behavior |
|---|---|---|
| 1. Full | JMEM + state + analysis | Normal operation |
| 2. State-only | JMEM down, state file works | Use cached L4 rules from last load |
| 3. Static | State file broken | Pure match/case, no persistence |
| 4. Silent | Everything broken | Return empty Decision, never crash |

The cortex catches all exceptions and degrades. It never throws to Claude Code's hook pipeline.

### 8.1 Circuit Breaker

Per-handler error tracking in cortex_state.json. 3 consecutive errors for a single handler type auto-disables that handler. A subsequent successful invocation re-enables it. Disabled handlers return observe-only decisions.

## 9. Context-Sensitive Project Personality

On first invocation, the cortex scans the project and generates a frozen profile:

| Signal | Adjustment |
|---|---|
| > 20 .py files | Aggressive Py3.15 enforcement |
| > 10 test files | Lower blocking threshold (trust the tests) |
| Security agent present | Emphasize security-related context injection |
| FreqTrade strategy present | Enable overfitting detection context |
| More .py than .ts | Primary language = Python |

Profile is cached in cortex_state.json and regenerated when project structure changes (detected via FileChanged on directory-level signals).

## 10. Python 3.15 Features (All Load-Bearing)

| Feature | Architectural Role |
|---|---|
| PEP 810 `lazy import` | Adaptive module loading: AST only for FileChanged .py, threading only for free-threading, JMEM only when storing. Startup <10ms for simple events. |
| PEP 814 `frozendict` | Immutable decision tables from JMEM L4. Hashable event keys for dedup sets. Thread-safe policy cache. |
| PEP 634 `match/case` | Core dispatch mechanism. Policy-as-code with guard clauses. AST pattern matching in analyzer. |
| PEP 695 type params | Generic event handlers: `def handle[E: HookEvent](event: E) -> Decision[E]`. Type-safe per-event decisions. |
| Free-threading | True parallel AST analysis when multiple .py files change. GIL detection via `sys._is_gil_enabled()`. |
| `asyncio.TaskGroup` | Concurrent JMEM operations (recall + store + reward) per event. |
| `except*` / ExceptionGroup | Structured error handling in degradation chain. Per-operation failure tracking. |
| `@dataclass(frozen=True, slots=True)` | Immutable, memory-efficient, hashable event types. |

The cortex is a living validation of Python 3.15: it uses every feature it enforces. If the cortex runs correctly, those features are proven to work.

## 11. File Structure

```
.claude/hooks/
  cortex.py               # Unified RL cortex (~400 lines, Python 3.15)
  cortex_state.json        # Operational state (auto-generated, gitignored)
  analyzers/
    py315_ast.py           # Deep AST Py3.15 analyzer (lazy imported)
  banner.cjs               # SessionStart display (unchanged)
  statusline.cjs           # Status line (unchanged)
  jmem_recall.py           # SessionStart bootstrap recall (kept)
```

`cortex.py` replaces `jmem_store_episode.py` (absorbed into Stop handler). `jmem_recall.py` stays for SessionStart bootstrap; `UserPromptSubmit` handles richer per-prompt recall.

## 12. settings.json Hook Configuration

All paths are absolute to the project root (`/Users/borris/Desktop/pfaa-engine`), abbreviated here as `$ROOT` for readability:

```json
{
  "SessionStart": [
    {"hooks": [{"type": "command", "command": "node $ROOT/.claude/hooks/banner.cjs"}]},
    {"hooks": [{"type": "command", "command": "python3 $ROOT/.claude/hooks/jmem_recall.py", "timeout": 5}]}
  ],
  "UserPromptSubmit": [
    {"hooks": [{"type": "command", "command": "python3 $ROOT/.claude/hooks/cortex.py UserPromptSubmit", "timeout": 3}]}
  ],
  "SubagentStart": [
    {"hooks": [{"type": "command", "command": "python3 $ROOT/.claude/hooks/cortex.py SubagentStart", "timeout": 5}]}
  ],
  "SubagentStop": [
    {"hooks": [{"type": "command", "command": "python3 $ROOT/.claude/hooks/cortex.py SubagentStop", "timeout": 10}]}
  ],
  "PostToolUseFailure": [
    {"hooks": [{"type": "command", "command": "python3 $ROOT/.claude/hooks/cortex.py PostToolUseFailure", "timeout": 5}]}
  ],
  "FileChanged": [
    {"matcher": "*.py|*.pyi|settings.json|.claude/agents/*.md",
     "hooks": [{"type": "command", "command": "python3 $ROOT/.claude/hooks/cortex.py FileChanged", "timeout": 10}]}
  ],
  "TaskCompleted": [
    {"hooks": [{"type": "command", "command": "python3 $ROOT/.claude/hooks/cortex.py TaskCompleted", "timeout": 5}]}
  ],
  "Stop": [
    {"hooks": [{"type": "command", "command": "node $ROOT/.claude/hooks/stop_scan.cjs"}]},
    {"hooks": [{"type": "command", "command": "python3 $ROOT/.claude/hooks/cortex.py Stop", "timeout": 10}]}
  ]
}
```

Existing PreToolUse (secret detection, sensitive file) and PostToolUse (TypeScript check, console.log, Py3.15 string-match) hooks remain unchanged. The cortex supplements them; it does not replace them.

## 13. Testing Strategy

### Unit Tests
- Each event handler tested in isolation with mock JMEM engine.
- Interest scoring verified for all event type combinations.
- Circuit breaker: verify disable after 3 errors, re-enable on success.
- Degradation chain: verify each level triggers when appropriate.
- Decision confidence thresholds: verify escalation ladder.

### Integration Tests
- Full event flow: SubagentStart -> SubagentStop -> reward -> consolidate.
- Dream cycle: pressure accumulation -> threshold -> full cycle execution.
- FileChanged: AST analysis -> suggestion ranking -> output formatting.
- UserPromptSubmit: recall -> inject -> verify additionalContext format.

### Self-Validation
- The cortex processes its own hook events (Stop, FileChanged on cortex.py).
- If the cortex's own Py3.15 features are detected as missing by the analyzer, that is a test failure.

## 14. Rollout Plan

**Phase 1: Foundation**
- Implement cortex.py with event types, entry point, cortex_state.json.
- Implement SubagentStart and SubagentStop handlers (core RL loop).
- Implement circuit breaker and degradation chain.

**Phase 2: Analysis**
- Implement FileChanged handler with AST analyzer.
- Implement PostToolUseFailure handler with escalation.
- Implement TaskCompleted handler (silent reinforcement).

**Phase 3: Intelligence**
- Implement UserPromptSubmit handler (per-prompt memory injection).
- Implement two-stage S1/S2 decision engine with dynamic L4 rules.
- Implement interest scoring and adaptive attention.

**Phase 4: Self-Improvement**
- Implement dream cycle with pressure tracking.
- Implement self-assessment and accuracy tracking.
- Implement hook evolution suggestions.
- Implement context-sensitive project personality.

Each phase is independently deployable. Phase 1 alone provides value (agent performance tracking + RL rewards). Each subsequent phase adds intelligence.

## 15. Success Criteria

- Cortex startup < 80ms for trivial events (interest < 0.3), including ~40ms Python interpreter startup.
- Cortex full analysis < 500ms for complex events.
- Block accuracy > 70% after 50+ decisions (measured by self-assessment).
- Dream cycles produce at least 1 L4 skill per 100 events.
- Zero crashes in Claude Code's hook pipeline (degradation chain holds).
- AST analyzer catches patterns string-matching misses (nested imports, conditional TypeVar, dict comprehensions).

## 16. Errata and Refinements (Post-Review)

### 16.1 Python Startup Cost

Every hook invocation runs `python3 cortex.py`, incurring ~40ms Python interpreter startup. This is unavoidable without a persistent daemon. Latency budgets throughout this spec include this baseline. The "skip entirely" tier for interest < 0.1 still costs ~40ms (Python starts, cortex reads stdin, checks interest, exits). Use `python3 -S` (skip site imports) to reduce to ~20ms where possible.

### 16.2 cortex_state.json Race Condition

Two hooks firing simultaneously (e.g., SubagentStop + TaskCompleted) could both read-modify-write cortex_state.json, with the second clobbering the first. Solution: atomic writes via temp file + `os.replace()`:

```python
def save(self) -> None:
    tmp = CORTEX_STATE_PATH.with_suffix('.tmp')
    tmp.write_text(json.dumps(asdict(self), default=str))
    os.replace(str(tmp), str(CORTEX_STATE_PATH))  # Atomic on POSIX
```

For counters (pressure, error counts), accept eventual consistency — off-by-one is acceptable. For boolean flags (disabled_handlers), the last writer wins, which is correct because the most recent error state is the most relevant.

### 16.3 Dream Cycle Timeout

The 7-step dream cycle may exceed the 10s Stop hook timeout. Solution: two-phase dream.

**Phase A (in Stop hook, <5s):** Run the lightweight steps:
- `consolidate()` (~1-2s)
- `decay_idle()` (~0.5s)
- Store `dream_pending = true` if heavier steps needed

**Phase B (in next SessionStart, <8s):** Run the heavy steps if `dream_pending`:
- `extract_skills()`
- `meta_learn()`
- `emergent_synthesis()`
- `self_assess()`
- `suggest_hook_evolution()`
- Set `dream_pending = false`

This keeps Stop fast and defers expensive analysis to session startup where latency is more forgiving.

### 16.4 Cross-Namespace Recall

The current JMEM MCP server uses a single namespace (`claude-code`). `recall_cross_namespace` would return nothing useful. Instead, use tag-based filtering on regular `recall`:

```python
# Instead of recall_cross_namespace:
results = await engine.recall(
    f"{task_description}",
    limit=5, min_q=0.3
)
# Filter for memories tagged with other agents:
cross = [m for m in results if any(t in AGENT_NAMES for t in m.tags) and agent not in m.tags]
```

All agent memories share one namespace but are tagged with their source agent. Regular recall with tag filtering achieves the same cross-agent synthesis.

### 16.5 FileChanged Per-File Invocation

Claude Code fires FileChanged once per changed file. If `git pull` lands 15 `.py` files, 15 separate `python3 cortex.py FileChanged` processes spawn. Each analyzes one file independently. The free-threading optimization for batch analysis does NOT apply (threads can't span processes).

Remove the free-threading FileChanged claim from Section 10. Free-threading is still load-bearing for concurrent JMEM TaskGroup operations within a single invocation.

### 16.6 UserPromptSubmit Cache

The 30-second recall cache cannot live in-process (each invocation is a new process). Store the cache in cortex_state.json:

```python
# In CortexState:
last_prompt_keywords: list[str] = []
last_prompt_recall: list[dict] = []   # Serialized memory summaries
last_prompt_at: float = 0.0

# In handler:
if time() - state.last_prompt_at < 30:
    overlap = len(set(keywords) & set(state.last_prompt_keywords)) / max(len(keywords), 1)
    if overlap > 0.5:
        return Decision(additional_context=format_cached(state.last_prompt_recall))
```

### 16.7 JMEM Engine Import

The cortex MUST use the `jmem-mcp-server/` engine, not the `python/` engine. They have different APIs:

| Feature | `jmem-mcp-server/jmem/engine.py` | `python/jmem/engine.py` |
|---|---|---|
| `recall(limit=, min_q=)` | Yes | No (uses `top_k=`) |
| `recall_cross_namespace()` | Yes | No |
| `extract_skills()` | Yes | Differs |
| `meta_learn()` | Yes | Differs |
| `emergent_synthesis()` | Yes | Differs |
| `reward_recalled()` | Yes | Differs |
| `decay_idle()` | Yes | Differs |

Import path: `sys.path.insert(0, "/Users/borris/Desktop/pfaa-engine/jmem-mcp-server")`.

### 16.8 Hook Payload Validation

Claude Code's stdin JSON schema varies by hook event. The cortex must validate gracefully:

```python
def parse_event(event_type: str, payload: dict) -> HookEvent:
    match event_type:
        case "SubagentStart":
            return AgentStartEvent(
                type=event_type,
                timestamp=time(),
                raw=frozendict(payload),
                agent=payload.get("agent_name", payload.get("name", "unknown")),
                task=payload.get("task", payload.get("prompt", "")[:200]),
            )
        # ... other cases with .get() defaults for all fields
```

Every field access uses `.get()` with a default. Missing fields degrade functionality but never crash.

### 16.9 Memory Volume Control

The cortex stores L1 episodes on most events. At high activity (50+ events/session), this could flood JMEM. Controls:

- **Dedup window:** Before storing, check cortex_state for last 5 episode hashes. Skip if duplicate content hash.
- **Rate limit:** Max 30 episodes per session. After that, only store high-interest events (score > 0.6).
- **Decay handles cleanup:** `decay_idle(24h)` in the dream cycle prunes stale episodes with low Q.

### 16.10 Multi-Project Portability

Replace hardcoded paths with environment variable detection:

```python
PROJECT_ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR",
    os.environ.get("PWD",
    "/Users/borris/Desktop/pfaa-engine"))
)
JMEM_PATH = PROJECT_ROOT / "jmem-mcp-server"
STATE_PATH = PROJECT_ROOT / ".claude" / "hooks" / "cortex_state.json"
```

### 16.11 Coordinator Phase Detection

The cortex infers the current phase from agent types being spawned:

| Agents spawning | Detected phase |
|---|---|
| aussie-researcher, aussie-planner, aussie-architect | RESEARCH |
| pfaa-lead (solo) | SYNTHESIS |
| aussie-tdd, pfaa-rewriter, aussie-deployer | IMPLEMENTATION |
| pfaa-validator, aussie-security | VERIFICATION |
| Mixed or unknown | IDLE (no phase injection) |

Phase advances when SubagentStop fires for the last agent in the current phase group. Stored in cortex_state.json as `phase: str`.

### 16.12 Error Classification

Expanded from 4 to 7 categories for richer PostToolUseFailure handling:

```python
ERROR_PATTERNS = {
    "permission": ["permission", "denied", "forbidden", "unauthorized"],
    "timeout": ["timeout", "timed out", "deadline exceeded"],
    "not_found": ["not found", "no such file", "does not exist", "enoent"],
    "syntax": ["syntax", "parse error", "unexpected token", "invalid"],
    "network": ["connection", "network", "econnrefused", "dns"],
    "resource": ["out of memory", "disk full", "too many open files"],
    "unknown": [],  # Fallback
}
```
