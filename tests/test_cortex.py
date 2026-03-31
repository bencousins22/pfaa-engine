"""Tests for CortexState, Decision, and Event types — Aussie Cortex hook system."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

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
    return JMemEngine()


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
