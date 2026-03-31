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
    def load(cls, path: Path | None = STATE_PATH) -> "CortexState":
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


# ── Decision ──────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Decision:
    """What the cortex tells Claude Code to do."""

    action: str = "observe"
    system_message: str | None = None
    additional_context: str | None = None
    block_reason: str | None = None
    confidence: float = 0.0

    def to_json(self) -> str:
        out: dict = {}
        if self.action == "block" and self.block_reason:
            out["decision"] = "block"
            out["reason"] = self.block_reason
        if self.system_message:
            out["systemMessage"] = self.system_message
        if self.additional_context:
            out["hookSpecificOutput"] = {"additionalContext": self.additional_context}
        return json.dumps(out) if out else ""


# ── Error classifier ──────────────────────────────────────────────

ERROR_PATTERNS: dict[str, list[str]] = {
    "permission": ["permission", "denied", "forbidden", "unauthorized"],
    "timeout": ["timeout", "timed out", "deadline exceeded"],
    "not_found": ["not found", "no such file", "does not exist", "enoent"],
    "syntax": ["syntax", "parse error", "unexpected token", "invalid"],
    "network": ["connection", "network", "econnrefused", "dns"],
    "resource": ["out of memory", "disk full", "too many open files"],
}


def classify_error(error: str) -> str:
    """Classify an error message into a known category."""
    lower = error.lower()
    for cls, patterns in ERROR_PATTERNS.items():
        if any(p in lower for p in patterns):
            return cls
    return "unknown"


# ── Hook events ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HookEvent:
    """Base event produced by a Claude Code hook invocation."""

    type: str = "unknown"
    timestamp: float = field(default_factory=time)

    def to_episode(self) -> str:
        """Human-readable summary for JMEM episodic memory."""
        return f"[{self.type}] event at {self.timestamp:.1f}"

    def tags(self) -> list[str]:
        """Classification tags for the event."""
        return [self.type]


@dataclass(frozen=True, slots=True)
class AgentStartEvent(HookEvent):
    """An agent has started working on a task."""

    agent: str = "unknown"
    task: str = ""

    def to_episode(self) -> str:
        return f"Agent {self.agent} started task: {self.task}"

    def tags(self) -> list[str]:
        return ["agent", "start", self.agent]


@dataclass(frozen=True, slots=True)
class AgentStopEvent(HookEvent):
    """An agent has finished (success or failure)."""

    agent: str = "unknown"
    success: bool = False
    error: str | None = None

    def to_episode(self) -> str:
        if self.success:
            return f"Agent {self.agent} completed successfully"
        return f"Agent {self.agent} failed: {self.error or 'unknown error'}"

    def tags(self) -> list[str]:
        tags = ["agent", "stop", self.agent]
        if not self.success:
            tags.append("error")
        return tags


@dataclass(frozen=True, slots=True)
class ToolFailureEvent(HookEvent):
    """A tool invocation failed."""

    tool: str = "unknown"
    error: str = ""
    error_class: str = "unknown"

    def to_episode(self) -> str:
        return f"Tool {self.tool} failed ({self.error_class}): {self.error}"

    def tags(self) -> list[str]:
        return ["tool", "failure", self.tool, self.error_class]


@dataclass(frozen=True, slots=True)
class FileChangedEvent(HookEvent):
    """A file was created or modified."""

    path: str = ""
    ext: str = ""

    def to_episode(self) -> str:
        return f"File changed: {self.path}"

    def tags(self) -> list[str]:
        tags = ["file", "changed"]
        if self.ext:
            tags.append(self.ext)
        return tags


@dataclass(frozen=True, slots=True)
class TaskCompletedEvent(HookEvent):
    """A task or sub-goal was completed."""

    subject: str = ""
    description: str = ""

    def to_episode(self) -> str:
        return f"Task completed — {self.subject}: {self.description}"

    def tags(self) -> list[str]:
        return ["task", "completed", self.subject]


@dataclass(frozen=True, slots=True)
class PromptSubmitEvent(HookEvent):
    """The user submitted a prompt."""

    prompt: str = ""

    def to_episode(self) -> str:
        return f"User prompt: {self.prompt}"

    def tags(self) -> list[str]:
        return ["prompt", "user_input"]


# ── Event dispatcher ──────────────────────────────────────────────


def parse_event(event_type: str, payload: dict) -> HookEvent:
    """Parse a raw hook payload into a typed HookEvent. Never crashes on missing fields."""
    ts = time()
    match event_type:
        case "agent_start":
            return AgentStartEvent(
                type=event_type,
                timestamp=ts,
                agent=payload.get("agent", "unknown"),
                task=payload.get("task", ""),
            )
        case "agent_stop":
            return AgentStopEvent(
                type=event_type,
                timestamp=ts,
                agent=payload.get("agent", "unknown"),
                success=payload.get("success", False),
                error=payload.get("error", None),
            )
        case "tool_failure":
            error_msg = payload.get("error", "")
            return ToolFailureEvent(
                type=event_type,
                timestamp=ts,
                tool=payload.get("tool", "unknown"),
                error=error_msg,
                error_class=classify_error(error_msg),
            )
        case "file_changed":
            file_path = payload.get("path", "")
            ext = Path(file_path).suffix if file_path else ""
            return FileChangedEvent(
                type=event_type,
                timestamp=ts,
                path=file_path,
                ext=ext,
            )
        case "task_completed":
            return TaskCompletedEvent(
                type=event_type,
                timestamp=ts,
                subject=payload.get("subject", ""),
                description=payload.get("description", ""),
            )
        case "prompt_submit":
            return PromptSubmitEvent(
                type=event_type,
                timestamp=ts,
                prompt=payload.get("prompt", ""),
            )
        case _:
            return HookEvent(type=event_type, timestamp=ts)
