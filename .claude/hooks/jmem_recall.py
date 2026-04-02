#!/usr/bin/env python3
"""SessionStart hook: recall JMEM context via daemon socket."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from importlib import import_module
jmem_client = import_module("jmem-client")

result = jmem_client.jmem_request("recall", {
    "query": "recent learnings priorities context",
    "limit": 3,
    "min_q": 0.6,
})

if result is not None and len(result) > 0:
    notes = [{"content": n["content"], "level": n["level"], "q": n["q_value"]} for n in result]
    txt = json.dumps(notes, indent=2, default=str)[:1500]
    print(json.dumps({"systemMessage": "JMEM Context:\n" + txt}))
elif result is None:
    # Daemon not running — fall back to direct engine
    import asyncio
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent.parent / "jmem-mcp-server"))
    from jmem.engine import JMemEngine

    async def _fallback():
        e = JMemEngine(db_path=os.path.expanduser("~/.jmem/claude-code/memory.db"))
        r = await e.recall("recent learnings priorities context", limit=3, min_q=0.6)
        if r:
            notes = [{"content": n.content, "level": str(n.level), "q": n.q_value} for n in r]
            txt = json.dumps(notes, indent=2, default=str)[:1500]
            print(json.dumps({"systemMessage": "JMEM Context:\n" + txt}))
        else:
            print(json.dumps({"systemMessage": "JMEM: no recent memories found"}))

    try:
        asyncio.run(_fallback())
    except Exception as ex:
        print(json.dumps({"systemMessage": f"JMEM auto-recall unavailable ({type(ex).__name__})"}))
else:
    print(json.dumps({"systemMessage": "JMEM: no recent memories found"}))
