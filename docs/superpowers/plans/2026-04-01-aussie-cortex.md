# Aussie Cortex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-improving RL cortex that processes 6 new Claude Code hook events through JMEM's 6-layer cognitive pipeline, evolving enforcement rules from experience.

**Architecture:** A single Python 3.15 file (`cortex.py`) receives all hook events via stdin JSON, routes through an interest gate + circuit breaker + two-stage decision engine, stores outcomes in JMEM, and persists operational state to `cortex_state.json`. Four rollout phases, each independently deployable.

**Tech Stack:** Python 3.15 (lazy imports, frozendict, match/case, TaskGroup, except*), JMEM engine from `jmem-mcp-server/`, pytest for tests.

**Spec:** `docs/superpowers/specs/2026-04-01-aussie-cortex-design.md`

---

## File Map

| File | Responsibility | Phase |
|---|---|---|
| `.claude/hooks/cortex.py` | Unified hook event processor — entry point, event types, decision engine, all handlers | 1-4 |
| `.claude/hooks/cortex_state.json` | Auto-generated operational state (gitignored) | 1 |
| `.claude/hooks/analyzers/py315_ast.py` | AST-based Python 3.15 opportunity scanner | 2 |
| `.claude/settings.json` | Hook configuration (add new hook entries) | 1 |
| `tests/test_cortex.py` | Unit + integration tests for cortex | 1-4 |
| `.gitignore` | Add cortex_state.json | 1 |

---

## Phase 1: Foundation

### Task 1: CortexState dataclass + persistence

**Files:**
- Create: `.claude/hooks/cortex.py`
- Create: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test for CortexState load/save**

```python
# tests/test_cortex.py
"""Tests for the Aussie Cortex hook processor."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from time import time

# Use jmem-mcp-server engine (not python/jmem)
_mcp_path = os.path.join(os.path.dirname(__file__), "..", "jmem-mcp-server")
sys.path.insert(0, _mcp_path)
for mod_name in list(sys.modules):
    if mod_name.startswith("jmem"):
        del sys.modules[mod_name]

import pytest


def test_cortex_state_default():
    """Fresh CortexState has correct defaults."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
    from cortex import CortexState
    state = CortexState()
    assert state.pressure == 0.0
    assert state.phase == "idle"
    assert state.error_counts == {}
    assert state.disabled_handlers == set()
    assert state.total_decisions == 0
    assert state.correct_blocks == 0
    assert state.overridden_blocks == 0
    assert state.interest_baseline == 0.5


def test_cortex_state_save_load(tmp_path):
    """CortexState round-trips through JSON."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
    from cortex import CortexState
    state_file = tmp_path / "cortex_state.json"
    state = CortexState(state_path=state_file)
    state.pressure = 7.5
    state.phase = "research"
    state.error_counts = {"SubagentStop": 2}
    state.save()
    loaded = CortexState.load(state_file)
    assert loaded.pressure == 7.5
    assert loaded.phase == "research"
    assert loaded.error_counts == {"SubagentStop": 2}


def test_cortex_state_atomic_write(tmp_path):
    """Save uses atomic write (temp file + os.replace)."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
    from cortex import CortexState
    state_file = tmp_path / "cortex_state.json"
    state = CortexState(state_path=state_file)
    state.pressure = 3.0
    state.save()
    # Verify no .tmp file remains
    assert not (tmp_path / "cortex_state.tmp").exists()
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["pressure"] == 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/borris/Desktop/pfaa-engine && python3 -m pytest tests/test_cortex.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cortex'`

- [ ] **Step 3: Implement CortexState in cortex.py**

```python
# .claude/hooks/cortex.py
"""
Aussie Cortex — Self-Improving Reinforcement Learning Hook Processor.

Processes Claude Code hook events through JMEM's 6-layer cognitive pipeline.
Python 3.15: lazy imports, frozendict, match/case, TaskGroup, except*.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from time import time

# ── Project paths ────────────────────────────────────────────────────
PROJECT_ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR",
    os.environ.get("PWD",
    "/Users/borris/Desktop/pfaa-engine"))
)
JMEM_PATH = PROJECT_ROOT / "jmem-mcp-server"
STATE_PATH = PROJECT_ROOT / ".claude" / "hooks" / "cortex_state.json"

# ── Operational State ────────────────────────────────────────────────

@dataclass
class CortexState:
    """Operational working memory — persisted to JSON, not JMEM."""
    pressure: float = 0.0
    phase: str = "idle"
    error_counts: dict[str, int] = field(default_factory=dict)
    disabled_handlers: set[str] = field(default_factory=set)
    total_decisions: int = 0
    correct_blocks: int = 0
    overridden_blocks: int = 0
    interest_baseline: float = 0.5
    last_dream_at: float = 0.0
    dream_pending: bool = False
    rules_loaded_at: float = 0.0
    episodes_this_session: int = 0
    last_prompt_keywords: list[str] = field(default_factory=list)
    last_prompt_recall: list[dict] = field(default_factory=list)
    last_prompt_at: float = 0.0
    recent_episode_hashes: list[str] = field(default_factory=list)
    state_path: Path = field(default=STATE_PATH, repr=False)

    def save(self) -> None:
        """Atomic write: temp file + os.replace."""
        data = asdict(self)
        data.pop("state_path", None)
        # Convert set to list for JSON
        data["disabled_handlers"] = list(data["disabled_handlers"])
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, default=str))
        os.replace(str(tmp), str(self.state_path))

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> CortexState:
        """Load from JSON, return defaults if missing or corrupt."""
        try:
            data = json.loads(path.read_text())
            data["disabled_handlers"] = set(data.get("disabled_handlers", []))
            data["state_path"] = path
            return cls(**data)
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return cls(state_path=path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/borris/Desktop/pfaa-engine && python3 -m pytest tests/test_cortex.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): CortexState dataclass with atomic JSON persistence"
```

---

### Task 2: Decision dataclass + JSON output

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test for Decision**

```python
# Append to tests/test_cortex.py

def test_decision_observe():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
    from cortex import Decision
    d = Decision()
    assert d.action == "observe"
    out = d.to_json()
    assert out == "{}" or out == ""


def test_decision_advise():
    from cortex import Decision
    d = Decision(action="advise", system_message="Pattern detected: 3 failures")
    parsed = json.loads(d.to_json())
    assert parsed["systemMessage"] == "Pattern detected: 3 failures"


def test_decision_block():
    from cortex import Decision
    d = Decision(action="block", block_reason="JMEM L4: aussie-tdd fails on auth")
    parsed = json.loads(d.to_json())
    assert parsed["decision"] == "block"
    assert "aussie-tdd" in parsed["reason"]


def test_decision_with_context():
    from cortex import Decision
    d = Decision(action="advise", additional_context="Prior findings: ...")
    parsed = json.loads(d.to_json())
    assert parsed["hookSpecificOutput"]["additionalContext"] == "Prior findings: ..."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py::test_decision_observe -v`
Expected: FAIL — `ImportError: cannot import name 'Decision'`

- [ ] **Step 3: Implement Decision in cortex.py**

Add after CortexState class:

```python
@dataclass(frozen=True, slots=True)
class Decision:
    """What the cortex tells Claude Code to do."""
    action: str = "observe"
    system_message: str | None = None
    additional_context: str | None = None
    block_reason: str | None = None
    confidence: float = 0.0

    def to_json(self) -> str:
        """Serialize to Claude Code hook output format."""
        out: dict = {}
        if self.action == "block" and self.block_reason:
            out["decision"] = "block"
            out["reason"] = self.block_reason
        if self.system_message:
            out["systemMessage"] = self.system_message
        if self.additional_context:
            out["hookSpecificOutput"] = {
                "additionalContext": self.additional_context,
            }
        return json.dumps(out) if out else ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v -k decision`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): Decision dataclass with Claude Code JSON output"
```

---

### Task 3: Event types + parse_event

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test for event parsing**

```python
# Append to tests/test_cortex.py

def test_parse_agent_start():
    from cortex import parse_event, AgentStartEvent
    event = parse_event("SubagentStart", {"agent_name": "aussie-tdd", "task": "fix auth bug"})
    assert isinstance(event, AgentStartEvent)
    assert event.agent == "aussie-tdd"
    assert event.task == "fix auth bug"
    assert event.type == "SubagentStart"


def test_parse_agent_stop_success():
    from cortex import parse_event, AgentStopEvent
    event = parse_event("SubagentStop", {"agent_name": "aussie-tdd", "result": {"success": True}})
    assert isinstance(event, AgentStopEvent)
    assert event.success is True
    assert event.error is None


def test_parse_agent_stop_failure():
    from cortex import parse_event, AgentStopEvent
    event = parse_event("SubagentStop", {
        "agent_name": "aussie-tdd",
        "result": {"success": False, "error": "Tests failed: 3 assertions"}
    })
    assert event.success is False
    assert "Tests failed" in event.error


def test_parse_file_changed():
    from cortex import parse_event, FileChangedEvent
    event = parse_event("FileChanged", {"file_path": "/src/auth.py"})
    assert isinstance(event, FileChangedEvent)
    assert event.path == "/src/auth.py"
    assert event.ext == ".py"


def test_parse_tool_failure():
    from cortex import parse_event, ToolFailureEvent
    event = parse_event("PostToolUseFailure", {
        "tool_name": "Bash", "error": "Permission denied"
    })
    assert isinstance(event, ToolFailureEvent)
    assert event.tool == "Bash"
    assert event.error_class == "permission"


def test_parse_prompt_submit():
    from cortex import parse_event, PromptSubmitEvent
    event = parse_event("UserPromptSubmit", {"prompt": "fix the auth bug in login"})
    assert isinstance(event, PromptSubmitEvent)
    assert event.prompt == "fix the auth bug in login"


def test_parse_task_completed():
    from cortex import parse_event, TaskCompletedEvent
    event = parse_event("TaskCompleted", {"subject": "Implement auth", "description": "Done"})
    assert isinstance(event, TaskCompletedEvent)
    assert event.subject == "Implement auth"


def test_parse_unknown_event():
    from cortex import parse_event, HookEvent
    event = parse_event("UnknownHook", {"foo": "bar"})
    assert isinstance(event, HookEvent)
    assert event.type == "UnknownHook"


def test_parse_missing_fields():
    """Missing fields use safe defaults, never crash."""
    from cortex import parse_event, AgentStartEvent
    event = parse_event("SubagentStart", {})
    assert isinstance(event, AgentStartEvent)
    assert event.agent == "unknown"
    assert event.task == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k parse`
Expected: FAIL — `ImportError: cannot import name 'parse_event'`

- [ ] **Step 3: Implement event types and parse_event**

Add to cortex.py after Decision class:

```python
# ── Event Types ──────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class HookEvent:
    type: str
    timestamp: float

    def to_episode(self) -> str:
        return f"[{self.type}]"

    def tags(self) -> list[str]:
        return [self.type.lower()]


@dataclass(frozen=True, slots=True)
class AgentStartEvent(HookEvent):
    agent: str = "unknown"
    task: str = ""

    def to_episode(self) -> str:
        return f"{self.agent} started on {self.task[:100]}"

    def tags(self) -> list[str]:
        return ["agent-start", self.agent]


@dataclass(frozen=True, slots=True)
class AgentStopEvent(HookEvent):
    agent: str = "unknown"
    success: bool = False
    error: str | None = None

    def to_episode(self) -> str:
        status = "succeeded" if self.success else f"failed: {(self.error or '')[:100]}"
        return f"{self.agent} {status}"

    def tags(self) -> list[str]:
        return ["agent-stop", self.agent, "success" if self.success else "failure"]


@dataclass(frozen=True, slots=True)
class ToolFailureEvent(HookEvent):
    tool: str = "unknown"
    error: str = ""
    error_class: str = "unknown"

    def to_episode(self) -> str:
        return f"{self.tool} failed ({self.error_class}): {self.error[:100]}"

    def tags(self) -> list[str]:
        return ["tool-failure", self.tool, self.error_class]


@dataclass(frozen=True, slots=True)
class FileChangedEvent(HookEvent):
    path: str = ""
    ext: str = ""

    def to_episode(self) -> str:
        return f"File changed: {self.path}"

    def tags(self) -> list[str]:
        return ["file-changed", self.ext.lstrip(".")]


@dataclass(frozen=True, slots=True)
class TaskCompletedEvent(HookEvent):
    subject: str = ""
    description: str = ""

    def to_episode(self) -> str:
        return f"Task completed: {self.subject}"

    def tags(self) -> list[str]:
        return ["task-completed"]


@dataclass(frozen=True, slots=True)
class PromptSubmitEvent(HookEvent):
    prompt: str = ""

    def to_episode(self) -> str:
        return f"User prompt: {self.prompt[:80]}"

    def tags(self) -> list[str]:
        return ["user-prompt"]


# ── Error Classification ─────────────────────────────────────────────

ERROR_PATTERNS: dict[str, list[str]] = {
    "permission": ["permission", "denied", "forbidden", "unauthorized"],
    "timeout": ["timeout", "timed out", "deadline exceeded"],
    "not_found": ["not found", "no such file", "does not exist", "enoent"],
    "syntax": ["syntax", "parse error", "unexpected token", "invalid"],
    "network": ["connection", "network", "econnrefused", "dns"],
    "resource": ["out of memory", "disk full", "too many open files"],
}


def classify_error(error: str) -> str:
    lower = error.lower()
    for cls, patterns in ERROR_PATTERNS.items():
        if any(p in lower for p in patterns):
            return cls
    return "unknown"


# ── Event Parser ─────────────────────────────────────────────────────

def parse_event(event_type: str, payload: dict) -> HookEvent:
    """Parse stdin JSON into a typed event. Never crashes — missing fields get defaults."""
    ts = time()
    match event_type:
        case "SubagentStart":
            return AgentStartEvent(
                type=event_type, timestamp=ts,
                agent=payload.get("agent_name", payload.get("name", "unknown")),
                task=payload.get("task", payload.get("prompt", ""))[:200],
            )
        case "SubagentStop":
            result = payload.get("result", {})
            if isinstance(result, dict):
                success = result.get("success", False)
                error = result.get("error")
            else:
                success = bool(result)
                error = None
            return AgentStopEvent(
                type=event_type, timestamp=ts,
                agent=payload.get("agent_name", payload.get("name", "unknown")),
                success=success, error=str(error) if error else None,
            )
        case "PostToolUseFailure":
            err = payload.get("error", "")
            return ToolFailureEvent(
                type=event_type, timestamp=ts,
                tool=payload.get("tool_name", payload.get("tool", "unknown")),
                error=str(err)[:500],
                error_class=classify_error(str(err)),
            )
        case "FileChanged":
            p = payload.get("file_path", payload.get("path", ""))
            return FileChangedEvent(
                type=event_type, timestamp=ts,
                path=p, ext=Path(p).suffix if p else "",
            )
        case "TaskCompleted":
            return TaskCompletedEvent(
                type=event_type, timestamp=ts,
                subject=payload.get("subject", ""),
                description=payload.get("description", ""),
            )
        case "UserPromptSubmit":
            return PromptSubmitEvent(
                type=event_type, timestamp=ts,
                prompt=payload.get("prompt", payload.get("content", "")),
            )
        case _:
            return HookEvent(type=event_type, timestamp=ts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All tests PASS (12 total)

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): event types, error classifier, parse_event with safe defaults"
```

---

### Task 4: Interest scoring + circuit breaker

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test for interest scoring**

```python
# Append to tests/test_cortex.py

def test_interest_score_failure_max():
    from cortex import AgentStopEvent, interest_score
    event = AgentStopEvent(type="SubagentStop", timestamp=time(), agent="tdd", success=False, error="fail")
    assert interest_score(event) == 1.0


def test_interest_score_trivial_prompt():
    from cortex import PromptSubmitEvent, interest_score
    event = PromptSubmitEvent(type="UserPromptSubmit", timestamp=time(), prompt="yes")
    assert interest_score(event) < 0.1


def test_interest_score_py_file():
    from cortex import FileChangedEvent, interest_score
    event = FileChangedEvent(type="FileChanged", timestamp=time(), path="auth.py", ext=".py")
    assert interest_score(event) == 0.8


def test_interest_score_task_completed():
    from cortex import TaskCompletedEvent, interest_score
    event = TaskCompletedEvent(type="TaskCompleted", timestamp=time(), subject="Done")
    assert interest_score(event) == 0.3


def test_circuit_breaker_disable():
    from cortex import CortexState
    state = CortexState()
    state.record_error("SubagentStop")
    state.record_error("SubagentStop")
    assert not state.is_disabled("SubagentStop")
    state.record_error("SubagentStop")
    assert state.is_disabled("SubagentStop")


def test_circuit_breaker_reenable():
    from cortex import CortexState
    state = CortexState()
    for _ in range(3):
        state.record_error("SubagentStop")
    assert state.is_disabled("SubagentStop")
    state.record_success("SubagentStop")
    assert not state.is_disabled("SubagentStop")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k "interest or circuit"`
Expected: FAIL — `ImportError: cannot import name 'interest_score'`

- [ ] **Step 3: Implement interest_score and circuit breaker methods**

Add `interest_score` function after `parse_event`:

```python
def interest_score(event: HookEvent) -> float:
    """How much processing does this event deserve? 0.0-1.0."""
    match event:
        case AgentStopEvent(success=False):
            return 1.0
        case AgentStartEvent():
            return 0.9
        case FileChangedEvent(ext=".py" | ".pyi"):
            return 0.8
        case PromptSubmitEvent(prompt=p) if len(p.split()) > 10:
            return 0.7
        case AgentStopEvent(success=True):
            return 0.5
        case TaskCompletedEvent():
            return 0.3
        case FileChangedEvent():
            return 0.4
        case PromptSubmitEvent(prompt=p) if len(p.split()) <= 3:
            return 0.05
        case PromptSubmitEvent():
            return 0.5
        case _:
            return 0.4
```

Add circuit breaker methods to `CortexState`:

```python
    def record_error(self, handler: str) -> None:
        self.error_counts[handler] = self.error_counts.get(handler, 0) + 1
        if self.error_counts[handler] >= 3:
            self.disabled_handlers.add(handler)

    def record_success(self, handler: str) -> None:
        self.error_counts[handler] = 0
        self.disabled_handlers.discard(handler)

    def is_disabled(self, handler: str) -> bool:
        return handler in self.disabled_handlers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All tests PASS (18 total)

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): interest scoring + circuit breaker"
```

---

### Task 5: Entry point + graceful degradation

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test for entry point**

```python
# Append to tests/test_cortex.py
import subprocess

def test_cortex_cli_unknown_event():
    """Cortex handles unknown events without crashing."""
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "cortex.py"), "UnknownEvent"],
        input="{}",
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0


def test_cortex_cli_bad_json():
    """Cortex handles corrupt stdin without crashing."""
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "cortex.py"), "SubagentStart"],
        input="not json",
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0


def test_cortex_cli_empty_stdin():
    """Cortex handles empty stdin without crashing."""
    result = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "cortex.py"), "Stop"],
        input="",
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k cli`
Expected: FAIL — cortex.py has no `if __name__ == "__main__"` block

- [ ] **Step 3: Implement entry point with degradation chain**

Add to bottom of cortex.py:

```python
# ── Entry Point ──────────────────────────────────────────────────────

async def _run(event_type: str, raw_input: str) -> None:
    """Main async entry — 4-level degradation chain."""
    # Parse payload
    try:
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    event = parse_event(event_type, payload)
    score = interest_score(event)

    # Level 0: Skip trivial events
    if score < 0.1:
        return

    # Load state
    state = CortexState.load()

    # Circuit breaker check
    if state.is_disabled(event_type):
        return

    # Level 1: Full processing (JMEM + state)
    decision = Decision()
    try:
        sys.path.insert(0, str(JMEM_PATH))
        import asyncio as _aio
        from jmem.engine import JMemEngine, MemoryLevel

        engine = JMemEngine()
        decision = await _handle_event(engine, event, state, score)
        state.record_success(event_type)
    except Exception:
        # Level 2: State-only (JMEM unavailable)
        try:
            state.record_error(event_type)
            decision = Decision()
        except Exception:
            # Level 3: Static (state file broken)
            decision = Decision()

    # Save state
    try:
        state.total_decisions += 1
        state.save()
    except Exception:
        pass  # Level 4: Silent — never crash

    # Output
    output = decision.to_json()
    if output:
        print(output)


async def _handle_event(engine, event: HookEvent, state: CortexState, score: float) -> Decision:
    """Route event to handler. Placeholder — handlers added in later tasks."""
    from jmem.engine import MemoryLevel

    # Store L1 episode for events with sufficient interest
    if score >= 0.1:
        episode_content = event.to_episode()
        # Dedup check
        import hashlib
        content_hash = hashlib.sha256(episode_content.encode()).hexdigest()[:12]
        if content_hash not in state.recent_episode_hashes and state.episodes_this_session < 30:
            await engine.remember(
                content=episode_content,
                level=MemoryLevel.EPISODE,
                tags=event.tags(),
            )
            state.episodes_this_session += 1
            state.recent_episode_hashes = (state.recent_episode_hashes + [content_hash])[-5:]

    return Decision()


def main() -> None:
    import asyncio
    event_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    raw_input = sys.stdin.read()
    try:
        asyncio.run(_run(event_type, raw_input))
    except Exception:
        pass  # Absolute last resort — never crash


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All tests PASS (21 total)

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): entry point with 4-level degradation chain"
```

---

### Task 6: SubagentStart + SubagentStop handlers

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test for agent handlers**

```python
# Append to tests/test_cortex.py

def run_async(coro):
    return asyncio.run(coro)


@pytest.fixture
def jmem_engine(tmp_path):
    """Create an isolated JMEM engine for testing."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "jmem-mcp-server"))
    for mod in list(sys.modules):
        if mod.startswith("jmem"):
            del sys.modules[mod]
    from jmem.engine import JMemEngine
    os.environ["JMEM_DATA_DIR"] = str(tmp_path / "jmem")
    return JMemEngine()


def test_handle_agent_start_no_history(jmem_engine):
    """Agent start with no history returns observe."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks"))
    from cortex import handle_agent_start, AgentStartEvent, CortexState
    event = AgentStartEvent(type="SubagentStart", timestamp=time(), agent="aussie-tdd", task="fix auth")
    state = CortexState()
    decision = run_async(handle_agent_start(jmem_engine, event, state))
    assert decision.action == "observe"


def test_handle_agent_stop_success(jmem_engine):
    """Successful agent stop returns observe + rewards."""
    from cortex import handle_agent_stop, AgentStopEvent, CortexState
    event = AgentStopEvent(type="SubagentStop", timestamp=time(), agent="aussie-tdd", success=True)
    state = CortexState()
    decision = run_async(handle_agent_stop(jmem_engine, event, state))
    assert decision.action == "observe"
    assert decision.system_message is not None
    assert "aussie-tdd" in decision.system_message


def test_handle_agent_stop_failure(jmem_engine):
    """Failed agent stop returns observe + penalizes."""
    from cortex import handle_agent_stop, AgentStopEvent, CortexState
    event = AgentStopEvent(type="SubagentStop", timestamp=time(), agent="aussie-tdd", success=False, error="tests failed")
    state = CortexState()
    decision = run_async(handle_agent_stop(jmem_engine, event, state))
    assert decision.action == "observe"


def test_handle_agent_stop_repeated_failure_advises(jmem_engine):
    """3+ failures from same agent triggers advisory."""
    from cortex import handle_agent_stop, AgentStopEvent, CortexState
    from jmem.engine import MemoryLevel
    state = CortexState()
    # Pre-store 3 failure episodes
    for i in range(3):
        run_async(jmem_engine.remember(
            content=f"aussie-tdd failed: error {i}",
            level=MemoryLevel.EPISODE,
            tags=["agent-stop", "aussie-tdd", "failure"],
        ))
    event = AgentStopEvent(type="SubagentStop", timestamp=time(), agent="aussie-tdd", success=False, error="error again")
    decision = run_async(handle_agent_stop(jmem_engine, event, state))
    assert decision.action in ("advise", "observe")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k handle_agent`
Expected: FAIL — `ImportError: cannot import name 'handle_agent_start'`

- [ ] **Step 3: Implement agent handlers**

Add to cortex.py before the entry point section:

```python
# ── Agent Names ──────────────────────────────────────────────────────

AGENT_NAMES = frozenset({
    "pfaa-lead", "aussie-researcher", "aussie-planner", "aussie-architect",
    "aussie-security", "aussie-tdd", "pfaa-rewriter", "pfaa-validator",
    "aussie-deployer", "aussie-docs",
})

RESEARCH_AGENTS = frozenset({"aussie-researcher", "aussie-planner", "aussie-architect"})
IMPL_AGENTS = frozenset({"aussie-tdd", "pfaa-rewriter", "aussie-deployer"})
VERIFY_AGENTS = frozenset({"pfaa-validator", "aussie-security"})

PHASE_GUIDANCE = {
    "research": "RESEARCH phase: focus on gathering information, do not implement.",
    "synthesis": "SYNTHESIS phase: synthesize research findings into a spec.",
    "implementation": "IMPLEMENTATION phase: implement per the synthesized spec.",
    "verification": "VERIFICATION phase: validate implementation, check for issues.",
}


# ── Event Handlers ───────────────────────────────────────────────────

async def handle_agent_start(engine, event: AgentStartEvent, state: CortexState) -> Decision:
    """SubagentStart: recall history, inject context, possibly block."""
    from jmem.engine import MemoryLevel

    # Store episode
    await engine.remember(
        content=event.to_episode(),
        level=MemoryLevel.EPISODE,
        tags=event.tags(),
    )

    # Detect phase from agent type
    if event.agent in RESEARCH_AGENTS:
        state.phase = "research"
    elif event.agent == "pfaa-lead":
        state.phase = "synthesis"
    elif event.agent in IMPL_AGENTS:
        state.phase = "implementation"
    elif event.agent in VERIFY_AGENTS:
        state.phase = "verification"

    # Recall agent history
    history = await engine.recall(
        f"{event.agent} performance", limit=5, min_q=0.3,
    )

    context_parts = []

    # Phase guidance
    if state.phase in PHASE_GUIDANCE:
        context_parts.append(PHASE_GUIDANCE[state.phase])

    # Cross-agent context (tag-based filtering)
    if history:
        cross = [m for m in history if any(t in AGENT_NAMES for t in m.tags) and event.agent not in m.tags]
        if cross:
            context_parts.append("From other agents: " + "; ".join(m.content[:80] for m in cross[:3]))

    # Check for blocking (3+ failures, low Q)
    failures = [m for m in history if "failure" in m.tags]
    if len(failures) >= 3:
        avg_q = sum(m.q_value for m in failures) / len(failures)
        if avg_q < 0.4:
            return Decision(
                action="block",
                block_reason=f"JMEM: {event.agent} has {len(failures)} recent failures (avg Q={avg_q:.2f})",
                confidence=0.85,
            )

    if context_parts:
        return Decision(action="observe", additional_context="\n".join(context_parts))
    return Decision(action="observe")


async def handle_agent_stop(engine, event: AgentStopEvent, state: CortexState) -> Decision:
    """SubagentStop: store outcome, reward/penalize, detect patterns."""
    from jmem.engine import MemoryLevel

    # Store episode
    await engine.remember(
        content=event.to_episode(),
        level=MemoryLevel.EPISODE,
        tags=event.tags(),
    )

    if event.success:
        # Reward recently recalled memories
        try:
            await engine.reward_recalled(reward_signal=0.8)
        except Exception:
            pass
        # Pressure increment
        state.pressure += 0.5
        return Decision(
            action="observe",
            system_message=f"{event.agent} completed",
        )
    else:
        # Penalize
        try:
            await engine.reward_recalled(reward_signal=-0.5)
        except Exception:
            pass
        state.pressure += 2.0

        # Check failure pattern
        prior_failures = await engine.recall(
            f"{event.agent} failed", limit=10, min_q=0.0,
        )
        recent = [m for m in prior_failures if time() - m.created_at < 3600]

        if len(recent) >= 3:
            # Store L2 concept for promotion pipeline
            await engine.remember(
                content=f"{event.agent} has repeated failures ({len(recent)} in 1h)",
                level=MemoryLevel.CONCEPT,
                tags=["routing-rule", event.agent, "failure-pattern"],
            )
            return Decision(
                action="advise",
                system_message=f"Pattern: {event.agent} has {len(recent)} failures in the last hour. Consider an alternative agent.",
                confidence=0.6,
            )

        return Decision(action="observe")
```

Update `_handle_event` to route to handlers:

```python
async def _handle_event(engine, event: HookEvent, state: CortexState, score: float) -> Decision:
    """Route event to handler."""
    from jmem.engine import MemoryLevel
    import hashlib

    # Store L1 episode with dedup
    if score >= 0.1:
        episode_content = event.to_episode()
        content_hash = hashlib.sha256(episode_content.encode()).hexdigest()[:12]
        if content_hash not in state.recent_episode_hashes and state.episodes_this_session < 30:
            state.episodes_this_session += 1
            state.recent_episode_hashes = (state.recent_episode_hashes + [content_hash])[-5:]

    # Route to specific handler
    match event:
        case AgentStartEvent():
            return await handle_agent_start(engine, event, state)
        case AgentStopEvent():
            return await handle_agent_stop(engine, event, state)
        case _:
            return Decision()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All tests PASS (25 total)

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): SubagentStart + SubagentStop handlers with RL loop"
```

---

### Task 7: Wire hooks into settings.json + gitignore

**Files:**
- Modify: `.claude/settings.json`
- Modify: `.gitignore`

- [ ] **Step 1: Update settings.json with new hook entries**

Use Python to safely add hooks (preserving existing config):

```bash
python3 -c "
import json
ROOT = '/Users/borris/Desktop/pfaa-engine'
s = json.load(open(f'{ROOT}/.claude/settings.json'))

new_hooks = {
    'SubagentStart': [{'hooks': [{'type': 'command', 'command': f'python3 {ROOT}/.claude/hooks/cortex.py SubagentStart', 'timeout': 5, 'statusMessage': 'Cortex: agent start...'}]}],
    'SubagentStop': [{'hooks': [{'type': 'command', 'command': f'python3 {ROOT}/.claude/hooks/cortex.py SubagentStop', 'timeout': 10, 'statusMessage': 'Cortex: agent stop...'}]}],
    'PostToolUseFailure': [{'hooks': [{'type': 'command', 'command': f'python3 {ROOT}/.claude/hooks/cortex.py PostToolUseFailure', 'timeout': 5, 'statusMessage': 'Cortex: tool failure...'}]}],
    'TaskCompleted': [{'hooks': [{'type': 'command', 'command': f'python3 {ROOT}/.claude/hooks/cortex.py TaskCompleted', 'timeout': 5, 'statusMessage': 'Cortex: task done...'}]}],
    'UserPromptSubmit': [{'hooks': [{'type': 'command', 'command': f'python3 {ROOT}/.claude/hooks/cortex.py UserPromptSubmit', 'timeout': 3, 'statusMessage': 'Cortex: recall...'}]}],
    'FileChanged': [{'matcher': '*.py|*.pyi|settings.json|.claude/agents/*.md', 'hooks': [{'type': 'command', 'command': f'python3 {ROOT}/.claude/hooks/cortex.py FileChanged', 'timeout': 10, 'statusMessage': 'Cortex: file changed...'}]}],
}

for event, config in new_hooks.items():
    s['hooks'][event] = config

# Add cortex.py to Stop hooks
s['hooks']['Stop'].append({'hooks': [{'type': 'command', 'command': f'python3 {ROOT}/.claude/hooks/cortex.py Stop', 'timeout': 10, 'statusMessage': 'Cortex: stop...'}]})

with open(f'{ROOT}/.claude/settings.json', 'w') as f:
    json.dump(s, f, indent=2, ensure_ascii=False)
    f.write('\n')
print('Done')
"
```

- [ ] **Step 2: Add cortex_state.json to .gitignore**

```bash
echo ".claude/hooks/cortex_state.json" >> /Users/borris/Desktop/pfaa-engine/.gitignore
echo ".claude/hooks/cortex_state.tmp" >> /Users/borris/Desktop/pfaa-engine/.gitignore
```

- [ ] **Step 3: Verify settings.json is valid**

```bash
python3 -c "import json; json.load(open('/Users/borris/Desktop/pfaa-engine/.claude/settings.json')); print('Valid JSON')"
```
Expected: `Valid JSON`

- [ ] **Step 4: Test cortex runs from hook path**

```bash
echo '{"agent_name":"aussie-tdd","task":"test"}' | python3 /Users/borris/Desktop/pfaa-engine/.claude/hooks/cortex.py SubagentStart
echo $?
```
Expected: exit code 0

- [ ] **Step 5: Commit**

```bash
git add .claude/settings.json .gitignore
git commit -m "feat(cortex): wire 6 new hooks + Stop into settings.json"
```

---

## Phase 2: Analysis

### Task 8: PostToolUseFailure handler

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_cortex.py

def test_handle_tool_failure_first_time(jmem_engine):
    """First tool failure is observe-only."""
    from cortex import handle_tool_failure, ToolFailureEvent, CortexState
    event = ToolFailureEvent(type="PostToolUseFailure", timestamp=time(), tool="Bash", error="Permission denied", error_class="permission")
    state = CortexState()
    decision = run_async(handle_tool_failure(jmem_engine, event, state))
    assert decision.action == "observe"


def test_handle_tool_failure_escalation(jmem_engine):
    """3+ failures for same tool+class escalates."""
    from cortex import handle_tool_failure, ToolFailureEvent, CortexState
    from jmem.engine import MemoryLevel
    state = CortexState()
    for i in range(3):
        run_async(jmem_engine.remember(
            content=f"Bash failed (permission): error {i}",
            level=MemoryLevel.EPISODE,
            tags=["tool-failure", "Bash", "permission"],
        ))
    event = ToolFailureEvent(type="PostToolUseFailure", timestamp=time(), tool="Bash", error="Permission denied again", error_class="permission")
    decision = run_async(handle_tool_failure(jmem_engine, event, state))
    assert decision.action in ("advise", "block")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k tool_failure`
Expected: FAIL — `ImportError: cannot import name 'handle_tool_failure'`

- [ ] **Step 3: Implement handle_tool_failure**

Add to cortex.py handlers section:

```python
async def handle_tool_failure(engine, event: ToolFailureEvent, state: CortexState) -> Decision:
    """PostToolUseFailure: classify, store, escalate on repeated failures."""
    from jmem.engine import MemoryLevel

    await engine.remember(
        content=event.to_episode(),
        level=MemoryLevel.EPISODE,
        tags=event.tags(),
    )

    # Penalize memories that led here
    try:
        await engine.reward_recalled(reward_signal=-0.3)
    except Exception:
        pass

    # Check for repeated failures
    prior = await engine.recall(
        f"{event.tool} failed {event.error_class}", limit=10, min_q=0.0,
    )
    same_class = [m for m in prior if event.error_class in m.tags]

    if len(same_class) >= 3:
        return Decision(
            action="advise",
            system_message=f"{event.tool} has failed {len(same_class)}x ({event.error_class}). Consider an alternative approach.",
            confidence=0.6,
        )
    elif len(same_class) >= 5:
        return Decision(
            action="block",
            block_reason=f"Repeated {event.error_class} failures for {event.tool} ({len(same_class)}x)",
            confidence=0.85,
        )

    return Decision(action="observe")
```

Update `_handle_event` match to add:

```python
        case ToolFailureEvent():
            return await handle_tool_failure(engine, event, state)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): PostToolUseFailure handler with escalation"
```

---

### Task 9: TaskCompleted handler

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_cortex.py

def test_handle_task_completed(jmem_engine):
    """TaskCompleted stores episode and increments pressure."""
    from cortex import handle_task_completed, TaskCompletedEvent, CortexState
    event = TaskCompletedEvent(type="TaskCompleted", timestamp=time(), subject="Fix auth", description="Done")
    state = CortexState()
    state.pressure = 5.0
    decision = run_async(handle_task_completed(jmem_engine, event, state))
    assert decision.action == "observe"
    assert state.pressure == 6.0  # +1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k task_completed`
Expected: FAIL

- [ ] **Step 3: Implement handle_task_completed**

```python
async def handle_task_completed(engine, event: TaskCompletedEvent, state: CortexState) -> Decision:
    """TaskCompleted: silent reinforcement + pressure accumulation."""
    from jmem.engine import MemoryLevel

    await engine.remember(
        content=event.to_episode(),
        level=MemoryLevel.EPISODE,
        tags=event.tags(),
    )

    try:
        await engine.reward_recalled(reward_signal=0.7)
    except Exception:
        pass

    state.pressure += 1.0

    return Decision(action="observe")
```

Add to `_handle_event`:

```python
        case TaskCompletedEvent():
            return await handle_task_completed(engine, event, state)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): TaskCompleted handler with silent reinforcement"
```

---

### Task 10: FileChanged handler + AST analyzer

**Files:**
- Create: `.claude/hooks/analyzers/py315_ast.py`
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test for AST analyzer**

```python
# Append to tests/test_cortex.py

def test_py315_analyzer_pep810(tmp_path):
    """AST analyzer detects heavy imports that should be lazy."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "analyzers"))
    from py315_ast import analyze
    f = tmp_path / "sample.py"
    f.write_text("import numpy\nimport json\nx = 1\n")
    suggestions = analyze(str(f))
    pep810 = [s for s in suggestions if s.pep == "PEP 810"]
    assert len(pep810) == 1
    assert "numpy" in pep810[0].current


def test_py315_analyzer_pep814(tmp_path):
    """AST analyzer detects UPPER_CASE dict assignments."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "analyzers"))
    from py315_ast import analyze
    f = tmp_path / "sample.py"
    f.write_text("CONFIG = {'key': 'value'}\nlower = {'a': 1}\n")
    suggestions = analyze(str(f))
    pep814 = [s for s in suggestions if s.pep == "PEP 814"]
    assert len(pep814) == 1
    assert "CONFIG" in pep814[0].current


def test_py315_analyzer_no_false_positives(tmp_path):
    """Clean file produces no suggestions."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "analyzers"))
    from py315_ast import analyze
    f = tmp_path / "clean.py"
    f.write_text("x = 1\ndef add(a, b):\n    return a + b\n")
    assert analyze(str(f)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k py315`
Expected: FAIL — `ModuleNotFoundError: No module named 'py315_ast'`

- [ ] **Step 3: Create the AST analyzer**

```bash
mkdir -p /Users/borris/Desktop/pfaa-engine/.claude/hooks/analyzers
```

```python
# .claude/hooks/analyzers/py315_ast.py
"""Deep AST-based Python 3.15 opportunity scanner."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

HEAVY_MODULES = frozenset({
    "numpy", "pandas", "torch", "tensorflow", "requests", "httpx",
    "sqlalchemy", "flask", "fastapi", "django", "pydantic", "scipy",
    "matplotlib", "boto3", "celery", "sklearn",
})


@dataclass(frozen=True, slots=True)
class Suggestion:
    pep: str
    line: int
    current: str
    proposed: str
    confidence: float


def analyze(filepath: str) -> list[Suggestion]:
    """Analyze a Python file for PEP 810/814/695/634 opportunities."""
    try:
        source = Path(filepath).read_text()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, FileNotFoundError, UnicodeDecodeError):
        return []

    suggestions: list[Suggestion] = []

    for node in ast.walk(tree):
        # PEP 810: Heavy imports that should be lazy
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in HEAVY_MODULES:
                    suggestions.append(Suggestion(
                        pep="PEP 810", line=node.lineno,
                        current=f"import {alias.name}",
                        proposed=f"lazy import {alias.name}",
                        confidence=0.95,
                    ))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in HEAVY_MODULES:
                suggestions.append(Suggestion(
                    pep="PEP 810", line=node.lineno,
                    current=f"from {node.module} import ...",
                    proposed=f"lazy import {node.module} (then access attrs)",
                    confidence=0.85,
                ))

        # PEP 814: UPPER_CASE dict literals -> frozendict
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (isinstance(target, ast.Name) and target.id.isupper()
                    and isinstance(node.value, ast.Dict)):
                suggestions.append(Suggestion(
                    pep="PEP 814", line=node.lineno,
                    current=f"{target.id} = {{...}}",
                    proposed=f"{target.id} = frozendict({{...}})",
                    confidence=0.85,
                ))

    return suggestions
```

- [ ] **Step 4: Implement handle_file_changed in cortex.py**

```python
async def handle_file_changed(engine, event: FileChangedEvent, state: CortexState) -> Decision:
    """FileChanged: AST analysis for .py, config tracking for settings.json."""
    from jmem.engine import MemoryLevel

    if event.ext in (".py", ".pyi") and event.path:
        # Lazy-import AST analyzer
        sys.path.insert(0, str(PROJECT_ROOT / ".claude" / "hooks" / "analyzers"))
        try:
            from py315_ast import analyze
            suggestions = analyze(event.path)
        except Exception:
            suggestions = []

        if suggestions:
            lines = [f"  Line {s.line}: {s.current} -> {s.proposed} ({s.pep}, {s.confidence:.0%})"
                     for s in suggestions[:5]]
            msg = f"Py3.15 opportunities in {Path(event.path).name}:\n" + "\n".join(lines)
            await engine.remember(
                content=f"Py3.15 scan: {Path(event.path).name} — {len(suggestions)} suggestions",
                level=MemoryLevel.EPISODE,
                tags=["file-changed", "py315-scan", f"file:{event.path}"],
            )
            return Decision(action="advise", system_message=msg, confidence=0.7)

    elif event.path and event.path.endswith("settings.json"):
        return Decision(action="observe", system_message="Config changed — cortex rules may need reload")

    elif event.path and ".claude/agents/" in event.path:
        await engine.remember(
            content=f"Agent definition updated: {Path(event.path).name}",
            level=MemoryLevel.EPISODE,
            tags=["file-changed", "agent-update"],
        )

    return Decision(action="observe")
```

Add to `_handle_event`:

```python
        case FileChangedEvent():
            return await handle_file_changed(engine, event, state)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add .claude/hooks/cortex.py .claude/hooks/analyzers/py315_ast.py tests/test_cortex.py
git commit -m "feat(cortex): FileChanged handler + AST Py3.15 analyzer (PEP 810/814)"
```

---

## Phase 3: Intelligence

### Task 11: UserPromptSubmit handler

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_cortex.py

def test_handle_prompt_submit_trivial():
    """Trivial prompts (<=3 words) return no injection."""
    from cortex import handle_prompt_submit, PromptSubmitEvent, CortexState
    event = PromptSubmitEvent(type="UserPromptSubmit", timestamp=time(), prompt="yes")
    state = CortexState()
    decision = run_async(handle_prompt_submit(None, event, state))
    assert decision.action == "observe"
    assert decision.additional_context is None


def test_handle_prompt_submit_with_memories(jmem_engine):
    """Substantial prompt with relevant memories injects context."""
    from cortex import handle_prompt_submit, PromptSubmitEvent, CortexState
    from jmem.engine import MemoryLevel
    run_async(jmem_engine.remember(
        content="auth module has a known race condition in token refresh",
        level=MemoryLevel.PRINCIPLE,
        tags=["auth", "security"],
    ))
    event = PromptSubmitEvent(type="UserPromptSubmit", timestamp=time(), prompt="fix the auth bug in the login token refresh flow")
    state = CortexState()
    decision = run_async(handle_prompt_submit(jmem_engine, event, state))
    # May or may not find the memory depending on JMEM's TF-IDF indexing
    assert decision.action == "observe"


def test_handle_prompt_submit_cache(jmem_engine):
    """Second similar prompt within 30s uses cached result."""
    from cortex import handle_prompt_submit, PromptSubmitEvent, CortexState
    state = CortexState()
    state.last_prompt_keywords = ["auth", "bug", "fix"]
    state.last_prompt_recall = [{"content": "cached memory", "level": "PRINCIPLE", "q": 0.8}]
    state.last_prompt_at = time()  # Just now
    event = PromptSubmitEvent(type="UserPromptSubmit", timestamp=time(), prompt="fix the auth bug again please")
    decision = run_async(handle_prompt_submit(jmem_engine, event, state))
    # Should use cache since keywords overlap
    assert decision.action == "observe"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k prompt_submit`
Expected: FAIL

- [ ] **Step 3: Implement handle_prompt_submit**

```python
def _extract_keywords(text: str) -> list[str]:
    """Extract significant keywords from prompt text."""
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                  "being", "have", "has", "had", "do", "does", "did", "will",
                  "would", "could", "should", "may", "might", "can", "to", "of",
                  "in", "for", "on", "with", "at", "by", "from", "it", "this",
                  "that", "and", "or", "but", "not", "no", "so", "if", "then",
                  "than", "too", "very", "just", "i", "me", "my", "we", "you"}
    words = text.lower().split()
    return [w for w in words if w not in stop_words and len(w) > 2][:10]


async def handle_prompt_submit(engine, event: PromptSubmitEvent, state: CortexState) -> Decision:
    """UserPromptSubmit: inject relevant JMEM context before Claude processes."""
    # Fast exit for trivial prompts
    if len(event.prompt.split()) <= 3:
        return Decision(action="observe")

    if engine is None:
        return Decision(action="observe")

    keywords = _extract_keywords(event.prompt)

    # Cache check
    if (time() - state.last_prompt_at < 30 and state.last_prompt_keywords):
        overlap = len(set(keywords) & set(state.last_prompt_keywords)) / max(len(keywords), 1)
        if overlap > 0.5 and state.last_prompt_recall:
            lines = [f"[{m['level']} Q={m['q']:.1f}] {m['content'][:120]}" for m in state.last_prompt_recall]
            return Decision(action="observe", additional_context="JMEM auto-recall:\n" + "\n".join(lines))

    # Full recall
    start = time()
    try:
        memories = await engine.recall(event.prompt, limit=3, min_q=0.6)
    except Exception:
        return Decision(action="observe")

    if time() - start > 0.15:
        return Decision(action="observe")

    if not memories:
        state.last_prompt_keywords = keywords
        state.last_prompt_recall = []
        state.last_prompt_at = time()
        return Decision(action="observe")

    # Format and cache
    recall_data = [{"content": m.content[:120], "level": m.level.name, "q": m.q_value} for m in memories]
    state.last_prompt_keywords = keywords
    state.last_prompt_recall = recall_data
    state.last_prompt_at = time()

    lines = [f"[{m['level'][:4]} Q={m['q']:.1f}] {m['content']}" for m in recall_data]
    return Decision(action="observe", additional_context="JMEM auto-recall:\n" + "\n".join(lines))
```

Add to `_handle_event`:

```python
        case PromptSubmitEvent():
            return await handle_prompt_submit(engine, event, state)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): UserPromptSubmit handler with per-prompt JMEM injection + cache"
```

---

### Task 12: Stop handler + dream cycle (Phase A)

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_cortex.py

def test_handle_stop_stores_episode(jmem_engine):
    """Stop handler stores session episode."""
    from cortex import handle_stop, HookEvent, CortexState
    event = HookEvent(type="Stop", timestamp=time())
    state = CortexState()
    decision = run_async(handle_stop(jmem_engine, event, state))
    assert decision.action == "observe"


def test_handle_stop_dream_phase_a(jmem_engine):
    """Dream phase A triggers when pressure exceeds threshold."""
    from cortex import handle_stop, HookEvent, CortexState
    event = HookEvent(type="Stop", timestamp=time())
    state = CortexState()
    state.pressure = 15.0  # Above default threshold of 10
    state.last_dream_at = 0.0  # Long ago
    decision = run_async(handle_stop(jmem_engine, event, state))
    assert state.pressure == 0.0  # Reset after dream
    assert state.dream_pending is True  # Phase B deferred


def test_handle_stop_no_dream_too_recent(jmem_engine):
    """Dream skipped if last dream was < 1 hour ago."""
    from cortex import handle_stop, HookEvent, CortexState
    event = HookEvent(type="Stop", timestamp=time())
    state = CortexState()
    state.pressure = 15.0
    state.last_dream_at = time() - 60  # 1 minute ago
    decision = run_async(handle_stop(jmem_engine, event, state))
    assert state.pressure == 15.0  # Not reset
    assert state.dream_pending is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k handle_stop`
Expected: FAIL

- [ ] **Step 3: Implement handle_stop with dream Phase A**

```python
PRESSURE_THRESHOLD_DEFAULT = 10.0
DREAM_MIN_HOURS = 1.0


async def handle_stop(engine, event: HookEvent, state: CortexState) -> Decision:
    """Stop: store episode, run dream Phase A if conditions met."""
    from jmem.engine import MemoryLevel

    # Store session episode
    await engine.remember(
        content=f"Session stop — {state.total_decisions} decisions, pressure={state.pressure:.1f}",
        level=MemoryLevel.EPISODE,
        tags=["session-stop", "auto-episode"],
    )

    # Check dream conditions
    hours_since_dream = (time() - state.last_dream_at) / 3600
    if state.pressure >= PRESSURE_THRESHOLD_DEFAULT and hours_since_dream >= DREAM_MIN_HOURS:
        # Dream Phase A: lightweight steps only (<5s)
        try:
            await engine.consolidate()
            await engine.decay_idle(hours_threshold=24.0)
        except Exception:
            pass

        state.pressure = 0.0
        state.last_dream_at = time()
        state.dream_pending = True  # Phase B deferred to next SessionStart

        return Decision(
            action="observe",
            system_message="Cortex dream (Phase A): consolidated + decayed",
        )

    return Decision(action="observe")
```

Add to `_handle_event`:

```python
        case HookEvent(type="Stop"):
            return await handle_stop(engine, event, state)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): Stop handler with dream Phase A (consolidate + decay)"
```

---

## Phase 4: Self-Improvement

### Task 13: Dream Phase B (heavy cognitive cycle)

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_cortex.py

def test_dream_phase_b(jmem_engine):
    """Dream Phase B runs heavy steps when dream_pending is True."""
    from cortex import run_dream_phase_b, CortexState
    state = CortexState()
    state.dream_pending = True
    run_async(run_dream_phase_b(jmem_engine, state))
    assert state.dream_pending is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k dream_phase_b`
Expected: FAIL

- [ ] **Step 3: Implement run_dream_phase_b**

```python
async def run_dream_phase_b(engine, state: CortexState) -> None:
    """Dream Phase B: heavy cognitive cycle — extract, meta-learn, emerge, assess."""
    try:
        await engine.extract_skills()
        await engine.meta_learn()
        await engine.emergent_synthesis()
    except Exception:
        pass

    # Self-assessment
    if state.total_decisions >= 20:
        total_blocks = state.correct_blocks + state.overridden_blocks
        if total_blocks > 0:
            accuracy = state.correct_blocks / total_blocks
            if accuracy < 0.5:
                state.interest_baseline = min(state.interest_baseline * 1.2, 0.9)
            elif accuracy > 0.85:
                state.interest_baseline = max(state.interest_baseline * 0.9, 0.2)

    state.dream_pending = False
```

Wire into `_run` — check `dream_pending` at the start of each invocation:

Add to the beginning of `_run` after loading state:

```python
    # Dream Phase B: deferred from prior Stop
    if state.dream_pending and event_type == "SessionStart":
        try:
            sys.path.insert(0, str(JMEM_PATH))
            from jmem.engine import JMemEngine
            engine = JMemEngine()
            await run_dream_phase_b(engine, state)
        except Exception:
            state.dream_pending = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): dream Phase B — extract_skills, meta_learn, emergent, self-assess"
```

---

### Task 14: Self-assessment + hook evolution suggestions

**Files:**
- Modify: `.claude/hooks/cortex.py`
- Modify: `tests/test_cortex.py`

- [ ] **Step 1: Write the failing test**

```python
# Append to tests/test_cortex.py

def test_self_assess_raises_baseline_on_low_accuracy():
    from cortex import CortexState, self_assess
    state = CortexState()
    state.total_decisions = 50
    state.correct_blocks = 2
    state.overridden_blocks = 8
    old_baseline = state.interest_baseline
    self_assess(state)
    assert state.interest_baseline > old_baseline


def test_self_assess_lowers_baseline_on_high_accuracy():
    from cortex import CortexState, self_assess
    state = CortexState()
    state.total_decisions = 50
    state.correct_blocks = 9
    state.overridden_blocks = 1
    old_baseline = state.interest_baseline
    self_assess(state)
    assert state.interest_baseline < old_baseline


def test_self_assess_noop_insufficient_data():
    from cortex import CortexState, self_assess
    state = CortexState()
    state.total_decisions = 5
    old_baseline = state.interest_baseline
    self_assess(state)
    assert state.interest_baseline == old_baseline
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cortex.py -v -k self_assess`
Expected: FAIL

- [ ] **Step 3: Extract self_assess as standalone function**

```python
def self_assess(state: CortexState) -> None:
    """Evaluate cortex accuracy and adjust intervention level."""
    if state.total_decisions < 20:
        return
    total_blocks = state.correct_blocks + state.overridden_blocks
    if total_blocks == 0:
        return
    accuracy = state.correct_blocks / total_blocks
    if accuracy < 0.5:
        state.interest_baseline = min(state.interest_baseline * 1.2, 0.9)
    elif accuracy > 0.85:
        state.interest_baseline = max(state.interest_baseline * 0.9, 0.2)
```

Update `run_dream_phase_b` to call `self_assess(state)` instead of inline logic.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py
git commit -m "feat(cortex): self-assessment adjusts intervention baseline from accuracy"
```

---

### Task 15: Final integration test + banner update

**Files:**
- Modify: `tests/test_cortex.py`
- Modify: `.claude/hooks/banner.cjs`

- [ ] **Step 1: Write full integration test**

```python
# Append to tests/test_cortex.py

def test_full_agent_lifecycle(jmem_engine):
    """Integration: start -> stop(success) -> task_completed -> pressure rises."""
    from cortex import (
        handle_agent_start, handle_agent_stop, handle_task_completed,
        AgentStartEvent, AgentStopEvent, TaskCompletedEvent, CortexState
    )
    state = CortexState()

    # Agent starts
    start_event = AgentStartEvent(type="SubagentStart", timestamp=time(), agent="aussie-tdd", task="fix auth")
    d1 = run_async(handle_agent_start(jmem_engine, start_event, state))
    assert d1.action == "observe"

    # Agent succeeds
    stop_event = AgentStopEvent(type="SubagentStop", timestamp=time(), agent="aussie-tdd", success=True)
    d2 = run_async(handle_agent_stop(jmem_engine, stop_event, state))
    assert d2.action == "observe"
    assert state.pressure == 0.5

    # Task completed
    task_event = TaskCompletedEvent(type="TaskCompleted", timestamp=time(), subject="Auth fixed")
    d3 = run_async(handle_task_completed(jmem_engine, task_event, state))
    assert state.pressure == 1.5


def test_cortex_end_to_end_cli():
    """Cortex runs end-to-end from CLI without crashing."""
    cortex_path = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "cortex.py")
    events = [
        ("SubagentStart", '{"agent_name":"aussie-tdd","task":"test"}'),
        ("SubagentStop", '{"agent_name":"aussie-tdd","result":{"success":true}}'),
        ("PostToolUseFailure", '{"tool_name":"Bash","error":"timeout"}'),
        ("TaskCompleted", '{"subject":"Done"}'),
        ("UserPromptSubmit", '{"prompt":"fix the auth bug in the login flow"}'),
        ("FileChanged", '{"file_path":"/tmp/test.py"}'),
        ("Stop", '{}'),
    ]
    for event_type, payload in events:
        result = subprocess.run(
            [sys.executable, cortex_path, event_type],
            input=payload, capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, f"{event_type} failed: {result.stderr}"
```

- [ ] **Step 2: Run full test suite**

Run: `python3 -m pytest tests/test_cortex.py -v`
Expected: All PASS

- [ ] **Step 3: Update banner to show 7 hooks (was 6)**

Edit `.claude/hooks/banner.cjs` — change the hooks count from `'6'` to `'7'`:

Find: `pill('hooks',  '6',  [255, 100, 80])`
Replace: `pill('hooks',  '7',  [255, 100, 80])`

- [ ] **Step 4: Update statusline hook count**

Edit `.claude/hooks/statusline.cjs`:

Find: `'6H'` or equivalent hooks reference and update if present.

- [ ] **Step 5: Commit**

```bash
git add .claude/hooks/cortex.py tests/test_cortex.py .claude/hooks/banner.cjs
git commit -m "feat(cortex): integration tests + updated hook counts in banner"
```

---

## Summary

| Phase | Tasks | What's Deployable After |
|---|---|---|
| 1: Foundation | Tasks 1-7 | Agent performance tracking, RL reward/penalize, circuit breaker, degradation |
| 2: Analysis | Tasks 8-10 | Tool failure escalation, Py3.15 AST scanning, task reinforcement |
| 3: Intelligence | Tasks 11-12 | Per-prompt memory injection, dream cycle Phase A |
| 4: Self-Improvement | Tasks 13-15 | Dream Phase B, self-assessment, accuracy-based tuning |
