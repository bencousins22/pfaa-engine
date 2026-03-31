#!/usr/bin/env python3
"""SessionStart hook: recall JMEM context directly via engine."""
import asyncio
import json
import sys

sys.path.insert(0, "/Users/borris/Desktop/pfaa-engine/jmem-mcp-server")

from jmem.engine import JMemEngine


async def main():
    e = JMemEngine()
    r = await e.recall("recent learnings priorities context", limit=3, min_q=0.6)
    if r:
        notes = [{"content": n.content, "level": str(n.level), "q": n.q_value} for n in r]
        txt = json.dumps(notes, indent=2, default=str)[:1500]
        print(json.dumps({"systemMessage": "JMEM Context:\n" + txt}))
    else:
        print(json.dumps({"systemMessage": "JMEM: no recent memories found"}))


try:
    asyncio.run(main())
except Exception as ex:
    print(json.dumps({"systemMessage": f"JMEM auto-recall unavailable ({ex})"}))
