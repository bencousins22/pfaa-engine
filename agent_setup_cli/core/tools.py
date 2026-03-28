"""
Aussie Agents Tool System — Self-registering, phase-aware tools.

Tools are the building blocks that agents use to interact with the world.
Each tool declares its optimal phase, and the Nucleus automatically
spawns agents in the right execution mode.

Python 3.15 features:
    - lazy import: tool dependencies load only when the tool is first used
    - frozendict: tool metadata is immutable and hashable
    - t-strings (3.14+): safe command construction for shell tools
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

lazy import subprocess
lazy import json
lazy import hashlib
lazy import shlex
lazy import urllib.request
lazy import tempfile

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.agent import AgentConfig, FluidAgent, TaskResult
from agent_setup_cli.core.nucleus import Nucleus

logger = logging.getLogger("pfaa.tools")


# ── Tool Definition ─────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolSpec:
    """Immutable tool specification — the blueprint for a tool."""
    name: str
    description: str
    phase: Phase
    capabilities: tuple[str, ...] = ()
    timeout_s: float = 30.0
    retries: int = 0
    isolated: bool = False

    def to_agent_config(self) -> AgentConfig:
        return AgentConfig(
            name=f"tool-{self.name}",
            capabilities=self.capabilities,
            max_phase=Phase.SOLID if self.isolated else self.phase,
            isolation_required=self.isolated,
        )


class ToolRegistry:
    """
    Central registry of all available tools.

    Tools register themselves with decorators. The registry provides
    discovery, execution, and parallel fan-out capabilities.
    """

    _instance: ToolRegistry | None = None

    def __init__(self):
        self._tools: dict[str, tuple[ToolSpec, Callable]] = {}
        self._nucleus = Nucleus()
        self._memory_ref = None  # set via set_memory() for exploration

    @classmethod
    def get(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, spec: ToolSpec) -> Callable:
        """Decorator to register a function as a tool."""
        def decorator(fn: Callable) -> Callable:
            self._tools[spec.name] = (spec, fn)
            logger.debug("Registered tool: %s (phase=%s)", spec.name, spec.phase.name)
            return fn
        return decorator

    def list_tools(self) -> list[ToolSpec]:
        return [spec for spec, _ in self._tools.values()]

    def get_tool(self, name: str) -> tuple[ToolSpec, Callable] | None:
        return self._tools.get(name)

    # Epsilon-greedy exploration: occasionally try a non-default phase
    # so L3 memory can compare performance across phases.
    EXPLORE_EPSILON: float = 0.15        # 15% exploration rate
    EXPLORE_CONFIDENCE_CAP: float = 0.5  # stop exploring once confident

    def _pick_phase(self, spec: ToolSpec) -> Phase:
        """Pick execution phase with epsilon-greedy exploration.

        Rules:
        - isolated tools always stay SOLID (safety constraint)
        - async tools skip VAPOR↔LIQUID exploration (both just await the
          coroutine — no real difference). They also can't go SOLID (can't
          pickle coroutines). So async tools are locked to their declared phase.
        - sync tools explore freely between VAPOR/LIQUID/SOLID. This is where
          real phase differences exist:
            VAPOR:  run_in_executor(None, fn) — shared default thread pool
            LIQUID: run_in_executor(dedicated_pool, fn) — own ThreadPoolExecutor
            SOLID:  ProcessPoolExecutor — full subprocess isolation
        - once confidence > 0.5, lock in the learned best phase
        """
        # Safety: isolated tools never explore
        if spec.isolated:
            return spec.phase

        # Async tools: VAPOR and LIQUID both just `await fn()`, so exploring
        # between them produces misleading data. SOLID is impossible (can't
        # pickle coroutines). Lock async tools to their declared phase.
        _, fn = self._tools[spec.name]
        if asyncio.iscoroutinefunction(fn):
            return spec.phase

        # Check if memory already has enough data for this tool
        if self._memory_ref:
            pattern = self._memory_ref.l2_semantic.get_pattern(spec.name)
            if pattern and pattern.confidence() >= self.EXPLORE_CONFIDENCE_CAP:
                # Confident — use the learned best phase, no exploration
                return pattern.best_phase

        # Epsilon-greedy: explore sync tools across all three phases
        if random.random() < self.EXPLORE_EPSILON:
            alternatives = [p for p in Phase if p != spec.phase]
            explored = random.choice(alternatives)
            logger.debug(
                "Exploring %s in %s (default: %s)",
                spec.name, explored.name, spec.phase.name,
            )
            return explored

        return spec.phase

    def set_memory(self, memory) -> None:
        """Attach a MemorySystem for exploration-guided phase selection.
        Also registers which tools are async so memory can prune stale strategies."""
        self._memory_ref = memory
        # Tell memory which tools are async (so it can prune bogus strategies)
        async_names = set()
        for name, (spec, fn) in self._tools.items():
            if asyncio.iscoroutinefunction(fn):
                async_names.add(name)
        if hasattr(memory, 'register_async_tools'):
            memory.register_async_tools(async_names)

    async def execute(
        self, name: str, *args: Any, **kwargs: Any
    ) -> TaskResult:
        """Execute a single tool by name, with epsilon-greedy phase exploration."""
        entry = self._tools.get(name)
        if entry is None:
            raise ValueError(f"Unknown tool: {name}")
        spec, fn = entry
        phase = self._pick_phase(spec)

        # Build agent config — if exploring a higher phase than default,
        # raise max_phase so the agent can transition there
        config = AgentConfig(
            name=f"tool-{spec.name}",
            capabilities=spec.capabilities,
            max_phase=max(phase, spec.phase, key=lambda p: p.value),
            isolation_required=spec.isolated,
        )

        for attempt in range(spec.retries + 1):
            try:
                result = await self._nucleus.execute_one(
                    config, fn, *args, hint=phase, **kwargs,
                )
                return result
            except Exception as e:
                if attempt == spec.retries:
                    raise
                logger.warning(
                    "Tool %s attempt %d failed: %s", name, attempt + 1, e
                )
                await asyncio.sleep(0.1 * (attempt + 1))
        raise RuntimeError("unreachable")

    async def execute_many(
        self,
        calls: list[tuple[str, tuple, dict]],
    ) -> list[TaskResult]:
        """Execute multiple tools in parallel (scatter pattern)."""
        tasks = []
        for name, args, kwargs in calls:
            tasks.append(self.execute(name, *args, **kwargs))
        return list(await asyncio.gather(*tasks, return_exceptions=True))

    async def pipeline(
        self,
        tool_chain: list[tuple[str, tuple]],
    ) -> list[TaskResult]:
        """Execute tools sequentially, feeding each result to the next."""
        entry = self._tools.get(tool_chain[0][0])
        if entry is None:
            raise ValueError(f"Unknown tool: {tool_chain[0][0]}")

        stages = []
        for name, extra_args in tool_chain:
            spec, fn = self._tools[name]
            stages.append((spec.phase, fn, extra_args))

        config = AgentConfig(
            name="pipeline",
            capabilities=("all",),
        )
        return await self._nucleus.pipeline(config, stages)

    def status(self) -> dict[str, Any]:
        return {
            "tools_registered": len(self._tools),
            "tool_names": list(self._tools.keys()),
            "nucleus": self._nucleus.status(),
        }

    async def shutdown(self) -> None:
        await self._nucleus.shutdown()


# ── Built-in Tools ──────────────────────────────────────────────────

registry = ToolRegistry.get()


@registry.register(ToolSpec(
    name="shell",
    description="Execute a shell command and return stdout/stderr",
    phase=Phase.SOLID,
    capabilities=("execute",),
    isolated=True,
    timeout_s=30.0,
    retries=0,
))
def tool_shell(command: str, timeout: float = 30.0) -> dict[str, Any]:
    """Execute a shell command in an isolated subprocess."""
    try:
        result = subprocess.run(
            shlex.split(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout", "timeout": timeout}
    except Exception as e:
        return {"success": False, "error": str(e)}


@registry.register(ToolSpec(
    name="read_file",
    description="Read a file and return its contents",
    phase=Phase.VAPOR,
    capabilities=("read",),
    timeout_s=5.0,
))
async def tool_read_file(path: str) -> dict[str, Any]:
    """Read a file asynchronously."""
    loop = asyncio.get_running_loop()
    try:
        content = await loop.run_in_executor(None, lambda: open(path).read())
        return {"success": True, "path": path, "content": content, "size": len(content)}
    except Exception as e:
        return {"success": False, "path": path, "error": str(e)}


@registry.register(ToolSpec(
    name="write_file",
    description="Write content to a file",
    phase=Phase.VAPOR,
    capabilities=("write",),
    timeout_s=5.0,
))
async def tool_write_file(path: str, content: str) -> dict[str, Any]:
    """Write to a file asynchronously."""
    loop = asyncio.get_running_loop()
    try:
        def _write():
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return os.path.getsize(path)
        size = await loop.run_in_executor(None, _write)
        return {"success": True, "path": path, "bytes_written": size}
    except Exception as e:
        return {"success": False, "path": path, "error": str(e)}


@registry.register(ToolSpec(
    name="glob_search",
    description="Find files matching a glob pattern",
    phase=Phase.VAPOR,
    capabilities=("search",),
    timeout_s=10.0,
))
async def tool_glob_search(pattern: str, root: str = ".") -> dict[str, Any]:
    """Search for files matching a pattern."""
    import glob as glob_mod
    loop = asyncio.get_running_loop()
    try:
        matches = await loop.run_in_executor(
            None, lambda: glob_mod.glob(pattern, root_dir=root, recursive=True)
        )
        return {"success": True, "pattern": pattern, "matches": matches, "count": len(matches)}
    except Exception as e:
        return {"success": False, "pattern": pattern, "error": str(e)}


@registry.register(ToolSpec(
    name="grep",
    description="Search file contents for a regex pattern",
    phase=Phase.LIQUID,
    capabilities=("search",),
    timeout_s=15.0,
))
def tool_grep(pattern: str, path: str = ".", file_glob: str = "*") -> dict[str, Any]:
    """Search file contents using grep (runs as thread for CPU parallelism)."""
    import re
    import glob as glob_mod
    compiled = re.compile(pattern)
    matches = []
    files_searched = 0

    for filepath in glob_mod.glob(
        os.path.join(path, "**", file_glob), recursive=True
    ):
        if not os.path.isfile(filepath):
            continue
        files_searched += 1
        try:
            with open(filepath) as f:
                for lineno, line in enumerate(f, 1):
                    if compiled.search(line):
                        matches.append({
                            "file": filepath,
                            "line": lineno,
                            "content": line.rstrip(),
                        })
        except (UnicodeDecodeError, PermissionError):
            continue

    return {
        "success": True,
        "pattern": pattern,
        "files_searched": files_searched,
        "matches": matches[:100],  # cap at 100
        "total_matches": len(matches),
    }


@registry.register(ToolSpec(
    name="compute",
    description="Execute a pure computation (CPU-bound)",
    phase=Phase.LIQUID,
    capabilities=("compute",),
    timeout_s=60.0,
))
def tool_compute(expression: str) -> dict[str, Any]:
    """Evaluate a mathematical expression in a thread."""
    import math as math_mod
    safe_builtins = {
        k: getattr(math_mod, k)
        for k in dir(math_mod)
        if not k.startswith("_")
    }
    safe_builtins.update({"abs": abs, "round": round, "len": len, "sum": sum, "min": min, "max": max})
    try:
        result = eval(expression, {"__builtins__": {}}, safe_builtins)
        return {"success": True, "expression": expression, "result": result}
    except Exception as e:
        return {"success": False, "expression": expression, "error": str(e)}


@registry.register(ToolSpec(
    name="sandbox_exec",
    description="Execute Python code in an isolated subprocess",
    phase=Phase.SOLID,
    capabilities=("execute",),
    isolated=True,
    timeout_s=30.0,
    retries=1,
))
def tool_sandbox_exec(code: str, timeout: float = 10.0) -> dict[str, Any]:
    """Execute arbitrary Python code in a sandboxed subprocess."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False
    ) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = subprocess.run(
            ["python3", temp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    finally:
        os.unlink(temp_path)


@registry.register(ToolSpec(
    name="http_fetch",
    description="Fetch content from a URL",
    phase=Phase.VAPOR,
    capabilities=("network",),
    timeout_s=15.0,
    retries=2,
))
async def tool_http_fetch(url: str, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch a URL asynchronously."""
    loop = asyncio.get_running_loop()
    try:
        def _fetch():
            req = urllib.request.Request(url, headers={"User-Agent": "AussieAgents/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": body[:10000],  # cap at 10KB
                    "size": len(body),
                }
        result = await loop.run_in_executor(None, _fetch)
        return {"success": True, "url": url, **result}
    except Exception as e:
        return {"success": False, "url": url, "error": str(e)}


@registry.register(ToolSpec(
    name="hash_data",
    description="Compute cryptographic hash of data",
    phase=Phase.LIQUID,
    capabilities=("compute",),
    timeout_s=5.0,
))
def tool_hash_data(
    data: str, algorithm: str = "sha256"
) -> dict[str, Any]:
    """Compute hash in a thread (CPU-bound for large inputs)."""
    try:
        h = hashlib.new(algorithm)
        h.update(data.encode("utf-8"))
        return {
            "success": True,
            "algorithm": algorithm,
            "digest": h.hexdigest(),
            "input_size": len(data),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@registry.register(ToolSpec(
    name="parallel_shell",
    description="Execute multiple shell commands in parallel",
    phase=Phase.SOLID,
    capabilities=("execute",),
    isolated=True,
    timeout_s=60.0,
))
def tool_parallel_shell(commands: list[str], timeout: float = 30.0) -> dict[str, Any]:
    """Run multiple shell commands in parallel subprocesses."""
    import concurrent.futures

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(commands)) as pool:
        futures = {}
        for cmd in commands:
            future = pool.submit(
                subprocess.run,
                shlex.split(cmd),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            futures[future] = cmd

        for future in concurrent.futures.as_completed(futures):
            cmd = futures[future]
            try:
                r = future.result()
                results.append({
                    "command": cmd,
                    "success": r.returncode == 0,
                    "stdout": r.stdout,
                    "stderr": r.stderr,
                })
            except Exception as e:
                results.append({"command": cmd, "success": False, "error": str(e)})

    return {
        "success": all(r["success"] for r in results),
        "results": results,
        "count": len(results),
    }
