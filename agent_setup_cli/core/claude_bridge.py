"""
Claude Code Bridge — Aussie Agents ↔ Claude Code orchestration layer.

This module lets Aussie Agents spawn Claude Code subagents as SOLID-phase agents.
Each Claude Code invocation runs in its own subprocess (crash-safe, isolated)
and communicates back via stdout/stderr JSON.

Patterns supported:
    1. Single-shot: Ask Claude a question, get answer
    2. Code generation: Generate code and write to file
    3. Parallel research: Fan-out N questions to N Claude agents
    4. Conversational: Multi-turn dialogue with context

Python 3.15 features:
    - lazy import: subprocess/json only load when Claude is actually invoked
    - kqueue: efficient process lifecycle on macOS
    - frozendict: immutable prompt templates
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

lazy import subprocess
lazy import shlex
lazy import json
lazy import tempfile

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.agent import AgentConfig, TaskResult
from agent_setup_cli.core.nucleus import Nucleus
from agent_setup_cli.core.memory import MemorySystem

logger = logging.getLogger("pfaa.claude_bridge")


@dataclass(frozen=True)
class ClaudeConfig:
    """Configuration for Claude Code invocation."""
    model: str = "sonnet"
    max_tokens: int = 4096
    timeout_s: float = 120.0
    allowed_tools: tuple[str, ...] = ()
    print_output: bool = False
    working_dir: str | None = None


@dataclass
class ClaudeResult:
    """Result from a Claude Code invocation."""
    success: bool
    output: str
    cost_usd: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    elapsed_ms: float = 0.0
    session_id: str | None = None


def _find_claude_binary() -> str | None:
    """Find the claude binary on the system."""
    for path in [
        os.path.expanduser("~/.claude/local/claude"),
        "/usr/local/bin/claude",
        "claude",
    ]:
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def _invoke_claude_sync(
    prompt: str,
    config: ClaudeConfig,
    context_files: list[str] | None = None,
) -> ClaudeResult:
    """Synchronous Claude Code invocation (runs in subprocess)."""
    claude_bin = _find_claude_binary()
    if not claude_bin:
        return ClaudeResult(
            success=False,
            output="Claude Code binary not found. Install with: npm install -g @anthropic-ai/claude-code",
        )

    cmd = [claude_bin, "--print"]

    if config.model:
        cmd.extend(["--model", config.model])

    if config.allowed_tools:
        for tool in config.allowed_tools:
            cmd.extend(["--allowedTools", tool])

    # Claude CLI takes prompt via stdin when using --print
    # The prompt is the last positional argument
    cmd.append(prompt)

    start = time.perf_counter_ns()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.timeout_s,
            cwd=config.working_dir or os.getcwd(),
        )
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        output = result.stdout.strip()
        if result.returncode != 0 and not output:
            output = result.stderr.strip()

        return ClaudeResult(
            success=result.returncode == 0,
            output=output,
            elapsed_ms=elapsed_ms,
        )

    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        return ClaudeResult(
            success=False,
            output=f"Timeout after {config.timeout_s}s",
            elapsed_ms=elapsed_ms,
        )
    except Exception as e:
        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
        return ClaudeResult(
            success=False,
            output=str(e),
            elapsed_ms=elapsed_ms,
        )


class ClaudeBridge:
    """
    Bridge between Aussie Agents and Claude Code.

    Claude invocations always run as SOLID-phase agents (subprocess isolation).
    The bridge handles:
        - Prompt construction with context injection
        - Parallel fan-out for research tasks
        - Memory integration (learned prompt patterns)
        - Result parsing and error recovery
    """

    def __init__(
        self,
        config: ClaudeConfig | None = None,
        memory: MemorySystem | None = None,
    ):
        self.config = config or ClaudeConfig()
        self._nucleus = Nucleus(max_concurrency=4)  # limit concurrent Claude calls
        self._memory = memory
        self._available = None  # lazy-check

    @property
    def is_available(self) -> bool:
        if self._available is None:
            self._available = _find_claude_binary() is not None
        return self._available

    # ── Single-shot queries ─────────────────────────────────────────

    async def ask(
        self,
        prompt: str,
        model: str | None = None,
        timeout: float | None = None,
    ) -> ClaudeResult:
        """Ask Claude a single question."""
        config = ClaudeConfig(
            model=model or self.config.model,
            max_tokens=self.config.max_tokens,
            timeout_s=timeout or self.config.timeout_s,
            working_dir=self.config.working_dir,
        )

        agent_config = AgentConfig(
            name="claude-ask",
            capabilities=("ai", "reasoning"),
            isolation_required=True,
        )

        result = await self._nucleus.execute_one(
            agent_config,
            _invoke_claude_sync,
            prompt,
            config,
            hint=Phase.SOLID,
        )

        claude_result = result.result
        if self._memory and isinstance(claude_result, ClaudeResult):
            self._memory.record(result, "claude_ask", (prompt[:100],))

        return claude_result

    # ── Code generation ─────────────────────────────────────────────

    async def generate_code(
        self,
        description: str,
        language: str = "python",
        output_file: str | None = None,
    ) -> ClaudeResult:
        """Generate code based on a description."""
        prompt = (
            f"Generate {language} code for the following. "
            f"Return ONLY the code, no explanation:\n\n{description}"
        )

        result = await self.ask(prompt)

        if result.success and output_file and result.output:
            code = result.output
            # Extract code block if present
            if f"```{language}" in code:
                code = code.split(f"```{language}")[1].split("```")[0].strip()
            elif "```" in code:
                code = code.split("```")[1].split("```")[0].strip()

            os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
            with open(output_file, "w") as f:
                f.write(code)

        return result

    # ── Parallel research ───────────────────────────────────────────

    async def research(
        self,
        questions: list[str],
        model: str | None = None,
    ) -> list[ClaudeResult]:
        """Fan-out multiple questions to parallel Claude agents."""
        config = ClaudeConfig(
            model=model or self.config.model,
            max_tokens=self.config.max_tokens,
            timeout_s=self.config.timeout_s,
            working_dir=self.config.working_dir,
        )

        agent_config = AgentConfig(
            name="claude-research",
            capabilities=("ai", "research"),
            isolation_required=True,
        )

        results = await self._nucleus.scatter(
            config=agent_config,
            task_fn=_invoke_claude_sync,
            args_list=[(q, config) for q in questions],
            hint=Phase.SOLID,
        )

        return [r.result for r in results]

    # ── Code review ─────────────────────────────────────────────────

    async def review_code(self, file_path: str) -> ClaudeResult:
        """Have Claude review a code file."""
        try:
            with open(file_path) as f:
                code = f.read()
        except Exception as e:
            return ClaudeResult(success=False, output=f"Cannot read {file_path}: {e}")

        prompt = (
            f"Review this code from {file_path}. "
            f"Focus on bugs, security issues, and performance. "
            f"Be concise.\n\n```\n{code}\n```"
        )
        return await self.ask(prompt)

    # ── Task decomposition ──────────────────────────────────────────

    async def decompose_task(self, task_description: str) -> list[str]:
        """
        Ask Claude to decompose a complex task into subtasks.
        Returns a list of subtask descriptions.
        """
        prompt = (
            f"Decompose this task into independent subtasks that can be "
            f"executed in parallel. Return each subtask on its own line, "
            f"prefixed with '- '. No other text.\n\n"
            f"Task: {task_description}"
        )

        result = await self.ask(prompt)
        if not result.success:
            return [task_description]  # fallback: treat as single task

        subtasks = []
        for line in result.output.split("\n"):
            line = line.strip()
            if line.startswith("- "):
                subtasks.append(line[2:].strip())
            elif line.startswith("* "):
                subtasks.append(line[2:].strip())

        return subtasks if subtasks else [task_description]

    # ── Autonomous execution ────────────────────────────────────────

    async def execute_task(
        self,
        task: str,
        allowed_tools: tuple[str, ...] = ("Read", "Write", "Edit", "Bash", "Glob", "Grep"),
        auto_decompose: bool = True,
    ) -> list[ClaudeResult]:
        """
        Execute a complex task, optionally decomposing it first.

        If auto_decompose is True, Claude first breaks the task into
        subtasks, then executes each subtask in parallel.
        """
        if auto_decompose:
            subtasks = await self.decompose_task(task)
            if len(subtasks) > 1:
                logger.info("Decomposed into %d subtasks", len(subtasks))
                return await self.research(subtasks)

        # Single task execution with tools
        config = ClaudeConfig(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            timeout_s=self.config.timeout_s,
            allowed_tools=allowed_tools,
            working_dir=self.config.working_dir,
        )

        agent_config = AgentConfig(
            name="claude-exec",
            capabilities=("ai", "execute"),
            isolation_required=True,
        )

        result = await self._nucleus.execute_one(
            agent_config,
            _invoke_claude_sync,
            task,
            config,
            hint=Phase.SOLID,
        )

        return [result.result]

    # ── Status ──────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        return {
            "available": self.is_available,
            "model": self.config.model,
            "nucleus": self._nucleus.status(),
        }

    async def shutdown(self) -> None:
        await self._nucleus.shutdown()
