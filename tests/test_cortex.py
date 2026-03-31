"""Tests for CortexState, Decision, and Event types — Aussie Cortex hook system."""

import json
import os
import sys

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
    ev = parse_event("agent_start", {"agent": "pfaa-lead", "task": "deploy v2"})
    assert isinstance(ev, AgentStartEvent)
    assert ev.type == "agent_start"
    assert ev.agent == "pfaa-lead"
    assert ev.task == "deploy v2"
    assert ev.timestamp > 0
    episode = ev.to_episode()
    assert "pfaa-lead" in episode
    assert "deploy v2" in episode
    assert "agent" in ev.tags()


def test_parse_agent_stop_success():
    """AgentStopEvent with success=True and no error."""
    ev = parse_event("agent_stop", {"agent": "aussie-tdd", "success": True})
    assert isinstance(ev, AgentStopEvent)
    assert ev.success is True
    assert ev.error is None
    assert "success" in ev.to_episode().lower() or "completed" in ev.to_episode().lower()


def test_parse_agent_stop_failure():
    """AgentStopEvent with success=False and error populated."""
    ev = parse_event(
        "agent_stop",
        {"agent": "aussie-tdd", "success": False, "error": "Timeout exceeded"},
    )
    assert isinstance(ev, AgentStopEvent)
    assert ev.success is False
    assert ev.error == "Timeout exceeded"
    assert "fail" in ev.to_episode().lower() or "error" in ev.to_episode().lower()


def test_parse_file_changed():
    """FileChangedEvent extracts path and extension."""
    ev = parse_event("file_changed", {"path": "src/core/engine.ts"})
    assert isinstance(ev, FileChangedEvent)
    assert ev.path == "src/core/engine.ts"
    assert ev.ext == ".ts"
    assert "file" in ev.tags()


def test_parse_tool_failure():
    """ToolFailureEvent classifies error correctly."""
    ev = parse_event(
        "tool_failure",
        {"tool": "Bash", "error": "Permission denied: /etc/shadow"},
    )
    assert isinstance(ev, ToolFailureEvent)
    assert ev.tool == "Bash"
    assert ev.error_class == "permission"
    assert "tool" in ev.tags()


def test_parse_prompt_submit():
    """PromptSubmitEvent extracts prompt text."""
    ev = parse_event("prompt_submit", {"prompt": "refactor the memory store"})
    assert isinstance(ev, PromptSubmitEvent)
    assert ev.prompt == "refactor the memory store"
    assert "prompt" in ev.tags()


def test_parse_task_completed():
    """TaskCompletedEvent extracts subject."""
    ev = parse_event(
        "task_completed",
        {"subject": "deploy", "description": "Deployed v2.1 to prod"},
    )
    assert isinstance(ev, TaskCompletedEvent)
    assert ev.subject == "deploy"
    assert ev.description == "Deployed v2.1 to prod"
    assert "task" in ev.tags()


def test_parse_unknown_event():
    """Unknown event type returns base HookEvent, never crashes."""
    ev = parse_event("totally_new_event", {"foo": "bar"})
    assert isinstance(ev, HookEvent)
    assert ev.type == "totally_new_event"


def test_parse_missing_fields():
    """Empty payload produces defaults, never crashes."""
    for event_type in [
        "agent_start",
        "agent_stop",
        "tool_failure",
        "file_changed",
        "task_completed",
        "prompt_submit",
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
