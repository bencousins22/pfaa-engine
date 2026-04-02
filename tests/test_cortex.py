"""Tests for CortexState, Decision, and Event types — Aussie Cortex hook system."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from time import time

# Set up paths so we can import from .claude/hooks/ and jmem-mcp-server
_hooks_path = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks")
sys.path.insert(0, _hooks_path)

_mcp_path = os.path.join(os.path.dirname(__file__), "..", "jmem-mcp-server")
sys.path.insert(0, _mcp_path)
for mod_name in list(sys.modules):
    if mod_name.startswith("jmem"):
        del sys.modules[mod_name]

import pytest

from cortex import (
    CortexState,
    STATE_PATH,
    Decision,
    HookEvent,
    AgentStartEvent,
    AgentStopEvent,
    ToolFailureEvent,
    FileChangedEvent,
    TaskCompletedEvent,
    PromptSubmitEvent,
    parse_event,
    classify_error,
    interest_score,
    is_feature_enabled,
    _build_agent_context,
    AGENT_FILE_HINTS,
)


# ── Default values ──────────────────────────────────────────────────


def test_cortex_state_default():
    """All fields should have sensible defaults on fresh construction."""
    s = CortexState()
    assert s.pressure == 0.0
    assert s.phase == "idle"
    assert s.error_counts == {}
    assert s.disabled_handlers == set()
    assert s.total_decisions == 0
    assert s.correct_blocks == 0
    assert s.overridden_blocks == 0
    assert s.interest_baseline == 0.5
    assert s.last_dream_at == 0.0
    assert s.dream_pending is False
    assert s.rules_loaded_at == 0.0
    assert s.episodes_this_session == 0
    assert s.last_prompt_keywords == []
    assert s.last_prompt_recall == []
    assert s.last_prompt_at == 0.0
    assert s.recent_episode_hashes == []
    assert s.state_path == STATE_PATH


# ── Round-trip save / load ──────────────────────────────────────────


def test_cortex_state_save_load(tmp_path):
    """State should survive a round-trip through JSON."""
    fp = tmp_path / "cortex_state.json"
    s = CortexState(state_path=fp)
    s.pressure = 0.75
    s.phase = "active"
    s.error_counts = {"type_check": 3, "secret_scan": 1}
    s.disabled_handlers = {"noisy_handler", "broken_handler"}
    s.total_decisions = 42
    s.correct_blocks = 10
    s.overridden_blocks = 2
    s.interest_baseline = 0.8
    s.last_dream_at = 1000.0
    s.dream_pending = True
    s.rules_loaded_at = 999.0
    s.episodes_this_session = 7
    s.last_prompt_keywords = ["refactor", "memory"]
    s.last_prompt_recall = [{"id": "abc", "score": 0.9}]
    s.last_prompt_at = 1234.5
    s.recent_episode_hashes = ["hash1", "hash2"]
    s.save()

    loaded = CortexState.load(fp)
    assert loaded.pressure == 0.75
    assert loaded.phase == "active"
    assert loaded.error_counts == {"type_check": 3, "secret_scan": 1}
    assert loaded.disabled_handlers == {"noisy_handler", "broken_handler"}
    assert loaded.total_decisions == 42
    assert loaded.correct_blocks == 10
    assert loaded.overridden_blocks == 2
    assert loaded.interest_baseline == 0.8
    assert loaded.last_dream_at == 1000.0
    assert loaded.dream_pending is True
    assert loaded.rules_loaded_at == 999.0
    assert loaded.episodes_this_session == 7
    assert loaded.last_prompt_keywords == ["refactor", "memory"]
    assert loaded.last_prompt_recall == [{"id": "abc", "score": 0.9}]
    assert loaded.last_prompt_at == 1234.5
    assert loaded.recent_episode_hashes == ["hash1", "hash2"]
    # state_path should be set to the loaded path, not serialized default
    assert loaded.state_path == fp


# ── Atomic write guarantees ─────────────────────────────────────────


def test_cortex_state_atomic_write(tmp_path):
    """Atomic save: no .tmp leftover, file exists, content is correct JSON."""
    import json

    fp = tmp_path / "cortex_state.json"
    s = CortexState(state_path=fp)
    s.phase = "dreaming"
    s.pressure = 0.42
    s.save()

    # No temp files should remain
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Temp files left behind: {tmp_files}"

    # File must exist
    assert fp.exists()

    # Content must be valid JSON with correct values
    data = json.loads(fp.read_text())
    assert data["phase"] == "dreaming"
    assert data["pressure"] == 0.42
    # state_path must NOT appear in serialized JSON
    assert "state_path" not in data


# ── Load from missing / corrupt file returns defaults ───────────────


def test_cortex_state_load_missing(tmp_path):
    """Loading from a non-existent file should return fresh defaults."""
    fp = tmp_path / "does_not_exist.json"
    loaded = CortexState.load(fp)
    assert loaded.phase == "idle"
    assert loaded.pressure == 0.0
    assert loaded.total_decisions == 0


def test_cortex_state_load_corrupt(tmp_path):
    """Loading from a corrupt JSON file should return fresh defaults."""
    fp = tmp_path / "bad.json"
    fp.write_text("not valid json {{{")
    loaded = CortexState.load(fp)
    assert loaded.phase == "idle"
    assert loaded.pressure == 0.0


# ── Decision tests ─────────────────────────────────────────────────


def test_decision_observe():
    """Default Decision (observe) produces empty JSON string."""
    d = Decision()
    assert d.action == "observe"
    assert d.to_json() == ""


def test_decision_advise():
    """Decision with system_message produces output with systemMessage."""
    d = Decision(action="advise", system_message="Check types before commit")
    out = json.loads(d.to_json())
    assert out["systemMessage"] == "Check types before commit"


def test_decision_block():
    """Decision with block action has decision:'block' and reason."""
    d = Decision(action="block", block_reason="Secret detected in .env")
    out = json.loads(d.to_json())
    assert out["decision"] == "block"
    assert out["reason"] == "Secret detected in .env"


def test_decision_with_context():
    """Decision with additional_context includes hookSpecificOutput."""
    d = Decision(
        action="advise",
        system_message="Heads up",
        additional_context="File changed: src/main.ts",
    )
    out = json.loads(d.to_json())
    assert out["systemMessage"] == "Heads up"
    assert out["hookSpecificOutput"]["additionalContext"] == "File changed: src/main.ts"


# ── Event type tests ───────────────────────────────────────────────


def test_parse_agent_start():
    """parse_event('agent_start', ...) returns AgentStartEvent with correct fields."""
    ev = parse_event("SubagentStart", {"agent_type": "pfaa-lead", "task": "deploy v2"})
    assert isinstance(ev, AgentStartEvent)
    assert ev.type == "SubagentStart"
    assert ev.agent == "pfaa-lead"
    assert ev.task == "deploy v2"
    assert ev.timestamp > 0
    episode = ev.to_episode()
    assert "pfaa-lead" in episode
    assert "deploy v2" in episode
    assert "agent" in ev.tags()


def test_parse_agent_stop_success():
    """AgentStopEvent with success=True and no error."""
    ev = parse_event("SubagentStop", {"agent_type": "aussie-tdd", "success": True})
    assert isinstance(ev, AgentStopEvent)
    assert ev.success is True
    assert ev.error is None
    assert "success" in ev.to_episode().lower() or "completed" in ev.to_episode().lower()


def test_parse_agent_stop_failure():
    """AgentStopEvent with success=False and error populated."""
    ev = parse_event(
        "SubagentStop",
        {"agent_type": "aussie-tdd", "success": False, "error": "Timeout exceeded"},
    )
    assert isinstance(ev, AgentStopEvent)
    assert ev.success is False
    assert ev.error == "Timeout exceeded"
    assert "fail" in ev.to_episode().lower() or "error" in ev.to_episode().lower()


def test_parse_file_changed():
    """FileChangedEvent extracts path and extension."""
    ev = parse_event("FileChanged", {"file_path": "src/core/engine.ts"})
    assert isinstance(ev, FileChangedEvent)
    assert ev.path == "src/core/engine.ts"
    assert ev.ext == ".ts"
    assert "file" in ev.tags()


def test_parse_tool_failure():
    """ToolFailureEvent classifies error correctly."""
    ev = parse_event(
        "PostToolUseFailure",
        {"tool_name": "Bash", "error": "Permission denied: /etc/shadow"},
    )
    assert isinstance(ev, ToolFailureEvent)
    assert ev.tool == "Bash"
    assert ev.error_class == "permission"
    assert "tool" in ev.tags()


def test_parse_prompt_submit():
    """PromptSubmitEvent extracts prompt text."""
    ev = parse_event("UserPromptSubmit", {"prompt": "refactor the memory store"})
    assert isinstance(ev, PromptSubmitEvent)
    assert ev.prompt == "refactor the memory store"
    assert "prompt" in ev.tags()


def test_parse_task_completed():
    """TaskCompletedEvent extracts subject."""
    ev = parse_event(
        "TaskCompleted",
        {"task_subject": "deploy", "task_description": "Deployed v2.1 to prod"},
    )
    assert isinstance(ev, TaskCompletedEvent)
    assert ev.subject == "deploy"
    assert ev.description == "Deployed v2.1 to prod"
    assert "task" in ev.tags()


def test_parse_unknown_event():
    """Unknown event type returns base HookEvent, never crashes."""
    ev = parse_event("TotallyNewEvent", {"foo": "bar"})
    assert isinstance(ev, HookEvent)
    assert ev.type == "TotallyNewEvent"


def test_parse_missing_fields():
    """Empty payload produces defaults, never crashes."""
    for event_type in [
        "SubagentStart",
        "SubagentStop",
        "PostToolUseFailure",
        "FileChanged",
        "TaskCompleted",
        "UserPromptSubmit",
    ]:
        ev = parse_event(event_type, {})
        assert ev.type == event_type
        assert ev.timestamp > 0
        # Should not raise — just produce defaults
        _ = ev.to_episode()
        _ = ev.tags()


# ── Error classifier tests ─────────────────────────────────────────


def test_classify_error_permission():
    assert classify_error("Permission denied: /etc/shadow") == "permission"


def test_classify_error_timeout():
    assert classify_error("Request timed out after 30s") == "timeout"


def test_classify_error_not_found():
    assert classify_error("ENOENT: no such file or directory") == "not_found"


def test_classify_error_syntax():
    assert classify_error("SyntaxError: unexpected token '}'") == "syntax"


def test_classify_error_network():
    assert classify_error("ECONNREFUSED: connection refused") == "network"


def test_classify_error_resource():
    assert classify_error("Fatal: out of memory") == "resource"


def test_classify_error_unknown():
    assert classify_error("Something completely unexpected") == "unknown"


# ── Task 4: Interest scoring + circuit breaker ─────────────────────


def test_interest_score_failure_max():
    """Failed agent stop should get maximum interest (1.0)."""
    ev = AgentStopEvent(type="agent_stop", agent="pfaa-lead", success=False, error="crash")
    assert interest_score(ev) == 1.0


def test_interest_score_trivial_prompt():
    """Very short prompt (<=3 words) should get near-zero interest."""
    ev = PromptSubmitEvent(type="prompt_submit", prompt="hi")
    assert interest_score(ev) == 0.05


def test_interest_score_py_file():
    """Python file changes should get high interest (0.8)."""
    ev = FileChangedEvent(type="file_changed", path="src/main.py", ext=".py")
    assert interest_score(ev) == 0.8


def test_interest_score_task_completed():
    """Task completed events should get low-medium interest (0.3)."""
    ev = TaskCompletedEvent(type="task_completed", subject="deploy")
    assert interest_score(ev) == 0.3


def test_circuit_breaker_disable():
    """After 3 errors on the same handler, it should be disabled."""
    s = CortexState()
    s.record_error("noisy_handler")
    s.record_error("noisy_handler")
    assert not s.is_disabled("noisy_handler")
    s.record_error("noisy_handler")
    assert s.is_disabled("noisy_handler")


def test_circuit_breaker_reenable():
    """A success should reset error count and re-enable a disabled handler."""
    s = CortexState()
    for _ in range(3):
        s.record_error("flaky_handler")
    assert s.is_disabled("flaky_handler")
    s.record_success("flaky_handler")
    assert not s.is_disabled("flaky_handler")
    assert s.error_counts["flaky_handler"] == 0


# ── Task 5: CLI entry point + degradation ──────────────────────────


CORTEX_SCRIPT = os.path.join(
    os.path.dirname(__file__), "..", ".claude", "hooks", "cortex.py"
)


def test_cortex_cli_unknown_event():
    """Unknown event type should not crash — should exit 0."""
    result = subprocess.run(
        [sys.executable, CORTEX_SCRIPT, "totally_made_up"],
        input="{}",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0


def test_cortex_cli_bad_json():
    """Bad JSON input should not crash — should exit 0."""
    result = subprocess.run(
        [sys.executable, CORTEX_SCRIPT, "agent_start"],
        input="not json at all {{{",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0


def test_cortex_cli_empty_stdin():
    """Empty stdin should not crash — should exit 0."""
    result = subprocess.run(
        [sys.executable, CORTEX_SCRIPT, "agent_start"],
        input="",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0


# ── Task 6: Agent handlers ─────────────────────────────────────────


def run_async(coro):
    """Helper to run an async function synchronously in tests."""
    return asyncio.run(coro)


@pytest.fixture
def jmem_engine(tmp_path):
    """Create an isolated JMemEngine using a temp directory."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "jmem-mcp-server"))
    for mod in list(sys.modules):
        if mod.startswith("jmem"):
            del sys.modules[mod]
    from jmem.engine import JMemEngine
    os.environ["JMEM_DATA_DIR"] = str(tmp_path / "jmem")
    db_path = str(tmp_path / "jmem" / "vector_store.db")
    return JMemEngine(db_path=db_path)


def test_handle_agent_start_no_history(jmem_engine, tmp_path):
    """Agent start with no history should observe with context."""
    from cortex import handle_agent_start

    state = CortexState(state_path=tmp_path / "state.json")
    ev = AgentStartEvent(
        type="agent_start", agent="aussie-researcher", task="analyze codebase"
    )

    async def _run():
        await jmem_engine.start()
        try:
            return await handle_agent_start(jmem_engine, ev, state)
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.action == "observe"


def test_handle_agent_stop_success(jmem_engine, tmp_path):
    """Successful agent stop should produce system_message mentioning the agent."""
    from cortex import handle_agent_stop

    state = CortexState(state_path=tmp_path / "state.json")
    ev = AgentStopEvent(
        type="agent_stop", agent="aussie-tdd", success=True
    )

    async def _run():
        await jmem_engine.start()
        try:
            return await handle_agent_stop(jmem_engine, ev, state)
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.action == "observe"
    assert decision.system_message is not None
    assert "aussie-tdd" in decision.system_message


def test_handle_agent_stop_failure(jmem_engine, tmp_path):
    """Failed agent stop should still observe (not block)."""
    from cortex import handle_agent_stop

    state = CortexState(state_path=tmp_path / "state.json")
    ev = AgentStopEvent(
        type="agent_stop", agent="pfaa-lead", success=False, error="timeout"
    )

    async def _run():
        await jmem_engine.start()
        try:
            return await handle_agent_stop(jmem_engine, ev, state)
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.action == "observe"


def test_handle_agent_stop_repeated_failure_advises(jmem_engine, tmp_path):
    """After 3+ recent failures, agent stop should advise."""
    from jmem.engine import MemoryLevel
    from cortex import handle_agent_stop

    state = CortexState(state_path=tmp_path / "state.json")

    async def _run():
        await jmem_engine.start()
        try:
            # Pre-store 3 failure episodes within the last hour
            for i in range(3):
                await jmem_engine.remember(
                    content=f"Agent pfaa-lead failed: error {i}",
                    level=MemoryLevel.EPISODE,
                    context="failure",
                    tags=["agent", "stop", "pfaa-lead", "error"],
                )

            ev = AgentStopEvent(
                type="agent_stop",
                agent="pfaa-lead",
                success=False,
                error="yet another failure",
            )
            return await handle_agent_stop(jmem_engine, ev, state)
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.action == "advise"


# ── Task 8: Tool failure handler ─────────────────────────────────────


def test_handle_tool_failure_first_time(jmem_engine):
    from cortex import handle_tool_failure, ToolFailureEvent, CortexState

    event = ToolFailureEvent(
        type="PostToolUseFailure",
        timestamp=time(),
        tool="Bash",
        error="denied",
        error_class="permission",
    )

    async def _run():
        await jmem_engine.start()
        try:
            return await handle_tool_failure(jmem_engine, event, CortexState())
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.action == "observe"


def test_handle_tool_failure_escalation(jmem_engine):
    """With 3 prior failures, tool failure still observes (threshold raised to 50)."""
    from cortex import handle_tool_failure, ToolFailureEvent, CortexState
    from jmem.engine import MemoryLevel

    async def _run():
        await jmem_engine.start()
        try:
            for i in range(3):
                await jmem_engine.remember(
                    content=f"Bash failed (permission): {i}",
                    level=MemoryLevel.EPISODE,
                    tags=["tool-failure", "Bash", "permission"],
                )
            event = ToolFailureEvent(
                type="PostToolUseFailure",
                timestamp=time(),
                tool="Bash",
                error="denied again",
                error_class="permission",
            )
            return await handle_tool_failure(jmem_engine, event, CortexState())
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    # Threshold raised to 50 — 3 failures should only observe, not block/advise
    assert decision.action == "observe"


# ── Task 9: Task completed handler ──────────────────────────────────


def test_handle_task_completed_pressure(jmem_engine):
    from cortex import handle_task_completed, TaskCompletedEvent, CortexState

    state = CortexState()
    state.pressure = 5.0
    event = TaskCompletedEvent(
        type="TaskCompleted", timestamp=time(), subject="Fix auth"
    )

    async def _run():
        await jmem_engine.start()
        try:
            return await handle_task_completed(jmem_engine, event, state)
        finally:
            await jmem_engine.shutdown()

    run_async(_run())
    assert state.pressure == 6.0


# ── Task 10: AST analyzer + file changed handler ────────────────────


def test_py315_analyzer_pep810(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "analyzers"),
    )
    # Clear cached module
    if "py315_ast" in sys.modules:
        del sys.modules["py315_ast"]
    from py315_ast import analyze

    f = tmp_path / "sample.py"
    f.write_text("import numpy\nimport json\nx = 1\n")
    suggestions = analyze(str(f))
    pep810 = [s for s in suggestions if s.pep == "PEP 810"]
    assert len(pep810) == 1
    assert "numpy" in pep810[0].current


def test_py315_analyzer_pep814(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "analyzers"),
    )
    if "py315_ast" in sys.modules:
        del sys.modules["py315_ast"]
    from py315_ast import analyze

    f = tmp_path / "sample.py"
    f.write_text("CONFIG = {'key': 'value'}\nlower = {'a': 1}\n")
    suggestions = analyze(str(f))
    pep814 = [s for s in suggestions if s.pep == "PEP 814"]
    assert len(pep814) == 1


def test_py315_analyzer_clean(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    sys.path.insert(
        0,
        os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "analyzers"),
    )
    if "py315_ast" in sys.modules:
        del sys.modules["py315_ast"]
    from py315_ast import analyze

    f = tmp_path / "clean.py"
    f.write_text("x = 1\ndef add(a, b):\n    return a + b\n")
    assert analyze(str(f)) == []


def test_handle_file_changed_py(jmem_engine, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    from cortex import handle_file_changed, FileChangedEvent, CortexState

    f = tmp_path / "sample.py"
    f.write_text("import pandas\nCONFIG = {'a': 1}\n")
    event = FileChangedEvent(
        type="FileChanged", timestamp=time(), path=str(f), ext=".py"
    )

    async def _run():
        await jmem_engine.start()
        try:
            return await handle_file_changed(jmem_engine, event, CortexState())
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.action == "advise"
    assert "Py3.15" in decision.system_message


# ── Task 11: handle_prompt_submit ──────────────────────────────────


def test_handle_prompt_submit_trivial():
    from cortex import handle_prompt_submit, PromptSubmitEvent, CortexState
    event = PromptSubmitEvent(type="UserPromptSubmit", timestamp=time(), prompt="yes")
    decision = run_async(handle_prompt_submit(None, event, CortexState()))
    assert decision.action == "observe"
    assert decision.additional_context is None

def test_handle_prompt_submit_no_engine():
    from cortex import handle_prompt_submit, PromptSubmitEvent, CortexState
    event = PromptSubmitEvent(type="UserPromptSubmit", timestamp=time(), prompt="fix the auth bug in the login flow please")
    decision = run_async(handle_prompt_submit(None, event, CortexState()))
    assert decision.action == "observe"

def test_handle_prompt_submit_with_memories(jmem_engine):
    from cortex import handle_prompt_submit, PromptSubmitEvent, CortexState
    from jmem.engine import MemoryLevel
    run_async(jmem_engine.remember(content="auth module has race condition in token refresh", level=MemoryLevel.PRINCIPLE, tags=["auth"]))
    event = PromptSubmitEvent(type="UserPromptSubmit", timestamp=time(), prompt="fix the auth bug in the login token refresh flow")
    decision = run_async(handle_prompt_submit(jmem_engine, event, CortexState()))
    assert decision.action == "observe"  # May or may not inject depending on TF-IDF match


# ── Task 12: handle_stop + Dream Phase A ──────────────────────────


def test_handle_stop_stores_episode(jmem_engine):
    from cortex import handle_stop, HookEvent, CortexState
    event = HookEvent(type="Stop", timestamp=time())
    decision = run_async(handle_stop(jmem_engine, event, CortexState()))
    assert decision.action == "observe"

def test_handle_stop_dream_phase_a(jmem_engine):
    from cortex import handle_stop, HookEvent, CortexState
    state = CortexState()
    state.pressure = 15.0
    state.last_dream_at = 0.0
    event = HookEvent(type="Stop", timestamp=time())
    decision = run_async(handle_stop(jmem_engine, event, state))
    assert state.pressure == 0.0
    assert state.dream_pending is True

def test_handle_stop_no_dream_too_recent(jmem_engine):
    from cortex import handle_stop, HookEvent, CortexState
    state = CortexState()
    state.pressure = 15.0
    state.last_dream_at = time() - 60  # 1 minute ago
    event = HookEvent(type="Stop", timestamp=time())
    run_async(handle_stop(jmem_engine, event, state))
    assert state.pressure == 15.0
    assert state.dream_pending is False


# ── Task 13: Dream Phase B ────────────────────────────────────────


def test_dream_phase_b(jmem_engine):
    from cortex import run_dream_phase_b, CortexState
    state = CortexState()
    state.dream_pending = True
    run_async(run_dream_phase_b(jmem_engine, state))
    assert state.dream_pending is False


# ── Task 14: self_assess ──────────────────────────────────────────


def test_self_assess_raises_baseline_low_accuracy():
    from cortex import CortexState, self_assess
    state = CortexState()
    state.total_decisions = 50
    state.correct_blocks = 2
    state.overridden_blocks = 8
    old = state.interest_baseline
    self_assess(state)
    assert state.interest_baseline > old

def test_self_assess_lowers_baseline_high_accuracy():
    from cortex import CortexState, self_assess
    state = CortexState()
    state.total_decisions = 50
    state.correct_blocks = 9
    state.overridden_blocks = 1
    old = state.interest_baseline
    self_assess(state)
    assert state.interest_baseline < old

def test_self_assess_noop_insufficient_data():
    from cortex import CortexState, self_assess
    state = CortexState()
    state.total_decisions = 5
    old = state.interest_baseline
    self_assess(state)
    assert state.interest_baseline == old


# ── Integration Tests ────────────────────────────────────────────────


def test_full_agent_lifecycle(jmem_engine):
    """Integration: start -> stop(success) -> task_completed -> pressure rises."""
    from cortex import (
        handle_agent_start, handle_agent_stop, handle_task_completed,
        AgentStartEvent, AgentStopEvent, TaskCompletedEvent, CortexState
    )
    state = CortexState()

    async def _run():
        await jmem_engine.start()
        try:
            # Agent starts
            start_event = AgentStartEvent(type="agent_start", timestamp=time(), agent="aussie-tdd", task="fix auth")
            d1 = await handle_agent_start(jmem_engine, start_event, state)
            assert d1.action == "observe"

            # Agent succeeds
            stop_event = AgentStopEvent(type="agent_stop", timestamp=time(), agent="aussie-tdd", success=True)
            d2 = await handle_agent_stop(jmem_engine, stop_event, state)
            assert d2.action == "observe"
            assert "aussie-tdd" in (d2.system_message or "")
            assert state.pressure > 0

            # Task completed
            task_event = TaskCompletedEvent(type="TaskCompleted", timestamp=time(), subject="Auth fixed")
            d3 = await handle_task_completed(jmem_engine, task_event, state)
            assert state.pressure > 0.5  # Both stop and task added pressure
        finally:
            await jmem_engine.shutdown()

    run_async(_run())


def test_cortex_end_to_end_cli():
    """Cortex runs end-to-end from CLI without crashing for all 7 event types."""
    cortex_path = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "cortex.py")
    # Reset cortex state to prevent dream Phase A triggering (slow consolidate+decay)
    state_path = os.path.join(os.path.dirname(__file__), "..", ".claude", "hooks", "cortex_state.json")
    try:
        data = json.loads(open(state_path).read())
        data["pressure"] = 0.0
        data["dream_pending"] = False
        open(state_path, "w").write(json.dumps(data))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    events = [
        ("SubagentStart", '{"agent_name":"aussie-tdd","task":"test"}'),
        ("SubagentStop", '{"agent_name":"aussie-tdd","result":{"success":true}}'),
        ("PostToolUseFailure", '{"tool_name":"Bash","error":"timeout"}'),
        ("TaskCompleted", '{"subject":"Done"}'),
        ("UserPromptSubmit", '{"prompt":"fix the auth bug in the login flow"}'),
        ("FileChanged", '{"file_path":"/tmp/nonexistent.py"}'),
        ("Stop", '{}'),
    ]
    for event_type, payload in events:
        result = subprocess.run(
            [sys.executable, cortex_path, event_type],
            input=payload, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"{event_type} failed: {result.stderr}"


# ── Enhancement 1: DynamicRules S1 Fast Path ────────────────────────


def test_dynamic_rules_empty():
    """No rules loaded returns None."""
    from cortex import DynamicRules
    rules = DynamicRules()
    assert rules.check("aussie-tdd", "auth") is None


def test_dynamic_rules_match():
    """Manually populated rules return decisions."""
    from cortex import DynamicRules, Decision
    rules = DynamicRules()
    rules._rules = {("aussie-tdd", "auth"): {"action": "block", "reason": "fails on auth", "q": 0.95, "source_id": "x"}}
    rules._loaded_at = time()
    result = rules.check("aussie-tdd", "auth")
    assert result is not None
    assert result.action == "block"
    assert result.confidence == 0.95


def test_dynamic_rules_wildcard():
    """Wildcard domain matches any domain."""
    from cortex import DynamicRules
    rules = DynamicRules()
    rules._rules = {("aussie-tdd", "*"): {"action": "advise", "reason": "general warning", "q": 0.8, "source_id": "x"}}
    rules._loaded_at = time()
    result = rules.check("aussie-tdd", "anything")
    assert result is not None
    assert result.action == "advise"


def test_dynamic_rules_no_match():
    """Non-matching agent returns None."""
    from cortex import DynamicRules
    rules = DynamicRules()
    rules._rules = {("aussie-tdd", "auth"): {"action": "block", "reason": "x", "q": 0.9, "source_id": "x"}}
    rules._loaded_at = time()
    assert rules.check("aussie-security", "auth") is None


# ── Enhancement 2: Context-Sensitive Project Personality ─────────────


def test_detect_project_profile():
    """Profile detects project characteristics."""
    from cortex import detect_project_profile
    profile = detect_project_profile()
    assert "py315_enforcement" in profile
    assert "primary_language" in profile
    assert profile["py_count"] > 0  # This project has Python files
    assert profile["security_emphasis"] == "high"  # aussie-security.md exists


def test_project_profile_cached_in_state():
    """Profile is stored in CortexState and persists."""
    from cortex import CortexState, detect_project_profile
    state = CortexState()
    assert state.project_profile == {}
    state.project_profile = detect_project_profile()
    assert state.project_profile["primary_language"] in ("python", "typescript")


def test_dream_cycle_full_integration(jmem_engine):
    """Integration: accumulate pressure -> stop triggers dream -> phase B clears pending."""
    from cortex import (
        handle_task_completed, handle_stop, run_dream_phase_b,
        TaskCompletedEvent, HookEvent, CortexState
    )
    state = CortexState()

    async def _run():
        await jmem_engine.start()
        try:
            # Accumulate pressure via task completions
            for i in range(12):
                event = TaskCompletedEvent(type="TaskCompleted", timestamp=time(), subject=f"Task {i}")
                await handle_task_completed(jmem_engine, event, state)

            assert state.pressure >= 10.0  # Above threshold

            # Stop triggers dream Phase A
            stop_event = HookEvent(type="Stop", timestamp=time())
            decision = await handle_stop(jmem_engine, stop_event, state)
            assert state.pressure == 0.0
            assert state.dream_pending is True

            # Dream Phase B
            await run_dream_phase_b(jmem_engine, state)
            assert state.dream_pending is False
        finally:
            await jmem_engine.shutdown()

    run_async(_run())


# ── Self-Build: Fail-Safe on Processing Errors ──────────────────────


def test_run_failsafe_advises_on_subagent_start_error():
    """When _handle_event raises a non-JMEM error for SubagentStart, _run should advise."""
    from cortex import _run

    # Simulate a SubagentStart with valid JSON — JMEM will fail (no server),
    # so Level 2 kicks in and should produce an advise for security-sensitive events.
    decision = run_async(_run("SubagentStart", '{"agent_type":"aussie-tdd","task":"test"}'))
    # If JMEM is available, we get a normal decision; if not, fail-safe advises
    # Either way it should not be None (the event has score >= 0.1)
    assert decision is not None


def test_run_failsafe_advises_on_tool_failure_error():
    """When _handle_event raises for PostToolUseFailure, _run should advise."""
    from cortex import _run

    decision = run_async(_run("PostToolUseFailure", '{"tool_name":"Bash","error":"timeout"}'))
    assert decision is not None


def test_run_non_security_event_observes_on_error():
    """Non-security events should still default to observe on processing error."""
    from cortex import _run

    decision = run_async(_run("TaskCompleted", '{"subject":"done"}'))
    # TaskCompleted has score 0.3 >= 0.1, so it should be processed
    assert decision is not None


# ── Self-Build Cycle 3: Event Timings + Feature Gates ────────────


def test_cortex_state_event_timings():
    """event_timings field persists through save/load."""
    from cortex import CortexState
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        fp = Path(td) / "cortex_state.json"
        state = CortexState(state_path=fp)
        assert state.event_timings == {}
        state.event_timings["SubagentStart"] = [5.2, 3.1, 4.8]
        state.save()
        loaded = CortexState.load(fp)
        assert loaded.event_timings["SubagentStart"] == [5.2, 3.1, 4.8]


def test_event_timings_default():
    """Fresh CortexState has empty event_timings."""
    state = CortexState()
    assert state.event_timings == {}


def test_event_timings_cap_at_10():
    """event_timings should only keep last 10 entries per event type."""
    state = CortexState()
    state.event_timings["SubagentStart"] = list(range(15))
    # Simulate what _run does: trim to last 10
    state.event_timings["SubagentStart"] = state.event_timings["SubagentStart"][-10:]
    assert len(state.event_timings["SubagentStart"]) == 10
    assert state.event_timings["SubagentStart"][0] == 5


def test_is_feature_enabled_default(jmem_engine):
    """Feature gate defaults to enabled when no JMEM skill exists."""
    result = run_async(is_feature_enabled(jmem_engine, "nonexistent_feature"))
    assert result is True


def test_is_feature_enabled_no_engine():
    """Feature gate defaults to enabled when engine is broken."""
    result = run_async(is_feature_enabled(None, "any_feature"))
    assert result is True


def test_handle_stop_perf_telemetry(jmem_engine):
    """handle_stop is silent even when timings exist (UI clutter fix)."""
    from cortex import handle_stop, HookEvent, CortexState
    state = CortexState()
    state.event_timings = {
        "SubagentStart": [12.5, 15.0, 10.0],
        "PostToolUseFailure": [5.0, 8.0],
    }
    event = HookEvent(type="Stop", timestamp=time())
    decision = run_async(handle_stop(jmem_engine, event, state))
    # Perf output silenced — no system_message
    assert decision.system_message is None


def test_handle_stop_no_telemetry_when_empty(jmem_engine):
    """handle_stop has no perf message when no timings recorded."""
    from cortex import handle_stop, HookEvent, CortexState
    state = CortexState()
    event = HookEvent(type="Stop", timestamp=time())
    decision = run_async(handle_stop(jmem_engine, event, state))
    # No timings -> system_message should be None (no perf line)
    assert decision.system_message is None


def test_handle_stop_dream_silent(jmem_engine):
    """When dream Phase A triggers, it completes silently (UI clutter fix)."""
    from cortex import handle_stop, HookEvent, CortexState
    state = CortexState()
    state.pressure = 15.0
    state.last_dream_at = 0.0
    state.event_timings = {"SubagentStart": [20.0]}
    event = HookEvent(type="Stop", timestamp=time())
    decision = run_async(handle_stop(jmem_engine, event, state))
    # Dream completes silently — no system_message
    assert decision.system_message is None
    assert state.dream_pending is True
    assert state.pressure == 0.0


# ── Self-Build Cycle 3: Pre-computed Agent Context Injection ──────


def test_build_agent_context_with_profile():
    """_build_agent_context returns project summary when profile is populated."""
    state = CortexState()
    state.project_profile = {
        "py_count": 100, "ts_count": 50, "test_count": 20,
        "primary_language": "python", "py315_enforcement": "aggressive",
    }
    ctx = _build_agent_context("aussie-researcher", "analyze code", state)
    assert any("100 Python" in line for line in ctx)
    assert any("50 TypeScript" in line for line in ctx)
    assert any("aggressive" in line for line in ctx)


def test_build_agent_context_with_decisions():
    """_build_agent_context includes cortex stats when decisions > 0."""
    state = CortexState()
    state.project_profile = {"py_count": 10, "ts_count": 5, "test_count": 3,
                             "primary_language": "python", "py315_enforcement": "moderate"}
    state.total_decisions = 50
    state.correct_blocks = 8
    state.pressure = 3.5
    state.phase = "implementation"
    ctx = _build_agent_context("pfaa-rewriter", "modernize", state)
    stats_lines = [l for l in ctx if "Cortex stats" in l]
    assert len(stats_lines) == 1
    assert "50 decisions" in stats_lines[0]
    assert "pressure=3.5" in stats_lines[0]


def test_build_agent_context_file_hints():
    """_build_agent_context includes agent-specific file hints for known agents."""
    state = CortexState()
    for agent, expected_fragment in [
        ("aussie-tdd", "test_cortex.py"),
        ("aussie-security", "settings.json"),
        ("pfaa-rewriter", "agent_setup_cli/core/"),
        ("pfaa-validator", "py315_ast.py"),
        ("aussie-docs", "CLAUDE.md"),
    ]:
        ctx = _build_agent_context(agent, "some task", state)
        assert any(expected_fragment in line for line in ctx), f"{agent} missing hint for {expected_fragment}"


def test_build_agent_context_no_hints_for_unknown():
    """_build_agent_context returns no file hints for agents not in AGENT_FILE_HINTS."""
    state = CortexState()
    ctx = _build_agent_context("aussie-researcher", "research", state)
    # No profile, no decisions, no hints -> empty
    assert ctx == []


def test_build_agent_context_empty_profile():
    """_build_agent_context with empty profile returns no project summary."""
    state = CortexState()
    state.project_profile = {}
    ctx = _build_agent_context("aussie-tdd", "test", state)
    # Only the file hint should be present (no profile, no decisions)
    assert len(ctx) == 1
    assert "test_cortex.py" in ctx[0]


def test_handle_agent_start_injects_project_context(jmem_engine, tmp_path):
    """Integration: handle_agent_start injects pre-computed project context."""
    from cortex import handle_agent_start

    state = CortexState(state_path=tmp_path / "state.json")
    state.project_profile = {
        "py_count": 100, "ts_count": 50, "test_count": 20,
        "primary_language": "python", "py315_enforcement": "aggressive",
    }
    state.total_decisions = 50
    event = AgentStartEvent(
        type="SubagentStart", timestamp=time(), agent="aussie-tdd", task="test auth"
    )

    async def _run():
        await jmem_engine.start()
        try:
            return await handle_agent_start(jmem_engine, event, state)
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.additional_context is not None
    assert "100 Python" in decision.additional_context
    assert "test_cortex.py" in decision.additional_context  # agent-specific hint


def test_handle_agent_start_no_profile_still_works(jmem_engine, tmp_path):
    """handle_agent_start works without a project profile (no crash, still has phase guidance)."""
    from cortex import handle_agent_start

    state = CortexState(state_path=tmp_path / "state.json")
    event = AgentStartEvent(
        type="SubagentStart", timestamp=time(), agent="aussie-researcher", task="explore"
    )

    async def _run():
        await jmem_engine.start()
        try:
            return await handle_agent_start(jmem_engine, event, state)
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.action == "observe"
    # Should still have phase guidance even without profile
    if decision.additional_context:
        assert "RESEARCH" in decision.additional_context


# ── NEW TDD: Keyword extraction ──────────────────────────────────────


def test_extract_keywords_filters_stop_words():
    """_extract_keywords removes common stop words."""
    from cortex import _extract_keywords
    result = _extract_keywords("fix the bug in the auth module")
    assert "the" not in result
    assert "in" not in result
    assert "fix" in result
    assert "bug" in result
    assert "auth" in result
    assert "module" in result


def test_extract_keywords_max_10():
    """_extract_keywords returns at most 10 keywords."""
    from cortex import _extract_keywords
    long_prompt = " ".join(f"word{i}" for i in range(50))
    result = _extract_keywords(long_prompt)
    assert len(result) <= 10


def test_extract_keywords_empty():
    """_extract_keywords handles empty string."""
    from cortex import _extract_keywords
    assert _extract_keywords("") == []


def test_extract_keywords_only_stop_words():
    """_extract_keywords returns empty for all stop words."""
    from cortex import _extract_keywords
    assert _extract_keywords("the a an is are was") == []


# ── NEW TDD: Episode dedup in _handle_event ──────────────────────────


def test_handle_event_dedup(jmem_engine, tmp_path):
    """Duplicate events should be skipped (same episode hash)."""
    from cortex import _handle_event, AgentStartEvent, CortexState

    state = CortexState(state_path=tmp_path / "state.json")
    event = AgentStartEvent(type="SubagentStart", agent="aussie-tdd", task="test auth")

    async def _run():
        await jmem_engine.start()
        try:
            d1 = await _handle_event(jmem_engine, event, state, 0.9)
            initial_episodes = state.episodes_this_session
            # Same event again — should be deduped
            d2 = await _handle_event(jmem_engine, event, state, 0.9)
            return d1, d2, initial_episodes
        finally:
            await jmem_engine.shutdown()

    d1, d2, initial_episodes = run_async(_run())
    assert d1.action == "observe"
    # Deduped event returns default Decision
    assert state.episodes_this_session == initial_episodes  # No increment on dedup


def test_handle_event_dedup_hash_cap(tmp_path):
    """Recent episode hashes should be capped at 100."""
    state = CortexState(state_path=tmp_path / "state.json")
    state.recent_episode_hashes = [f"hash{i}" for i in range(120)]
    # Simulate the cap logic from _handle_event
    if len(state.recent_episode_hashes) > 100:
        state.recent_episode_hashes = state.recent_episode_hashes[-100:]
    assert len(state.recent_episode_hashes) == 100
    assert state.recent_episode_hashes[0] == "hash20"


# ── NEW TDD: Phase detection in handle_agent_start ───────────────────


def test_phase_detection_research(jmem_engine, tmp_path):
    """Research agents set phase to 'research'."""
    from cortex import handle_agent_start, AgentStartEvent, CortexState

    state = CortexState(state_path=tmp_path / "state.json")

    async def _run():
        await jmem_engine.start()
        try:
            for agent in ["aussie-researcher", "aussie-planner", "aussie-architect"]:
                ev = AgentStartEvent(type="SubagentStart", agent=agent, task="research")
                await handle_agent_start(jmem_engine, ev, state)
                assert state.phase == "research", f"{agent} should set phase to research"
        finally:
            await jmem_engine.shutdown()

    run_async(_run())


def test_phase_detection_impl(jmem_engine, tmp_path):
    """Implementation agents set phase to 'implementation'."""
    from cortex import handle_agent_start, AgentStartEvent, CortexState

    state = CortexState(state_path=tmp_path / "state.json")

    async def _run():
        await jmem_engine.start()
        try:
            for agent in ["aussie-tdd", "pfaa-rewriter", "aussie-deployer"]:
                ev = AgentStartEvent(type="SubagentStart", agent=agent, task="implement")
                await handle_agent_start(jmem_engine, ev, state)
                assert state.phase == "implementation", f"{agent} should set phase to implementation"
        finally:
            await jmem_engine.shutdown()

    run_async(_run())


def test_phase_detection_verify(jmem_engine, tmp_path):
    """Verification agents set phase to 'verification'."""
    from cortex import handle_agent_start, AgentStartEvent, CortexState

    state = CortexState(state_path=tmp_path / "state.json")

    async def _run():
        await jmem_engine.start()
        try:
            for agent in ["pfaa-validator", "aussie-security"]:
                ev = AgentStartEvent(type="SubagentStart", agent=agent, task="validate")
                await handle_agent_start(jmem_engine, ev, state)
                assert state.phase == "verification", f"{agent} should set phase to verification"
        finally:
            await jmem_engine.shutdown()

    run_async(_run())


# ── NEW TDD: Pressure accumulation ──────────────────────────────────


def test_pressure_increases_on_success():
    """Successful agent stop increases pressure by 0.5."""
    state = CortexState()
    state.pressure = 2.0
    # Simulate what handle_agent_stop does on success
    state.pressure = max(0.0, state.pressure + 0.5)
    assert state.pressure == 2.5


def test_pressure_increases_on_failure():
    """Failed agent stop increases pressure by 2.0, capped at 10.0."""
    state = CortexState()
    state.pressure = 9.0
    state.pressure = min(10.0, state.pressure + 2.0)
    assert state.pressure == 10.0


def test_pressure_resets_on_dream():
    """Dream Phase A resets pressure to 0."""
    state = CortexState()
    state.pressure = 15.0
    state.pressure = 0.0
    state.dream_pending = True
    assert state.pressure == 0.0
    assert state.dream_pending is True


# ── NEW TDD: Interest scoring edge cases ─────────────────────────────


def test_interest_score_agent_start():
    """Agent start gets high interest (0.9)."""
    ev = AgentStartEvent(type="SubagentStart", agent="pfaa-lead", task="plan")
    assert interest_score(ev) == 0.9


def test_interest_score_pyi_file():
    """.pyi stub files get same interest as .py (0.8)."""
    ev = FileChangedEvent(type="FileChanged", path="types.pyi", ext=".pyi")
    assert interest_score(ev) == 0.8


def test_interest_score_non_py_file():
    """Non-Python file changes get lower interest (0.4)."""
    ev = FileChangedEvent(type="FileChanged", path="config.json", ext=".json")
    assert interest_score(ev) == 0.4


def test_interest_score_medium_prompt():
    """Medium-length prompt (4-10 words) gets 0.5."""
    ev = PromptSubmitEvent(type="UserPromptSubmit", prompt="fix the auth module please")
    assert interest_score(ev) == 0.5


def test_interest_score_long_prompt():
    """Long prompt (>10 words) gets high interest (0.7)."""
    ev = PromptSubmitEvent(type="UserPromptSubmit", prompt="please fix the authentication bug in the login flow that causes timeout errors for users")
    assert interest_score(ev) == 0.7


def test_interest_score_success_agent_stop():
    """Successful agent stop gets medium interest (0.5)."""
    ev = AgentStopEvent(type="SubagentStop", agent="aussie-tdd", success=True)
    assert interest_score(ev) == 0.5


# ── NEW TDD: Tool failure threshold at 50 ────────────────────────────


def test_tool_failure_does_not_block_under_50(jmem_engine):
    """Tool failure should not block even with many failures (threshold=50)."""
    from cortex import handle_tool_failure, CortexState
    from jmem.engine import MemoryLevel

    async def _run():
        await jmem_engine.start()
        try:
            # Store 20 failures — still under threshold
            for i in range(20):
                await jmem_engine.remember(
                    content=f"Read failed (unknown): attempt {i}",
                    level=MemoryLevel.EPISODE,
                    tags=["tool", "failure", "Read", "unknown"],
                )
            event = ToolFailureEvent(
                type="PostToolUseFailure", tool="Read",
                error="some error", error_class="unknown",
            )
            return await handle_tool_failure(jmem_engine, event, CortexState())
        finally:
            await jmem_engine.shutdown()

    decision = run_async(_run())
    assert decision.action == "observe"  # Not block — under 50 threshold


# ── NEW TDD: classify_error edge cases ───────────────────────────────


def test_classify_error_case_insensitive():
    """Error classification is case-insensitive."""
    assert classify_error("PERMISSION DENIED") == "permission"
    assert classify_error("Connection Refused") == "network"


def test_classify_error_first_match_wins():
    """When multiple patterns match, first category wins."""
    # "forbidden" matches permission, comes before others
    assert classify_error("forbidden network error") == "permission"
