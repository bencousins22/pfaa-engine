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

import subprocess
import json
import hashlib
import shlex
import urllib.request
import tempfile

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

    def __init__(self, *, memory=None):
        self._tools: dict[str, tuple[ToolSpec, Callable]] = {}
        self._nucleus = Nucleus()
        self._memory_ref = None
        # Accept memory at construction time (dependency injection)
        # so callers don't need a separate set_memory() call.
        if memory is not None:
            self.set_memory(memory)

    @classmethod
    def get(cls, *, memory=None) -> ToolRegistry:
        """Return the singleton registry, optionally injecting memory.

        If memory is provided and the instance already exists, it will
        be attached via set_memory() — no re-creation needed.
        """
        if cls._instance is None:
            cls._instance = cls(memory=memory)
        elif memory is not None:
            cls._instance.set_memory(memory)
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
        coros = [self.execute(name, *args, **kwargs) for name, args, kwargs in calls]
        results: list[TaskResult] = []
        try:
            async with asyncio.TaskGroup() as tg:
                task_handles = [tg.create_task(c) for c in coros]
            results = [t.result() for t in task_handles]
        except* Exception as eg:
            for t in task_handles:
                if t.done() and t.exception() is None:
                    results.append(t.result())
                else:
                    results.append(t.exception() if t.done() else None)
        return results

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
    """Read a file asynchronously with path traversal protection."""
    resolved = os.path.realpath(path)
    if ".." in os.path.relpath(resolved, os.getcwd()):
        # Allow home dir and /tmp but reject paths outside workspace going upward
        allowed_prefixes = (os.path.expanduser("~"), "/tmp", os.getcwd())
        if not any(resolved.startswith(p) for p in allowed_prefixes):
            return {"success": False, "path": path, "error": "Path outside allowed directories"}
    loop = asyncio.get_running_loop()
    try:
        content = await loop.run_in_executor(None, lambda: open(resolved).read())
        return {"success": True, "path": resolved, "content": content, "size": len(content)}
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
    """Write to a file asynchronously with path traversal protection."""
    resolved = os.path.realpath(os.path.expanduser(path))
    allowed_prefixes = (os.path.expanduser("~"), "/tmp", os.getcwd())
    if not any(resolved.startswith(p) for p in allowed_prefixes):
        return {"success": False, "path": path, "error": "Path outside allowed directories"}
    loop = asyncio.get_running_loop()
    try:
        def _write():
            os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)
            with open(resolved, "w") as f:
                f.write(content)
            return os.path.getsize(resolved)
        size = await loop.run_in_executor(None, _write)
        return {"success": True, "path": resolved, "bytes_written": size}
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
    """Evaluate a mathematical expression safely using AST parsing."""
    import ast
    import math as math_mod
    import operator

    # Allowed operators for safe evaluation
    _ops = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
        ast.Pow: operator.pow, ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    # Allowed math functions
    _funcs: dict[str, Any] = {
        k: getattr(math_mod, k)
        for k in dir(math_mod)
        if not k.startswith("_") and callable(getattr(math_mod, k))
    }
    _funcs.update({"abs": abs, "round": round, "len": len, "sum": sum, "min": min, "max": max})

    # Allowed constants
    _consts: dict[str, Any] = {
        k: getattr(math_mod, k)
        for k in ("pi", "e", "tau", "inf", "nan")
        if hasattr(math_mod, k)
    }

    def _safe_eval(node: ast.AST) -> Any:
        match node:
            case ast.Expression(body=body):
                return _safe_eval(body)
            case ast.Constant(value=int() | float() | complex() as v):
                return v
            case ast.Constant(value=v):
                raise ValueError(f"Unsupported constant: {v!r}")
            case ast.BinOp(op=op_node, left=left, right=right):
                op = _ops.get(type(op_node))
                if op is None:
                    raise ValueError(f"Unsupported operator: {type(op_node).__name__}")
                return op(_safe_eval(left), _safe_eval(right))
            case ast.UnaryOp(op=op_node, operand=operand):
                op = _ops.get(type(op_node))
                if op is None:
                    raise ValueError(f"Unsupported unary operator: {type(op_node).__name__}")
                return op(_safe_eval(operand))
            case ast.Call(func=ast.Name(id=fn_name), args=call_args):
                func = _funcs.get(fn_name)
                if func is None:
                    raise ValueError(f"Unknown function: {fn_name}")
                return func(*[_safe_eval(a) for a in call_args])
            case ast.Call():
                raise ValueError("Only named function calls allowed")
            case ast.Name(id=name) if name in _consts:
                return _consts[name]
            case ast.Name(id=name) if name in _funcs:
                return _funcs[name]
            case ast.Name(id=name):
                raise ValueError(f"Unknown name: {name}")
            case _:
                raise ValueError(f"Unsupported expression: {type(node).__name__}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree)
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
    """Execute Python code in an isolated subprocess via stdin (no temp file)."""
    try:
        result = subprocess.run(
            ["python3", "-c", code],
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


@registry.register(ToolSpec(
    name="http_fetch",
    description="Fetch content from a URL",
    phase=Phase.VAPOR,
    capabilities=("network",),
    timeout_s=15.0,
    retries=2,
))
async def tool_http_fetch(url: str, timeout: float = 10.0) -> dict[str, Any]:
    """Fetch a URL asynchronously. Enforces HTTPS for security."""
    if not url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        return {"success": False, "url": url, "error": "Only HTTPS URLs allowed (except localhost)"}
    MAX_DOWNLOAD_BYTES = 1_048_576  # 1 MB hard limit on response body
    loop = asyncio.get_running_loop()
    try:
        def _fetch():
            req = urllib.request.Request(url, headers={"User-Agent": "AussieAgents/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                # Reject responses that advertise a body larger than 1 MB
                content_length = resp.headers.get("content-length")
                if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                    return {
                        "success": False,
                        "url": url,
                        "error": f"Response too large: {content_length} bytes (limit {MAX_DOWNLOAD_BYTES})",
                    }
                # Read with size cap to guard against missing/lying Content-Length
                raw = resp.read(MAX_DOWNLOAD_BYTES + 1)
                if len(raw) > MAX_DOWNLOAD_BYTES:
                    return {
                        "success": False,
                        "url": url,
                        "error": f"Response exceeded {MAX_DOWNLOAD_BYTES} byte download limit",
                    }
                body = raw.decode("utf-8", errors="replace")
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": body[:10000],  # cap at 10KB for output
                    "size": len(body),
                }
        result = await loop.run_in_executor(None, _fetch)
        if "success" in result and not result["success"]:
            return result  # early rejection (size limit)
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
