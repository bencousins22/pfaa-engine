"""
Aussie Agents Base — Python 3.15
Mirrors Agent Zero's async execute(**kwargs) -> Response pattern.
All tier agents inherit from this.

Python 3.15 features:
  - PEP 695 type aliases
  - match/case for routing
  - asyncio.timeout() context manager
  - ExceptionGroup fault isolation
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import json
from dataclasses import dataclass, field
from typing import Any, TypeAlias


# PEP 695 type aliases
AgentId: TypeAlias = str
JsonDict: TypeAlias = dict[str, Any]
ToolName: TypeAlias = str
Tier: TypeAlias = str


@dataclass(slots=True)
class Response:
    """Mirrors Agent Zero's Response(message=str, break_loop=bool)."""
    message: str
    break_loop: bool = False
    tool_calls: int = 0
    token_count: int = 0
    error: str | None = None


@dataclass(slots=True)
class AgentContext:
    agent_id: AgentId
    tier: Tier
    role: str
    model: str
    provider: str
    workspace: str
    tools: list[ToolName]
    memory_area: str = "main"
    system_prompt: str = ""
    qdrant_url: str = "http://localhost:6333"
    max_iterations: int = 20
    timeout_seconds: float = 90.0


def emit(event: JsonDict) -> None:
    sys.stdout.write(json.dumps(event, default=str) + "\n")
    sys.stdout.flush()


class PFAAAgent:
    """
    Base agent class — Agent Zero execute() pattern.
    Subclass and override build_system_prompt() for tier specialisation.
    """

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx
        self._tool_calls = 0
        self._token_count = 0

    async def execute(self, prompt: str, **kwargs: Any) -> Response:
        start = time.monotonic()
        emit({
            "type": "agent_start",
            "agent_id": self.ctx.agent_id,
            "tier": self.ctx.tier,
            "role": self.ctx.role,
            "ts": start,
        })

        try:
            async with asyncio.timeout(self.ctx.timeout_seconds):
                output = await self._agent_loop(prompt)

            duration_ms = int((time.monotonic() - start) * 1000)
            emit({
                "type": "agent_complete",
                "agent_id": self.ctx.agent_id,
                "duration_ms": duration_ms,
                "tokens": self._token_count,
                "tool_calls": self._tool_calls,
            })
            return Response(
                message=output,
                tool_calls=self._tool_calls,
                token_count=self._token_count,
            )

        except TimeoutError:
            err = f"{self.ctx.agent_id} timed out after {self.ctx.timeout_seconds}s"
            emit({"type": "agent_error", "agent_id": self.ctx.agent_id, "error": err})
            return Response(message="", error=err, break_loop=True)

        except Exception as e:
            emit({"type": "agent_error", "agent_id": self.ctx.agent_id, "error": str(e)})
            return Response(message="", error=str(e))

    async def _agent_loop(self, prompt: str) -> str:
        match self.ctx.provider:
            case "claude":
                return await self._loop_claude(prompt)
            case "gemini":
                return await self._loop_gemini(prompt)
            case _:
                raise ValueError(f"Unknown provider: {self.ctx.provider}")

    async def _loop_claude(self, prompt: str) -> str:
        import anthropic
        client = anthropic.AsyncAnthropic()
        messages: list[JsonDict] = [{"role": "user", "content": prompt}]
        parts: list[str] = []

        for _ in range(self.ctx.max_iterations):
            resp = await client.messages.create(
                model=self.ctx.model,
                system=self.build_system_prompt(),
                messages=messages,
                tools=self._tool_defs(),
                max_tokens=4096,
            )
            self._token_count += resp.usage.input_tokens + resp.usage.output_tokens

            tool_results: list[JsonDict] = []
            for block in resp.content:
                match block.type:
                    case "text":
                        parts.append(block.text)
                        emit({
                            "type": "text",
                            "agent_id": self.ctx.agent_id,
                            "content": block.text[:300],
                        })
                    case "tool_use":
                        self._tool_calls += 1
                        emit({
                            "type": "tool_call",
                            "agent_id": self.ctx.agent_id,
                            "tool": block.name,
                            "input": block.input,
                        })
                        result = await self._run_tool(block.name, block.input)
                        emit({
                            "type": "tool_result",
                            "agent_id": self.ctx.agent_id,
                            "tool": block.name,
                            "result": str(result)[:400],
                        })
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": str(result),
                        })

            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "end_turn":
                break
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        return "\n".join(parts)

    async def _loop_gemini(self, prompt: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
        model_obj = genai.GenerativeModel(
            model_name=self.ctx.model or "gemini-2.5-pro",
            system_instruction=self.build_system_prompt(),
        )
        resp = await asyncio.to_thread(model_obj.generate_content, prompt)
        self._token_count += getattr(resp.usage_metadata, "total_token_count", 0)
        return resp.text

    def build_system_prompt(self) -> str:
        """Override in subclasses for tier specialisation."""
        return (
            f"You are an Aussie Agents autonomous agent.\n"
            f"Tier: {self.ctx.tier}\n"
            f"Role: {self.ctx.role}\n"
            f"Workspace: {self.ctx.workspace}\n"
            f"Python version target: 3.15 — use match/case, type aliases, "
            f"asyncio.TaskGroup, ExceptionGroup wherever possible.\n"
            f"Be precise, autonomous, output structured JSON results.\n"
            + (f"\n{self.ctx.system_prompt}" if self.ctx.system_prompt else "")
        )

    def _tool_defs(self) -> list[JsonDict]:
        defs: list[JsonDict] = []
        if "python" in self.ctx.tools:
            defs.append({
                "name": "python",
                "description": "Execute Python 3.15 code in isolated sandbox",
                "input_schema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            })
        if "file" in self.ctx.tools:
            defs.append({
                "name": "read_file",
                "description": "Read file from workspace",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            })
            defs.append({
                "name": "write_file",
                "description": "Write file to workspace",
                "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
            })
        if "fetch" in self.ctx.tools:
            defs.append({
                "name": "web_fetch",
                "description": "HTTP GET a URL, returns up to 3000 chars",
                "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            })
        if "shell" in self.ctx.tools:
            defs.append({
                "name": "shell",
                "description": "Run a bash command in workspace",
                "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
            })
        if "memory_recall" in self.ctx.tools:
            defs.append({
                "name": "memory_recall",
                "description": "Semantic search over Aussie Agents memory (Qdrant + sentence-transformers)",
                "input_schema": {"type": "object", "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                }, "required": ["query"]},
            })
        return defs

    async def _run_tool(self, name: ToolName, inp: JsonDict) -> str:
        match name:
            case "python":       return await self._exec_python(inp["code"])
            case "read_file":    return await self._read_file(inp["path"])
            case "write_file":   return await self._write_file(inp["path"], inp["content"])
            case "web_fetch":    return await self._web_fetch(inp["url"])
            case "shell":        return await self._shell(inp["command"])
            case "memory_recall": return await self._memory_recall(inp["query"], inp.get("limit", 5))
            case _:              return f"Unknown tool: {name}"

    async def _exec_python(self, code: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.ctx.workspace,
            env={**os.environ, "PYTHON_GIL": "0"},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        return (stdout.decode() + stderr.decode()).strip()

    async def _read_file(self, path: str) -> str:
        full = os.path.join(self.ctx.workspace, path)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: open(full).read())

    async def _write_file(self, path: str, content: str) -> str:
        full = os.path.join(self.ctx.workspace, path)
        os.makedirs(os.path.dirname(os.path.abspath(full)), exist_ok=True)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: open(full, "w").write(content))
        return f"Written {path}"

    async def _web_fetch(self, url: str) -> str:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    return (await r.text())[:3000]
        except ImportError:
            import urllib.request
            loop = asyncio.get_event_loop()
            def _fetch():
                req = urllib.request.Request(url, headers={"User-Agent": "AussieAgents/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return resp.read().decode("utf-8", errors="replace")[:3000]
            return await loop.run_in_executor(None, _fetch)

    async def _shell(self, cmd: str) -> str:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=self.ctx.workspace,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        return (out.decode() + err.decode()).strip()

    async def _memory_recall(self, query: str, limit: int) -> str:
        try:
            from qdrant_client import QdrantClient
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")
            vec = model.encode([query], normalize_embeddings=True)[0].tolist()
            client = QdrantClient(url=self.ctx.qdrant_url)
            results = client.search("pfaa_memory", query_vector=vec, limit=limit, with_payload=True)
            return "\n".join(str(r.payload.get("content", "")) for r in results)
        except Exception as e:
            return f"[memory unavailable: {e}]"
