#!/usr/bin/env python3
"""Stop hook: store session episode via JMEM daemon socket."""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from importlib import import_module
jmem_client = import_module("jmem-client")

inp = {}
try:
    data = sys.stdin.read(1_000_000)
    if data.strip():
        inp = json.loads(data)
except Exception:
    pass

summary = inp.get("stop_reason") or inp.get("summary") or "Session ended"
ts = datetime.now().isoformat()
content = f"[{ts}] Session episode: {str(summary)[:500]}"

result = jmem_client.jmem_request("remember", {
    "content": content,
    "level": 1,
    "tags": ["auto-episode", "session"],
})

if result is None:
    # Daemon not running — fall back to direct engine
    import asyncio
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent.parent / "jmem-mcp-server"))
    from jmem.engine import JMemEngine, MemoryLevel

    async def _fallback():
        e = JMemEngine(db_path=os.path.expanduser("~/.jmem/claude-code/memory.db"))
        await e.remember(content=content, level=MemoryLevel.EPISODE, tags=["auto-episode", "session"])

    try:
        asyncio.run(_fallback())
    except Exception:
        pass
