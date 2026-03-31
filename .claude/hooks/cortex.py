"""
Aussie Cortex — Self-improving RL hook processor for Claude Code.

CortexState is the operational state that persists between hook invocations
via atomic JSON file writes. It tracks pressure, phase, error counts,
decision statistics, and JMEM integration metadata.

This module is the foundation of the cortex hook system. Higher-level
components (decisions, event handlers, RL policies) build on top of this
state and are added in subsequent tasks.
"""

import json
import os
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from time import time

# ── Path constants ──────────────────────────────────────────────────

PROJECT_ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR")
    or os.environ.get("PWD")
    or "/Users/borris/Desktop/pfaa-engine"
)

JMEM_PATH = PROJECT_ROOT / "jmem-mcp-server"
STATE_PATH = PROJECT_ROOT / ".claude" / "hooks" / "cortex_state.json"


# ── CortexState ────────────────────────────────────────────────────


@dataclass
class CortexState:
    """Persistent operational state for the Aussie Cortex hook processor."""

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

    # ── Persistence ─────────────────────────────────────────────────

    def save(self) -> None:
        """Atomic write: serialize to temp file, then os.replace() into place."""
        data = {}
        for f in fields(self):
            if f.name == "state_path":
                continue
            val = getattr(self, f.name)
            # Convert set to sorted list for JSON serialization
            if isinstance(val, set):
                val = sorted(val)
            data[f.name] = val

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2))
            os.replace(tmp, self.state_path)
        except BaseException:
            # Clean up temp file on any failure
            if tmp.exists():
                tmp.unlink()
            raise

    @classmethod
    def load(cls, path: Path = STATE_PATH) -> "CortexState":
        """Load state from JSON, returning defaults if file is missing or corrupt."""
        try:
            data = json.loads(Path(path).read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return cls(state_path=path)

        # Convert disabled_handlers list back to set
        if "disabled_handlers" in data:
            data["disabled_handlers"] = set(data["disabled_handlers"])

        # Only pass fields that the dataclass knows about (forward compat)
        known = {f.name for f in fields(cls)} - {"state_path"}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(state_path=path, **filtered)
