#!/usr/bin/env python3
"""Stop hook: store session episode directly via JMEM engine."""
import asyncio
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, "/Users/borris/Desktop/pfaa-engine/jmem-mcp-server")

from jmem.engine import JMemEngine, MemoryLevel


async def main():
    inp = {}
    try:
        data = sys.stdin.read(1_000_000)  # 1MB max
        if data.strip():
            inp = json.loads(data)
    except Exception:
        pass

    summary = inp.get("stop_reason") or inp.get("summary") or "Session ended"
    ts = datetime.now().isoformat()
    content = f"[{ts}] Session episode: {str(summary)[:500]}"

    e = JMemEngine(db_path=os.path.expanduser("~/.jmem/claude-code/memory.db"))
    await e.remember(content=content, level=MemoryLevel.EPISODE, tags=["auto-episode", "session"])
    print(json.dumps({"systemMessage": "JMEM: episode stored"}))


try:
    asyncio.run(main())
except Exception as ex:
    print(json.dumps({"systemMessage": f"JMEM auto-store skipped ({type(ex).__name__})"}))
