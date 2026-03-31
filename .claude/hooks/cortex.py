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
    project_profile: dict = field(default_factory=dict)
    event_timings: dict[str, list[float]] = field(default_factory=dict)  # event_type -> last 10 latencies
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
        case "SubagentStart":
            return AgentStartEvent(
                type=event_type,
                timestamp=ts,
                agent=payload.get("agent_type", payload.get("agent_name", payload.get("agent", "unknown"))),
                task=payload.get("task", payload.get("prompt", "")),
            )
        case "SubagentStop":
            # CC sends: agent_type, agent_id, last_assistant_message, stop_hook_active
            last_msg = payload.get("last_assistant_message", "")
            success = "error" not in last_msg.lower() if last_msg else True
            return AgentStopEvent(
                type=event_type,
                timestamp=ts,
                agent=payload.get("agent_type", payload.get("agent_name", payload.get("agent", "unknown"))),
                success=payload.get("success", success),
                error=payload.get("error", None),
            )
        case "PostToolUseFailure":
            # CC sends: tool_name, tool_input, tool_use_id, error
            error_msg = str(payload.get("error", ""))
            return ToolFailureEvent(
                type=event_type,
                timestamp=ts,
                tool=payload.get("tool_name", payload.get("tool", "unknown")),
                error=error_msg[:500],
                error_class=classify_error(error_msg),
            )
        case "FileChanged":
            # CC sends: file_path, event (change|add|unlink)
            file_path = payload.get("file_path", payload.get("path", ""))
            ext = Path(file_path).suffix if file_path else ""
            return FileChangedEvent(
                type=event_type,
                timestamp=ts,
                path=file_path,
                ext=ext,
            )
        case "TaskCompleted":
            # CC sends: task_id, task_subject, task_description, teammate_name
            return TaskCompletedEvent(
                type=event_type,
                timestamp=ts,
                subject=payload.get("task_subject", payload.get("subject", "")),
                description=payload.get("task_description", payload.get("description", "")),
            )
        case "UserPromptSubmit":
            # CC sends: prompt
            return PromptSubmitEvent(
                type=event_type,
                timestamp=ts,
                prompt=payload.get("prompt", payload.get("content", "")),
            )
        case "Stop":
            # CC sends: stop_hook_active, last_assistant_message
            return HookEvent(type=event_type, timestamp=ts)
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


# Events that never need full S1 analysis — safe-list bypass (like CC's SAFE_YOLO_ALLOWLISTED_TOOLS)
SAFE_EVENTS = frozenset({"TaskCompleted", "Stop"})


# ── S1 Fast Path: Dynamic L4 Rules ──────────────────────────────


class DynamicRules:
    """S1 Fast Path: JMEM L4 skills loaded as frozen decision tables."""

    def __init__(self):
        self._rules: dict[tuple[str, str], dict] = {}  # (agent, domain) -> rule
        self._loaded_at: float = 0.0

    async def load(self, engine) -> None:
        """Reload L4 skills as decision rules. Cache for 60s."""
        if time() - self._loaded_at < 60:
            return
        try:
            from jmem.engine import MemoryLevel
            skills = await engine.recall(
                "blocking rules routing rules enforcement",
                limit=20, level=MemoryLevel.SKILL, min_q=0.85,
            )
            rules = {}
            for skill in skills:
                try:
                    parsed = json.loads(skill.content)
                    key = (parsed.get("agent", "*"), parsed.get("domain", "*"))
                    rules[key] = {
                        "action": parsed["action"],
                        "reason": parsed.get("reason", "JMEM L4 rule"),
                        "q": skill.q_value,
                        "source_id": skill.id,
                    }
                except (json.JSONDecodeError, KeyError):
                    continue
            self._rules = rules
            self._loaded_at = time()
        except Exception:
            pass  # Keep existing rules on failure

    def check(self, agent: str, domain: str) -> Decision | None:
        """Check for a matching L4 rule. Returns Decision or None."""
        # Try exact match first, then wildcard
        for key in [(agent, domain), (agent, "*"), ("*", domain)]:
            if key in self._rules:
                rule = self._rules[key]
                match rule["action"]:
                    case "block":
                        return Decision(
                            action="block",
                            block_reason=f"JMEM L4 (Q={rule['q']:.2f}): {rule['reason']}",
                            confidence=rule["q"],
                        )
                    case "advise":
                        return Decision(
                            action="advise",
                            system_message=f"JMEM L4: {rule['reason']}",
                            confidence=rule["q"],
                        )
        return None


# Module-level singleton
_dynamic_rules = DynamicRules()


# ── JMEM Feature Gates ─────────────────────────────────────────


async def is_feature_enabled(engine, feature_name: str) -> bool:
    """Check JMEM L4 skills for feature gate status. Default: enabled."""
    try:
        results = await engine.recall(
            f"feature gate {feature_name}",
            limit=1, level=4, min_q=0.5,  # L4 SKILL level
        )
        if results:
            content = results[0].content.lower()
            if "disabled" in content or "off" in content:
                return False
    except Exception:
        pass
    return True  # Safe default: enabled


# ── Context-Sensitive Project Personality ────────────────────────


def detect_project_profile() -> dict[str, str | bool | float]:
    """Scan project characteristics to adapt cortex behavior."""
    try:
        root = PROJECT_ROOT
        # Bounded scan — exclude heavy directories
        EXCLUDE = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}
        py_count = 0
        ts_count = 0
        test_count = 0

        def _count(path, depth=0):
            nonlocal py_count, ts_count, test_count
            if depth > 4 or py_count + ts_count > 5000:  # Bail on huge trees
                return
            try:
                for entry in path.iterdir():
                    if entry.name in EXCLUDE or entry.name.startswith('.'):
                        continue
                    if entry.is_dir():
                        _count(entry, depth + 1)
                    elif entry.suffix == '.py':
                        py_count += 1
                        if 'test' in entry.name.lower():
                            test_count += 1
                    elif entry.suffix == '.ts':
                        ts_count += 1
                        if 'test' in entry.name.lower():
                            test_count += 1
            except PermissionError:
                pass

        _count(root)
        has_security = (root / ".claude" / "agents" / "aussie-security.md").exists()
        has_freqtrade = (root / "freqtrade_strategy").exists()

        return {
            "py315_enforcement": "aggressive" if py_count > 20 else "moderate",
            "blocking_confidence": 0.75 if test_count > 10 else 0.90,
            "security_emphasis": "high" if has_security else "normal",
            "overfitting_checks": has_freqtrade,
            "primary_language": "python" if py_count > ts_count else "typescript",
            "py_count": py_count,
            "ts_count": ts_count,
            "test_count": test_count,
        }
    except Exception:
        return {
            "py315_enforcement": "moderate",
            "blocking_confidence": 0.90,
            "security_emphasis": "normal",
            "overfitting_checks": False,
            "primary_language": "python",
        }


# ── Pre-computed agent context (saves agent turns) ──────────────

AGENT_FILE_HINTS = {
    "aussie-security": "Key security files: .claude/hooks/cortex.py, .claude/settings.json",
    "aussie-tdd": "Test files: tests/test_cortex.py, tests/test_jmem_engine.py",
    "pfaa-rewriter": "Python files needing Py3.15: .claude/hooks/cortex.py, agent_setup_cli/core/",
    "pfaa-validator": "Validation targets: .claude/hooks/cortex.py, .claude/hooks/analyzers/py315_ast.py",
    "aussie-docs": "Doc files: CLAUDE.md, README.md, ARCHITECTURE.md, docs/superpowers/specs/",
}


def _build_agent_context(agent: str, task: str, state: CortexState) -> list[str]:
    """Pre-compute context for agent injection -- saves agent turns."""
    context: list[str] = []

    # Project profile summary
    profile = state.project_profile
    if profile:
        context.append(
            f"Project: {profile.get('py_count', 0)} Python files, "
            f"{profile.get('ts_count', 0)} TypeScript files, "
            f"{profile.get('test_count', 0)} test files. "
            f"Primary language: {profile.get('primary_language', 'unknown')}. "
            f"Py3.15 enforcement: {profile.get('py315_enforcement', 'moderate')}."
        )

    # Recent cortex decisions (what the system has been doing)
    if state.total_decisions > 0:
        context.append(
            f"Cortex stats: {state.total_decisions} decisions, "
            f"{state.correct_blocks} correct blocks, "
            f"pressure={state.pressure:.1f}, phase={state.phase}."
        )

    # Agent-specific file hints
    hint = AGENT_FILE_HINTS.get(agent)
    if hint:
        context.append(hint)

    return context


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

    # Pre-computed project context (saves agent turns)
    pre_context = _build_agent_context(event.agent, event.task, state)
    parts.extend(pre_context)

    # Block if 3+ failures AND avg Q < 0.4
    # Adjust blocking confidence from project profile
    blocking_threshold = state.project_profile.get("blocking_confidence", 0.90) if state.project_profile else 0.90
    failure_notes = [n for n in history if "error" in n.tags]
    if len(failure_notes) >= 3:
        avg_q = sum(n.q_value for n in failure_notes) / len(failure_notes)
        if avg_q < 0.4:
            return Decision(
                action="block",
                block_reason=f"Agent {event.agent} has {len(failure_notes)} recent failures with avg Q={avg_q:.2f}. Investigate before retrying.",
                confidence=blocking_threshold,
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


async def handle_tool_failure(engine, event: ToolFailureEvent, state: CortexState) -> Decision:
    """PostToolUseFailure: classify, store, escalate on repeated failures."""
    from jmem.engine import MemoryLevel

    await engine.remember(
        content=event.to_episode(),
        level=MemoryLevel.EPISODE,
        tags=event.tags(),
    )

    try:
        await engine.reward_recalled(reward_signal=-0.3)
    except Exception:
        pass

    prior = await engine.recall(
        f"{event.tool} failed {event.error_class}", limit=10, min_q=0.0,
    )
    same_class = [m for m in prior if event.error_class in m.tags]

    if len(same_class) >= 5:
        return Decision(
            action="block",
            block_reason=f"Repeated {event.error_class} failures for {event.tool} ({len(same_class)}x)",
            confidence=0.85,
        )
    elif len(same_class) >= 3:
        return Decision(
            action="advise",
            system_message=f"{event.tool} has failed {len(same_class)}x ({event.error_class}). Consider an alternative approach.",
            confidence=0.6,
        )

    return Decision(action="observe")


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


async def handle_file_changed(engine, event: FileChangedEvent, state: CortexState) -> Decision:
    """FileChanged: AST analysis for .py, config tracking for others."""
    from jmem.engine import MemoryLevel

    if event.ext in (".py", ".pyi") and event.path:
        _analyzers_path = str(PROJECT_ROOT / ".claude" / "hooks" / "analyzers")
        if _analyzers_path not in sys.path:
            sys.path.append(_analyzers_path)
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
                tags=["file-changed", "py315-scan"],
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


# ── Keyword extraction ──────────────────────────────────────────


def _extract_keywords(text: str) -> list[str]:
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                  "being", "have", "has", "had", "do", "does", "did", "will",
                  "would", "could", "should", "may", "might", "can", "to", "of",
                  "in", "for", "on", "with", "at", "by", "from", "it", "this",
                  "that", "and", "or", "but", "not", "no", "so", "if", "then",
                  "than", "too", "very", "just", "i", "me", "my", "we", "you"}
    words = text.lower().split()
    return [w for w in words if w not in stop_words and len(w) > 2][:10]


# ── Prompt submit handler ──────────────────────────────────────────


async def handle_prompt_submit(engine, event: PromptSubmitEvent, state: CortexState) -> Decision:
    """UserPromptSubmit: inject relevant JMEM context before Claude processes."""
    if len(event.prompt.split()) <= 3:
        return Decision(action="observe")

    if engine is None:
        return Decision(action="observe")

    keywords = _extract_keywords(event.prompt)

    # Cache check (30s window, 50% keyword overlap)
    if (time() - state.last_prompt_at < 30 and state.last_prompt_keywords):
        overlap = len(set(keywords) & set(state.last_prompt_keywords)) / max(len(keywords), 1)
        if overlap > 0.5 and state.last_prompt_recall:
            lines = [f"[{m['level']} Q={m['q']:.1f}] {m['content'][:120]}" for m in state.last_prompt_recall]
            return Decision(action="observe", additional_context="JMEM auto-recall:\n" + "\n".join(lines))

    # Full JMEM recall with latency gate
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

    recall_data = [{"content": m.content[:120], "level": m.level.name, "q": m.q_value} for m in memories]
    state.last_prompt_keywords = keywords
    state.last_prompt_recall = recall_data
    state.last_prompt_at = time()

    lines = [f"[{m['level'][:4]} Q={m['q']:.1f}] {m['content']}" for m in recall_data]
    return Decision(action="observe", additional_context="JMEM auto-recall:\n" + "\n".join(lines))


# ── Stop + Dream Phase A ──────────────────────────────────────────

PRESSURE_THRESHOLD_DEFAULT = 10.0
DREAM_MIN_HOURS = 1.0


async def handle_stop(engine, event: HookEvent, state: CortexState) -> Decision:
    """Stop: store episode, run dream Phase A if conditions met."""
    from jmem.engine import MemoryLevel

    await engine.remember(
        content=f"Session stop — {state.total_decisions} decisions, pressure={state.pressure:.1f}",
        level=MemoryLevel.EPISODE,
        tags=["session-stop", "auto-episode"],
    )

    # Performance telemetry
    perf_msg = None
    if state.event_timings:
        perf_parts = []
        for evt, times in sorted(state.event_timings.items()):
            if times:
                avg = sum(times) / len(times)
                perf_parts.append(f"{evt}:{avg:.0f}ms")
        if perf_parts:
            perf_msg = " | ".join(perf_parts)

    hours_since_dream = (time() - state.last_dream_at) / 3600
    if state.pressure >= PRESSURE_THRESHOLD_DEFAULT and hours_since_dream >= DREAM_MIN_HOURS:
        try:
            await engine.consolidate()
            await engine.decay_idle(hours_threshold=24.0)
        except Exception:
            pass

        state.pressure = 0.0
        state.last_dream_at = time()
        state.dream_pending = True

        dream_msg = "Cortex dream (Phase A): consolidated + decayed"
        if perf_msg:
            dream_msg += f"\nPerf: {perf_msg}"
        return Decision(action="observe", system_message=dream_msg)

    stop_msg = None
    if perf_msg:
        stop_msg = f"Cortex perf: {perf_msg}"
    return Decision(action="observe", system_message=stop_msg)


# ── Self-assessment ───────────────────────────────────────────────


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


# ── Dream Phase B ────────────────────────────────────────────────


async def suggest_self_improvements(engine) -> list[str]:
    """Check JMEM for CC patterns not yet applied to cortex."""
    suggestions = []
    try:
        patterns = await engine.recall("claude-code-pattern apply cortex", limit=5, min_q=0.5)
        for p in patterns:
            if "apply to cortex" in p.content.lower() or "apply to pfaa" in p.content.lower():
                suggestions.append(f"Unapplied CC pattern (Q={p.q_value:.2f}): {p.content[:100]}")
    except Exception:
        pass
    return suggestions


async def run_dream_phase_b(engine, state: CortexState) -> list[str]:
    """Dream Phase B: heavy cognitive cycle — extract, meta-learn, emerge, assess.

    Returns list of self-improvement suggestions (may be empty).
    """
    try:
        await engine.extract_skills()
    except Exception:
        pass
    try:
        await engine.meta_learn()
    except Exception:
        pass
    try:
        await engine.emergent_synthesis()
    except Exception:
        pass

    self_assess(state)
    state.dream_pending = False

    # Check for unapplied CC patterns
    return await suggest_self_improvements(engine)


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

    # S1 Fast Path: check dynamic L4 rules for agent events (skip safe events)
    if isinstance(event, (AgentStartEvent, AgentStopEvent)) and event.type not in SAFE_EVENTS:
        await _dynamic_rules.load(engine)
        s1_result = _dynamic_rules.check(
            event.agent,
            event.task if isinstance(event, AgentStartEvent) else ""
        )
        # CC permission precedence: DENY > ASK > ALLOW
        # If S1 says block, never override with S2 allow
        if s1_result and s1_result.action == "block":
            return s1_result  # Deny always wins regardless of confidence
        if s1_result and s1_result.confidence > 0.9:
            return s1_result  # High confidence L4 rule, skip S2

    # S2 Full Path: per-handler logic
    match event:
        case AgentStartEvent():
            return await handle_agent_start(engine, event, state)
        case AgentStopEvent():
            return await handle_agent_stop(engine, event, state)
        case ToolFailureEvent():
            return await handle_tool_failure(engine, event, state)
        case TaskCompletedEvent():
            return await handle_task_completed(engine, event, state)
        case FileChangedEvent():
            return await handle_file_changed(engine, event, state)
        case PromptSubmitEvent():
            return await handle_prompt_submit(engine, event, state)
        case HookEvent(type="Stop"):
            return await handle_stop(engine, event, state)
        case _:
            return Decision()


# ── Entry point with 4-level degradation ─────────────────────────


async def _run(event_type: str, raw_input: str) -> Decision | None:
    """Main async entry point with graceful degradation. Returns Decision for exit code handling."""
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
            return None

        # Load cortex state
        try:
            state = CortexState.load()
        except Exception:
            # Level 3 degradation: state load failure
            return None

        # Detect project profile on first run
        if not state.project_profile:
            state.project_profile = detect_project_profile()

        # Dream Phase B: deferred from prior Stop
        if state.dream_pending:
            try:
                if str(JMEM_PATH) not in sys.path:
                    sys.path.append(str(JMEM_PATH))
                from jmem.engine import JMemEngine
                engine = JMemEngine(db_path=os.path.expanduser("~/.jmem/claude-code/memory.db"))
                await run_dream_phase_b(engine, state)
            except Exception:
                state.dream_pending = False

        # Check circuit breaker for this event type
        handler_name = event_type
        if state.is_disabled(handler_name):
            return None

        # Level 1: full processing with JMEM
        import time as _time
        handler_start = _time.monotonic()

        try:
            if str(JMEM_PATH) not in sys.path:
                sys.path.append(str(JMEM_PATH))
            from jmem.engine import JMemEngine

            engine = JMemEngine(db_path=os.path.expanduser("~/.jmem/claude-code/memory.db"))
            await engine.start()
            try:
                decision = await _handle_event(engine, event, state, score)
                state.record_success(handler_name)
            finally:
                await engine.shutdown()

        except Exception as exc:
            # Level 2: JMEM unavailable — state-only decisions
            try:
                state.record_error(handler_name)
                # Fail-safe: advise on security-sensitive events when processing fails
                if event_type in ("SubagentStart", "PostToolUseFailure"):
                    decision = Decision(
                        action="advise",
                        system_message=f"Cortex processing error for {event_type} — proceeding with caution",
                    )
                else:
                    decision = Decision()
            except Exception:
                decision = Decision()

        # Track timing (keep last 10 per event type)
        handler_elapsed = _time.monotonic() - handler_start
        timings = state.event_timings.get(event_type, [])
        timings.append(round(handler_elapsed * 1000, 1))  # ms
        state.event_timings[event_type] = timings[-10:]  # Keep last 10

        # Save state and output
        try:
            state.save()
        except Exception:
            pass

        output = decision.to_json()
        if output:
            print(output)

        return decision

    except Exception:
        # Level 4 degradation: absolute fallback — never crash
        return None


def main() -> None:
    """CLI entry point — reads event type from argv[1], payload from stdin."""
    event_type = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    raw_input = sys.stdin.read(1_000_000) if not sys.stdin.isatty() else ""  # 1MB max
    decision = asyncio.run(_run(event_type, raw_input))

    # CC hook protocol: exit code 2 = blocking signal
    if decision and decision.action == "block":
        sys.exit(2)


if __name__ == "__main__":
    main()
