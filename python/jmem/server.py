"""
JMEM MCP Server — Persistent semantic memory for AI agents.

Zero external dependencies. Pure Python 3.12+ stdlib.
Implements MCP (Model Context Protocol) as JSON-RPC 2.0 over stdin/stdout.

7 tools: recall, remember, consolidate, reflect, reward, evolve, status.

Usage:
  pip install jmem-mcp-server
  claude mcp add jmem -- jmem-server

  # Or as module
  claude mcp add jmem -- python3 -m jmem

  # With agent identity
  claude mcp add jmem -- env JMEM_AGENT=coder jmem-server
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger("jmem.mcp")

type JsonRpcRequest = dict[str, Any]
type JsonRpcResponse = dict[str, Any]

AGENT_NAME = os.environ.get("JMEM_AGENT", os.environ.get("PFAA_AGENT_NAME", "default"))

_engine = None


async def _get_engine():
    global _engine
    if _engine is None:
        from jmem.engine import JMemEngine
        db_dir = os.path.expanduser("~/.jmem")
        os.makedirs(db_dir, exist_ok=True)
        _engine = JMemEngine(persist_dir=db_dir)
        await _engine.__aenter__()
        logger.info("JMEM initialized — agent=%s, db=%s", AGENT_NAME, db_dir)
    return _engine


def _safe(obj: Any) -> Any:
    if obj is None: return None
    if isinstance(obj, (str, int, float, bool)): return obj
    if isinstance(obj, dict): return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_safe(v) for v in obj[:100]]
    return str(obj)[:500]


TOOLS: list[dict[str, Any]] = [
    {
        "name": "jmem_recall",
        "description": "Search semantic memory using TF-IDF + Zettelkasten graph traversal. Returns memories ranked by relevance and Q-value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "top_k": {"type": "integer", "description": "Max results", "default": 5},
                "graph_walk": {"type": "boolean", "description": "Follow backlinks", "default": True},
            },
            "required": ["query"],
        },
    },
    {
        "name": "jmem_remember",
        "description": "Store a memory. Levels: episode (fact) -> concept (pattern) -> principle (rule) -> skill (capability).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory content"},
                "context": {"type": "string", "description": "When/where this applies", "default": ""},
                "keywords": {"type": "array", "items": {"type": "string"}, "default": []},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                "level": {"type": "string", "enum": ["episode", "concept", "principle", "skill"], "default": "episode"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "jmem_consolidate",
        "description": "Link related memories, promote up hierarchy, synthesize clusters, decay low-value notes.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "jmem_reflect",
        "description": "Full cognitive cycle — consolidation + drift detection, principle extraction, health analysis.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "jmem_reward",
        "description": "Reinforce a memory. Positive increases Q-value, negative decreases it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string"},
                "reward": {"type": "number", "description": "-1.0 to 1.0"},
                "context": {"type": "string", "default": ""},
            },
            "required": ["note_id", "reward"],
        },
    },
    {
        "name": "jmem_evolve",
        "description": "Update existing memory content or metadata in place.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string"},
                "content": {"type": "string"},
                "add_keywords": {"type": "array", "items": {"type": "string"}},
                "add_tags": {"type": "array", "items": {"type": "string"}},
                "context": {"type": "string"},
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "jmem_status",
        "description": "Health report — counts by level, Q-value stats, store info.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


async def _handle_recall(args: dict) -> Any:
    e = await _get_engine()
    notes = await e.recall(
        args["query"],
        top_k=args.get("top_k", 5),
        graph_walk=args.get("graph_walk", True),
    )
    return [
        {
            "id": n.id, "content": n.content[:500], "context": n.context,
            "level": n.level.value, "q_value": round(n.q_value, 3),
            "keywords": n.keywords, "tags": n.tags, "area": n.area,
            "retrieval_count": n.retrieval_count,
        }
        for n in notes
    ]


async def _handle_remember(args: dict) -> Any:
    e = await _get_engine()
    from jmem.engine import MemoryLevel
    level_map = {lv.value: lv for lv in MemoryLevel}
    note = await e.remember(
        content=args["content"],
        context=args.get("context", ""),
        keywords=args.get("keywords", []),
        tags=args.get("tags", []),
        level=level_map.get(args.get("level", "episode"), MemoryLevel.EPISODE),
        source=f"mcp:{AGENT_NAME}",
        area=AGENT_NAME,
    )
    return {"id": note.id, "level": note.level.value, "q_value": round(note.q_value, 3), "area": AGENT_NAME}


async def _handle_consolidate(args: dict) -> Any:
    return _safe(await (await _get_engine()).consolidate())


async def _handle_reflect(args: dict) -> Any:
    return _safe(await (await _get_engine()).reflect())


async def _handle_reward(args: dict) -> Any:
    e = await _get_engine()
    await e.reward(args["note_id"], args["reward"], args.get("context", f"mcp:{AGENT_NAME}"))
    return {"success": True, "note_id": args["note_id"], "reward": args["reward"]}


async def _handle_evolve(args: dict) -> Any:
    e = await _get_engine()
    note = await e.evolve(
        note_id=args["note_id"],
        new_content=args.get("content"),
        add_keywords=args.get("add_keywords"),
        add_tags=args.get("add_tags"),
        new_context=args.get("context"),
    )
    if note is None:
        return {"error": "Note not found"}
    return {
        "id": note.id, "content": note.content[:200],
        "evolution_count": note.evolution_count, "q_value": round(note.q_value, 3),
    }


async def _handle_status(args: dict) -> Any:
    return {"available": True, "agent": AGENT_NAME, **_safe(await (await _get_engine()).status())}


HANDLERS = {
    "jmem_recall": _handle_recall,
    "jmem_remember": _handle_remember,
    "jmem_consolidate": _handle_consolidate,
    "jmem_reflect": _handle_reflect,
    "jmem_reward": _handle_reward,
    "jmem_evolve": _handle_evolve,
    "jmem_status": _handle_status,
}

SERVER_INFO = {"name": "jmem", "version": "1.0.0"}


def _ok(rid: Any, result: Any) -> JsonRpcResponse:
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid: Any, code: int, msg: str) -> JsonRpcResponse:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


async def handle_request(req: JsonRpcRequest) -> JsonRpcResponse | None:
    method = req.get("method", "")
    params = req.get("params", {})
    rid = req.get("id")

    match method:
        case "initialize":
            return _ok(rid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            })
        case "notifications/initialized":
            return None
        case "ping":
            return _ok(rid, {})
        case "tools/list":
            return _ok(rid, {"tools": TOOLS})
        case "tools/call":
            name = params.get("name", "")
            handler = HANDLERS.get(name)
            if not handler:
                return _err(rid, -32602, f"Unknown tool: {name}")
            try:
                result = await handler(params.get("arguments", {}))
                return _ok(rid, {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
                    "isError": False,
                })
            except Exception as ex:
                logger.exception("Tool failed: %s", name)
                return _ok(rid, {
                    "content": [{"type": "text", "text": json.dumps({"error": str(ex)})}],
                    "isError": True,
                })
        case _:
            if rid:
                return _err(rid, -32601, f"Unknown method: {method}")
            return None


async def run_stdio():
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)
    stdout = sys.stdout.buffer

    logger.info("JMEM MCP server — agent=%s, transport=stdio", AGENT_NAME)

    buf = b""
    while True:
        chunk = await reader.read(65536)
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                out = json.dumps(_err(None, -32700, "Parse error")).encode() + b"\n"
                stdout.write(out)
                stdout.flush()
                continue
            response = await handle_request(request)
            if response:
                out = json.dumps(response, default=str).encode() + b"\n"
                stdout.write(out)
                stdout.flush()


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(name)s: %(message)s")
    asyncio.run(run_stdio())


if __name__ == "__main__":
    main()
