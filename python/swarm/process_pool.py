"""
Pre-warmed Python worker pool — eliminates cold start on every team dispatch.
Workers load all imports once at startup, then accept tasks via stdin JSON lines.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

def _preload():
    """Pre-import expensive modules at worker startup."""
    try:
        import anthropic  # noqa
    except ImportError:
        pass
    try:
        import google.generativeai  # noqa
    except ImportError:
        pass
    try:
        from sentence_transformers import SentenceTransformer
        global _SBERT
        _SBERT = SentenceTransformer("sentence-transformers/all-mpnet-base-v2", device="cpu")
    except ImportError:
        pass

_SBERT = None


async def worker_main():
    """Long-lived worker — reads task JSON lines from stdin, runs team, writes results."""
    _preload()

    # Signal ready
    sys.stdout.write(json.dumps({"status": "ready", "pid": os.getpid()}) + "\n")
    sys.stdout.flush()

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            # Add parent dir to path for imports
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from team_runner import run_team
            await run_team(payload["task"], payload["opts"])
        except Exception as e:
            sys.stdout.write(json.dumps({"type": "worker_error", "error": str(e)}) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    os.environ["PYTHON_GIL"] = "0"
    asyncio.run(worker_main())
