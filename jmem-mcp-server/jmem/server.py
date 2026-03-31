"""
JMEM MCP Server — JSON-RPC 2.0 over stdin/stdout.

Ported from https://github.com/Aussie-Agents/jmem-mcp-server

8 MCP Tools:
    jmem_recall       — Search semantic memory with TF-IDF + Zettelkasten graph
    jmem_remember     — Store memories at cognitive levels (episode→concept→principle→skill)
    jmem_consolidate  — Link related memories and synthesize clusters
    jmem_reflect      — Full cognitive cycle with principle extraction
    jmem_reward       — Reinforce memories via Q-value adjustment
    jmem_evolve       — Update existing memory content
    jmem_status       — Health reporting and statistics
    jmem_recall_cross — Cross-namespace search for multi-agent synthesis

Protocol: MCP (Model Context Protocol) via stdio transport.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Any

from jmem.engine import JMemEngine, MemoryLevel

logger = logging.getLogger("jmem.server")

AGENT_NAME = os.environ.get("PFAA_AGENT_NAME", "default")


# ── Tool Definitions ─────────────────────────────────────────────────

TOOLS = [
    {
        "name": "jmem_recall",
        "description": "Search JMEM semantic memory for relevant knowledge. Uses TF-IDF + BM25 + Q-boost hybrid search with Zettelkasten graph traversal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "description": "Max results", "default": 5},
                "level": {"type": "integer", "description": "Memory level filter (1=episode, 2=concept, 3=principle, 4=skill)"},
                "min_q": {"type": "number", "description": "Minimum Q-value threshold", "default": 0.0},
            },
            "required": ["query"],
        },
    },
    {
        "name": "jmem_remember",
        "description": "Store a memory at a cognitive level. Levels: 1=episode (raw), 2=concept (pattern), 3=principle (rule), 4=skill (capability).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Memory content"},
                "level": {"type": "integer", "description": "Cognitive level (1-4)", "default": 1},
                "context": {"type": "string", "description": "Contextual metadata"},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "Keywords for indexing"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "jmem_consolidate",
        "description": "Link related memories via keyword clustering, auto-promote high-Q episodes to concepts, and synthesize knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "jmem_reflect",
        "description": "Run a full cognitive cycle — statistics, health assessment, and knowledge summary.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "jmem_reward",
        "description": "Reinforce a memory via Q-learning. Positive reward (0-1) strengthens, negative (-1-0) weakens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "Memory ID to reinforce"},
                "reward": {"type": "number", "description": "Reward signal (-1 to 1)"},
                "context": {"type": "string", "description": "Reward context"},
            },
            "required": ["note_id", "reward"],
        },
    },
    {
        "name": "jmem_evolve",
        "description": "Mutate a memory's content while preserving its metadata and Q-value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "Memory ID to evolve"},
                "new_content": {"type": "string", "description": "Updated content"},
            },
            "required": ["note_id", "new_content"],
        },
    },
    {
        "name": "jmem_status",
        "description": "Get JMEM health report: memory counts by level, average Q-value, database size.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "jmem_reward_recalled",
        "description": "Auto-reward all memories that were recently recalled. Call after successful task completion to reinforce useful knowledge.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reward": {"type": "number", "description": "Reward signal (0-1, default 0.7)", "default": 0.7},
            },
        },
    },
    {
        "name": "jmem_decay",
        "description": "Apply time-based Q-decay to idle memories. Prevents stale knowledge from blocking promotion pipeline.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours_threshold": {"type": "number", "description": "Hours of inactivity before decay (default 24)", "default": 24.0},
            },
        },
    },
    {
        "name": "jmem_extract_skills",
        "description": "Auto-extract high-Q principles (Q≥0.92, retrievals≥5) into structured SKILL memories.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "jmem_meta_learn",
        "description": "L4 Meta-Learning: analyze the learning process itself. Examines Q-value distribution, promotion velocity, keyword diversity, and reward patterns. Auto-stores insights as META memories.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "jmem_emergent",
        "description": "L5 Emergent Knowledge: discover cross-cutting patterns across all memories. Finds keyword clusters, promotion chains, knowledge gaps, and graph density. Auto-stores discoveries as EMERGENT memories.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "jmem_recall_cross",
        "description": "Search across multiple agent namespaces and merge results by Q-value. Enables emergent cross-agent knowledge synthesis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "namespaces": {"type": "array", "items": {"type": "string"}, "description": "Agent namespaces to search (e.g. ['security', 'architect', 'tdd'])"},
                "limit": {"type": "integer", "description": "Max results across all namespaces", "default": 5},
            },
            "required": ["query", "namespaces"],
        },
    },
]


# ── Request Handler ──────────────────────────────────────────────────

async def handle_tool_call(engine: JMemEngine, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Route an MCP tool call to the engine."""
    if name == "jmem_recall":
        notes = await engine.recall(
            query=args["query"],
            limit=args.get("limit", 5),
            level=MemoryLevel(args["level"]) if args.get("level") else None,
            min_q=args.get("min_q", 0.0),
        )
        return {
            "memories": [
                {
                    "id": n.id,
                    "content": n.content,
                    "level": n.level.name,
                    "q_value": round(n.q_value, 3),
                    "keywords": n.keywords,
                    "retrieval_count": n.retrieval_count,
                }
                for n in notes
            ],
            "count": len(notes),
        }

    elif name == "jmem_remember":
        note_id = await engine.remember(
            content=args["content"],
            level=MemoryLevel(args.get("level", 1)),
            context=args.get("context", ""),
            keywords=args.get("keywords"),
            tags=args.get("tags"),
        )
        return {"id": note_id, "stored": True}

    elif name == "jmem_consolidate":
        stats = await engine.consolidate()
        return stats

    elif name == "jmem_reflect":
        return await engine.reflect()

    elif name == "jmem_reward":
        new_q = await engine.reward(
            note_id=args["note_id"],
            reward_signal=args["reward"],
            context=args.get("context", ""),
        )
        return {"note_id": args["note_id"], "new_q": round(new_q, 3)}

    elif name == "jmem_evolve":
        new_id = await engine.evolve(
            note_id=args["note_id"],
            new_content=args["new_content"],
        )
        return {"old_id": args["note_id"], "new_id": new_id}

    elif name == "jmem_status":
        return await engine.reflect()

    elif name == "jmem_reward_recalled":
        return await engine.reward_recalled(reward_signal=args.get("reward", 0.7))

    elif name == "jmem_decay":
        return await engine.decay_idle(hours_threshold=args.get("hours_threshold", 24.0))

    elif name == "jmem_extract_skills":
        return await engine.extract_skills()

    elif name == "jmem_meta_learn":
        return await engine.meta_learn()

    elif name == "jmem_emergent":
        return await engine.emergent_synthesis()

    elif name == "jmem_recall_cross":
        notes = await engine.recall_cross_namespace(
            query=args["query"],
            namespaces=args["namespaces"],
            limit=args.get("limit", 5),
        )
        return {
            "memories": [
                {
                    "id": n.id,
                    "content": n.content,
                    "level": n.level.name,
                    "q_value": round(n.q_value, 3),
                    "keywords": n.keywords,
                    "tags": n.tags,
                    "retrieval_count": n.retrieval_count,
                }
                for n in notes
            ],
            "count": len(notes),
            "namespaces_queried": args["namespaces"],
        }

    else:
        raise ValueError(f"Unknown tool: {name}")


# ── JSON-RPC Server ──────────────────────────────────────────────────

async def serve_stdio(engine: JMemEngine) -> None:
    """MCP server loop — JSON-RPC 2.0 over stdin/stdout."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    def _write(data: dict) -> None:
        sys.stdout.write(json.dumps(data) + "\n")
        sys.stdout.flush()

    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            request = json.loads(line.decode("utf-8").strip())
            method = request.get("method", "")
            params = request.get("params", {})
            req_id = request.get("id")

            if method == "initialize":
                _write({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "jmem-mcp-server",
                            "version": "1.0.0",
                        },
                    },
                })

            elif method == "notifications/initialized":
                pass  # No response needed

            elif method == "tools/list":
                _write({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": TOOLS},
                })

            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                try:
                    result = await handle_tool_call(engine, tool_name, tool_args)
                    _write({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                        },
                    })
                except Exception as e:
                    _write({
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"Error: {e}"}],
                            "isError": True,
                        },
                    })

            elif method == "ping":
                _write({"jsonrpc": "2.0", "id": req_id, "result": {}})

            else:
                _write({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                })

        except json.JSONDecodeError:
            continue
        except Exception as e:
            logger.error("Server error: %s", e)
            continue


def main() -> None:
    """Entry point for the JMEM MCP server."""
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s", stream=sys.stderr)

    db_path = os.path.join(os.path.expanduser("~/.jmem"), AGENT_NAME, "memory.db")
    engine = JMemEngine(namespace=AGENT_NAME, db_path=db_path)

    async def _run():
        await engine.start()
        try:
            await serve_stdio(engine)
        finally:
            await engine.shutdown()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
