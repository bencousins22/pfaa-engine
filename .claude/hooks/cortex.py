"""
Aussie Cortex — Self-improving RL hook processor for Claude Code.

CortexState is the operational state that persists between hook invocations
via atomic JSON file writes. It tracks pressure, phase, error counts,
decision statistics, and JMEM integration metadata.

This module is the foundation of the cortex hook system. Higher-level
components (decisions, event handlers, RL policies) build on top of this
state and are added in subsequent tasks.
"""

import asyncio
import hashlib
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

    # ── Circuit breaker ──────────────────────────────────────────────

    def record_error(self, handler: str) -> None:
        self.error_counts[handler] = self.error_counts.get(handler, 0) + 1
        if self.error_counts[handler] >= 3:
            self.disabled_handlers.add(handler)

    def record_success(self, handler: str) -> None:
        self.error_counts[handler] = 0
        self.disabled_handlers.discard(handler)

    def is_disabled(self, handler: str) -> bool:
        return handler in self.disabled_handlers

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


# ── Interest scoring ─────────────────────────────────────────────


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


# ── Phase constants ──────────────────────────────────────────────

RESEARCH_AGENTS = frozenset({"aussie-researcher", "aussie-planner", "aussie-architect"})
IMPL_AGENTS = frozenset({"aussie-tdd", "pfaa-rewriter", "aussie-deployer"})
VERIFY_AGENTS = frozenset({"pfaa-validator", "aussie-security"})
PHASE_GUIDANCE = {
    "research": "RESEARCH phase: focus on gathering information, do not implement.",
    "synthesis": "SYNTHESIS phase: synthesize research findings into a spec.",
    "implementation": "IMPLEMENTATION phase: implement per the synthesized spec.",
    "verification": "VERIFICATION phase: validate implementation, check for issues.",
}

AGENT_NAMES = frozenset({
    "pfaa-lead", "aussie-researcher", "aussie-planner", "aussie-architect",
    "aussie-security", "aussie-tdd", "pfaa-rewriter", "pfaa-validator",
    "aussie-deployer", "aussie-docs",
})


# ── Agent handlers ───────────────────────────────────────────────


async def handle_agent_start(engine, event: AgentStartEvent, state: CortexState) -> Decision:
    """Handle an agent starting — detect phase, recall history, provide context."""
    # Store L1 episode
    from jmem.engine import MemoryLevel

    await engine.remember(
        content=event.to_episode(),
        level=MemoryLevel.EPISODE,
        context=f"agent_start:{event.agent}",
        tags=event.tags(),
    )

    # Detect phase from agent type
    if event.agent in RESEARCH_AGENTS:
        state.phase = "research"
    elif event.agent in IMPL_AGENTS:
        state.phase = "implementation"
    elif event.agent in VERIFY_AGENTS:
        state.phase = "verification"
    else:
        state.phase = "synthesis"

    # Recall agent history
    history = await engine.recall(
        query=f"agent {event.agent}",
        limit=5,
        min_q=0.3,
    )

    # Build context: phase guidance + cross-agent findings
    parts = []
    guidance = PHASE_GUIDANCE.get(state.phase)
    if guidance:
        parts.append(guidance)

    # Cross-agent findings: memories tagged with other agents
    cross_findings = [
        n for n in history
        if event.agent not in n.tags and any(a in n.tags for a in AGENT_NAMES)
    ]
    for finding in cross_findings[:3]:
        parts.append(f"[cross-agent] {finding.content[:120]}")

    # Block if 3+ failures AND avg Q < 0.4
    failure_notes = [n for n in history if "error" in n.tags]
    if len(failure_notes) >= 3:
        avg_q = sum(n.q_value for n in failure_notes) / len(failure_notes)
        if avg_q < 0.4:
            return Decision(
                action="block",
                block_reason=f"Agent {event.agent} has {len(failure_notes)} recent failures with avg Q={avg_q:.2f}. Investigate before retrying.",
                confidence=0.8,
            )

    context = "\n".join(parts) if parts else None
    return Decision(action="observe", additional_context=context)


async def handle_agent_stop(engine, event: AgentStopEvent, state: CortexState) -> Decision:
    """Handle an agent finishing — reward/penalize, detect repeated failure."""
    from jmem.engine import MemoryLevel

    # Store L1 episode
    await engine.remember(
        content=event.to_episode(),
        level=MemoryLevel.EPISODE,
        context=f"agent_stop:{event.agent}",
        tags=event.tags(),
    )

    if event.success:
        # Reward recalled memories
        await engine.reward_recalled(reward_signal=0.8)
        state.pressure = max(0.0, state.pressure + 0.5)
        return Decision(
            action="observe",
            system_message=f"Agent {event.agent} completed successfully. Pressure: {state.pressure:.1f}",
            confidence=0.6,
        )

    # Failure path
    await engine.reward_recalled(reward_signal=-0.5)
    state.pressure = min(10.0, state.pressure + 2.0)

    # Count recent failures (1h window) by recalling failure episodes
    recent_failures = await engine.recall(
        query=f"agent {event.agent} failed error",
        limit=10,
        level=MemoryLevel.EPISODE,
    )
    # Filter to those tagged as errors for this agent
    agent_failures = [
        n for n in recent_failures
        if "error" in n.tags and event.agent in n.tags
    ]

    if len(agent_failures) >= 3:
        # Store L2 Concept about repeated failure
        await engine.remember(
            content=f"Agent {event.agent} has failed {len(agent_failures)} times recently. Pattern: repeated failures suggest systemic issue.",
            level=MemoryLevel.CONCEPT,
            context=f"repeated_failure:{event.agent}",
            keywords=[event.agent, "repeated-failure", "systemic"],
            tags=["agent", "failure-pattern", event.agent],
        )
        return Decision(
            action="advise",
            system_message=f"Agent {event.agent} has failed {len(agent_failures)} times recently. Consider investigating root cause before retrying. Pressure: {state.pressure:.1f}",
            confidence=0.8,
        )

    return Decision(
        action="observe",
        system_message=f"Agent {event.agent} failed: {event.error or 'unknown'}. Pressure: {state.pressure:.1f}",
        confidence=0.4,
    )


# ── Core event processor ─────────────────────────────────────────


async def _handle_event(engine, event: HookEvent, state: CortexState, score: float) -> Decision:
    """Process a hook event through the cortex. Store L1 episode with dedup, then route."""
    # Dedup: skip if we already processed an identical episode recently
    episode_text = event.to_episode()
    ep_hash = hashlib.sha256(episode_text.encode()).hexdigest()[:12]

    if ep_hash in state.recent_episode_hashes:
        return Decision()

    state.recent_episode_hashes.append(ep_hash)
    # Keep only last 100 hashes
    if len(state.recent_episode_hashes) > 100:
        state.recent_episode_hashes = state.recent_episode_hashes[-100:]

    state.episodes_this_session += 1
    state.total_decisions += 1

    # Route to specific handlers
    match event:
        case AgentStartEvent():
            return await handle_agent_start(engine, event, state)
        case AgentStopEvent():
            return await handle_agent_stop(engine, event, state)
        case _:
            return Decision()


# ── Entry point with 4-level degradation ─────────────────────────


async def _run(event_type: str, raw_input: str) -> None:
    """Main async entry point with graceful degradation."""
    # Level 4: outermost try — never crash
    try:
        # Level 3: parse JSON input
        try:
            payload = json.loads(raw_input) if raw_input.strip() else {}
        except (json.JSONDecodeError, ValueError):
            payload = {}

        # Parse event and compute interest
        event = parse_event(event_type, payload)
        score = interest_score(event)

        # Skip low-interest events
        if score < 0.1:
            return

        # Load cortex state
        try:
            state = CortexState.load()
        except Exception:
            # Level 3 degradation: state load failure
            return

        # Check circuit breaker for this event type
        handler_name = event_type
        if state.is_disabled(handler_name):
            return

        # Level 1: full processing with JMEM
        try:
            sys.path.insert(0, str(JMEM_PATH))
            from jmem.engine import JMemEngine

            engine = JMemEngine()
            await engine.start()
            try:
                decision = await _handle_event(engine, event, state, score)
                state.record_success(handler_name)
            finally:
                await engine.shutdown()

        except Exception:
            # Level 2 degradation: JMEM failure
            state.record_error(handler_name)
            decision = Decision()

        # Save state and output
        try:
            state.save()
        except Exception:
            pass

        output = decision.to_json()
        if output:
            print(output)

    except Exception:
        # Level 4 degradation: absolute fallback — never crash
        pass


def main() -> None:
    """CLI entry point — reads event type from argv[1], payload from stdin."""
    event_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    raw_input = sys.stdin.read() if not sys.stdin.isatty() else ""
    asyncio.run(_run(event_type, raw_input))


if __name__ == "__main__":
    main()
