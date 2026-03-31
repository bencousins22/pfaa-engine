"""Tests for CortexState — atomic JSON persistence for the Aussie Cortex hook system."""

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

from cortex import CortexState, STATE_PATH


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
