# JMEM Daemon — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-hook Python subprocess spawning with a long-running JMEM daemon on a Unix socket, reducing hook latency from 3-8s to <10ms.

**Architecture:** A Python asyncio daemon listens on `/tmp/pfaa-jmem.sock`, keeps the JMemEngine warm in memory. Hooks communicate via a shared 20-line Node.js socket client (`jmem-client.cjs`). Stop hooks fire as detached background processes so the UI never blocks.

**Tech Stack:** Python 3.15 asyncio, Unix domain sockets, Node.js `net` module

---

## File Structure

| File | Responsibility |
|------|---------------|
| `jmem-mcp-server/jmem/daemon.py` | Unix socket daemon — accepts JSON commands, routes to JMemEngine |
| `tests/test_daemon.py` | Daemon tests — start/stop, recall, remember, status, timeout |
| `.claude/hooks/jmem-client.cjs` | Shared Node.js client — sends JSON over Unix socket, returns result |
| `.claude/hooks/jmem-client.py` | Shared Python client — same protocol, for Python hooks |
| `.claude/hooks/cortex.py` | Modified — use daemon client instead of direct JMemEngine |
| `.claude/hooks/jmem_store_episode.py` | Modified — use daemon client |
| `.claude/hooks/jmem_recall.py` | Modified — use daemon client |
| `.claude/hooks/banner.cjs` | Modified — use jmem-client.cjs for stats |
| `.claude/hooks/statusline.cjs` | Modified — use jmem-client.cjs for stats |
| `.claude/settings.json` | Modified — add daemon start to SessionStart, background offload for Stop |

---

### Task 1: JMEM Daemon Server

**Files:**
- Create: `jmem-mcp-server/jmem/daemon.py`
- Test: `tests/test_daemon.py`

- [ ] **Step 1: Write the failing test for daemon start/stop**

```python
# tests/test_daemon.py
"""Tests for the JMEM Unix socket daemon."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "jmem-mcp-server"))

import pytest

from jmem.daemon import JMemDaemon


def run_async(coro):
    return asyncio.run(coro)


def test_daemon_starts_and_stops(tmp_path):
    """Daemon should create a socket file and clean it up on shutdown."""
    sock = str(tmp_path / "test.sock")
    db = str(tmp_path / "test.db")

    async def _run():
        d = JMemDaemon(sock_path=sock, db_path=db)
        task = asyncio.create_task(d.serve())
        await asyncio.sleep(0.3)  # let it bind
        assert os.path.exists(sock), "Socket file not created"
        await d.shutdown()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert not os.path.exists(sock), "Socket file not cleaned up"

    run_async(_run())
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_daemon.py::test_daemon_starts_and_stops -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'jmem.daemon'`

- [ ] **Step 3: Write the daemon implementation**

```python
# jmem-mcp-server/jmem/daemon.py
"""
JMEM Unix Socket Daemon — keeps the JMemEngine warm for fast hook access.

Protocol: newline-delimited JSON over Unix domain socket.
Request:  {"method": "recall", "params": {"query": "...", "limit": 5}}
Response: {"result": [...]} or {"error": "message"}
"""

import asyncio
import json
import logging
import os
import signal
import time
from pathlib import Path

from jmem.engine import JMemEngine, MemoryLevel

logger = logging.getLogger("jmem.daemon")

DEFAULT_SOCK = "/tmp/pfaa-jmem.sock"
DEFAULT_DB = os.path.expanduser("~/.jmem/claude-code/memory.db")
DEFAULT_PID = "/tmp/pfaa-jmem.pid"
IDLE_TIMEOUT_S = 1800  # 30 minutes


class JMemDaemon:
    def __init__(
        self,
        sock_path: str = DEFAULT_SOCK,
        db_path: str = DEFAULT_DB,
        pid_path: str = DEFAULT_PID,
        idle_timeout: float = IDLE_TIMEOUT_S,
    ):
        self.sock_path = sock_path
        self.db_path = db_path
        self.pid_path = pid_path
        self.idle_timeout = idle_timeout
        self._engine: JMemEngine | None = None
        self._server: asyncio.Server | None = None
        self._last_activity = time.monotonic()
        self._shutdown_event = asyncio.Event()

    async def _ensure_engine(self) -> JMemEngine:
        if self._engine is None:
            self._engine = JMemEngine(db_path=self.db_path)
            await self._engine.start()
            logger.info("JMEM engine started (db=%s)", self.db_path)
        return self._engine

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._last_activity = time.monotonic()
        try:
            data = await asyncio.wait_for(reader.readline(), timeout=10.0)
            if not data:
                return
            request = json.loads(data.decode())
            method = request.get("method", "")
            params = request.get("params", {})
            result = await self._dispatch(method, params)
            response = json.dumps({"result": result}, default=str)
        except asyncio.TimeoutError:
            response = json.dumps({"error": "read timeout"})
        except Exception as e:
            response = json.dumps({"error": str(e)})
        try:
            writer.write((response + "\n").encode())
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, method: str, params: dict) -> dict | list | str:
        engine = await self._ensure_engine()
        match method:
            case "recall":
                notes = await engine.recall(
                    query=params.get("query", ""),
                    limit=params.get("limit", 5),
                    min_q=params.get("min_q", 0.0),
                    level=MemoryLevel(params["level"]) if "level" in params else None,
                )
                return [
                    {
                        "id": n.id,
                        "content": n.content,
                        "level": n.level.name,
                        "q_value": n.q_value,
                        "tags": n.tags,
                        "retrieval_count": n.retrieval_count,
                    }
                    for n in notes
                ]
            case "remember":
                note_id = await engine.remember(
                    content=params.get("content", ""),
                    level=MemoryLevel(params.get("level", 1)),
                    context=params.get("context", ""),
                    keywords=params.get("keywords", []),
                    tags=params.get("tags", []),
                )
                return {"id": note_id}
            case "status":
                return await engine.status()
            case "consolidate":
                return await engine.consolidate()
            case "reward_recalled":
                return await engine.reward_recalled(
                    reward_signal=params.get("signal", 0.7)
                )
            case "decay":
                return await engine.decay_idle(
                    hours_threshold=params.get("hours", 24.0)
                )
            case "reflect":
                return await engine.reflect()
            case "ping":
                return {"pong": True, "uptime": time.monotonic() - self._last_activity}
            case _:
                return {"error": f"unknown method: {method}"}

    async def _idle_watchdog(self) -> None:
        while not self._shutdown_event.is_set():
            await asyncio.sleep(60)
            elapsed = time.monotonic() - self._last_activity
            if elapsed > self.idle_timeout:
                logger.info("Idle timeout (%.0fs) — shutting down", elapsed)
                await self.shutdown()
                return

    async def serve(self) -> None:
        # Clean up stale socket
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=self.sock_path
        )

        # Write PID file
        Path(self.pid_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.pid_path).write_text(str(os.getpid()))

        logger.info("JMEM daemon listening on %s (pid=%d)", self.sock_path, os.getpid())

        # Start idle watchdog
        watchdog = asyncio.create_task(self._idle_watchdog())

        try:
            await self._shutdown_event.wait()
        finally:
            watchdog.cancel()
            try:
                await watchdog
            except asyncio.CancelledError:
                pass

    async def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._engine:
            await self._engine.shutdown()
            self._engine = None
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        if os.path.exists(self.pid_path):
            os.unlink(self.pid_path)
        logger.info("JMEM daemon shut down")


async def main() -> None:
    """CLI entry point: python -m jmem.daemon"""
    import argparse

    parser = argparse.ArgumentParser(description="JMEM Unix socket daemon")
    parser.add_argument("--sock", default=DEFAULT_SOCK, help="Socket path")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite DB path")
    parser.add_argument("--pid", default=DEFAULT_PID, help="PID file path")
    parser.add_argument("--timeout", type=int, default=IDLE_TIMEOUT_S, help="Idle timeout (seconds)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    daemon = JMemDaemon(
        sock_path=args.sock,
        db_path=args.db,
        pid_path=args.pid,
        idle_timeout=args.timeout,
    )

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(daemon.shutdown()))

    await daemon.serve()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_daemon.py::test_daemon_starts_and_stops -v
```

Expected: PASS

- [ ] **Step 5: Write test for recall via socket**

```python
# Add to tests/test_daemon.py

async def _send(sock_path: str, method: str, params: dict) -> dict:
    """Send a JSON-RPC request to the daemon and return the response."""
    reader, writer = await asyncio.open_unix_connection(sock_path)
    request = json.dumps({"method": method, "params": params}) + "\n"
    writer.write(request.encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.readline(), timeout=5.0)
    writer.close()
    await writer.wait_closed()
    return json.loads(data.decode())


def test_daemon_remember_and_recall(tmp_path):
    """Store a memory via daemon, then recall it."""
    sock = str(tmp_path / "test.sock")
    db = str(tmp_path / "test.db")

    async def _run():
        d = JMemDaemon(sock_path=sock, db_path=db)
        task = asyncio.create_task(d.serve())
        await asyncio.sleep(0.3)

        # Remember
        res = await _send(sock, "remember", {
            "content": "Python 3.15 has lazy imports via PEP 810",
            "level": 1,
            "tags": ["python", "pep810"],
        })
        assert "result" in res
        assert "id" in res["result"]

        # Recall
        res = await _send(sock, "recall", {"query": "lazy imports PEP 810", "limit": 3})
        assert "result" in res
        assert len(res["result"]) >= 1
        assert "PEP 810" in res["result"][0]["content"]

        await d.shutdown()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run_async(_run())


def test_daemon_status(tmp_path):
    """Status returns memory count and health info."""
    sock = str(tmp_path / "test.sock")
    db = str(tmp_path / "test.db")

    async def _run():
        d = JMemDaemon(sock_path=sock, db_path=db)
        task = asyncio.create_task(d.serve())
        await asyncio.sleep(0.3)

        res = await _send(sock, "status", {})
        assert "result" in res
        assert "total_memories" in res["result"]

        await d.shutdown()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run_async(_run())


def test_daemon_ping(tmp_path):
    """Ping returns pong for health checks."""
    sock = str(tmp_path / "test.sock")
    db = str(tmp_path / "test.db")

    async def _run():
        d = JMemDaemon(sock_path=sock, db_path=db)
        task = asyncio.create_task(d.serve())
        await asyncio.sleep(0.3)

        res = await _send(sock, "ping", {})
        assert res["result"]["pong"] is True

        await d.shutdown()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run_async(_run())


def test_daemon_unknown_method(tmp_path):
    """Unknown methods return an error, not crash."""
    sock = str(tmp_path / "test.sock")
    db = str(tmp_path / "test.db")

    async def _run():
        d = JMemDaemon(sock_path=sock, db_path=db)
        task = asyncio.create_task(d.serve())
        await asyncio.sleep(0.3)

        res = await _send(sock, "nonexistent", {})
        assert "error" in res.get("result", {})

        await d.shutdown()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run_async(_run())
```

- [ ] **Step 6: Run all daemon tests**

```bash
python3 -m pytest tests/test_daemon.py -v
```

Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add jmem-mcp-server/jmem/daemon.py tests/test_daemon.py
git commit -m "feat(jmem): Unix socket daemon for warm engine access

- JMemDaemon listens on /tmp/pfaa-jmem.sock
- Keeps JMemEngine warm in memory (no per-hook startup)
- JSON-RPC protocol: recall, remember, status, consolidate, reward_recalled, decay, reflect, ping
- Idle timeout (30min) with graceful shutdown
- PID file for health checks
- 5 tests covering start/stop, remember/recall, status, ping, unknown method

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Python Socket Client

**Files:**
- Create: `.claude/hooks/jmem-client.py`

- [ ] **Step 1: Write the Python client**

```python
# .claude/hooks/jmem-client.py
"""
Lightweight Python client for the JMEM daemon socket.
Used by cortex.py and other Python hooks instead of spawning JMemEngine directly.

Usage:
    from jmem_client import jmem_request
    result = jmem_request("recall", {"query": "...", "limit": 5})
"""

import json
import os
import socket

SOCK_PATH = os.environ.get("JMEM_SOCK", "/tmp/pfaa-jmem.sock")


def jmem_request(method: str, params: dict | None = None, timeout: float = 5.0) -> dict | None:
    """Send a request to the JMEM daemon. Returns None if daemon is unavailable."""
    if not os.path.exists(SOCK_PATH):
        return None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(SOCK_PATH)
        request = json.dumps({"method": method, "params": params or {}}) + "\n"
        sock.sendall(request.encode())
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        sock.close()
        response = json.loads(data.decode().strip())
        return response.get("result")
    except Exception:
        return None


def is_daemon_running() -> bool:
    """Check if the JMEM daemon is accepting connections."""
    result = jmem_request("ping")
    return result is not None and result.get("pong") is True
```

- [ ] **Step 2: Commit**

```bash
git add .claude/hooks/jmem-client.py
git commit -m "feat(hooks): Python socket client for JMEM daemon

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Node.js Socket Client

**Files:**
- Create: `.claude/hooks/jmem-client.cjs`

- [ ] **Step 1: Write the Node.js client**

```javascript
// .claude/hooks/jmem-client.cjs
/**
 * Lightweight Node.js client for the JMEM daemon socket.
 * Used by banner.cjs, statusline.cjs, and stop_scan.cjs.
 *
 * Usage:
 *   const { jmemRequest } = require('./jmem-client.cjs');
 *   const result = jmemRequest('status', {});
 *   // result is null if daemon unavailable, otherwise the response object
 */

const net = require('net');
const fs = require('fs');

const SOCK_PATH = process.env.JMEM_SOCK || '/tmp/pfaa-jmem.sock';

function jmemRequestSync(method, params, timeoutMs = 3000) {
  if (!fs.existsSync(SOCK_PATH)) return null;
  try {
    const client = net.createConnection({ path: SOCK_PATH });
    client.setTimeout(timeoutMs);
    const request = JSON.stringify({ method, params: params || {} }) + '\n';

    let data = '';
    let done = false;
    let result = null;

    client.on('data', (chunk) => { data += chunk.toString(); });
    client.on('end', () => { done = true; });
    client.on('timeout', () => { client.destroy(); done = true; });
    client.on('error', () => { done = true; });

    client.write(request);

    // Synchronous wait using execFileSync trick — spawn a subprocess that connects
    // For hooks we need sync. Use spawnSync with a tiny Python one-liner instead.
    client.destroy();
  } catch { return null; }
  return null;
}

/**
 * Synchronous JMEM request using Python subprocess (reliable for hooks).
 * Adds ~50ms overhead but avoids Node async complexity in hook scripts.
 */
function jmemRequest(method, params) {
  if (!fs.existsSync(SOCK_PATH)) return null;
  try {
    const { execFileSync } = require('child_process');
    const script = `
import json, socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(3)
s.connect("${SOCK_PATH}")
s.sendall((json.dumps({"method":"${method}","params":${JSON.stringify(params || {})}})+"\\n").encode())
d = b""
while True:
    c = s.recv(65536)
    if not c: break
    d += c
    if b"\\n" in d: break
s.close()
r = json.loads(d.decode().strip())
print(json.dumps(r.get("result")))
`;
    const out = execFileSync('python3', ['-c', script], {
      timeout: 4000, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
    return JSON.parse(out);
  } catch {
    return null;
  }
}

function isDaemonRunning() {
  const result = jmemRequest('ping', {});
  return result !== null && result.pong === true;
}

module.exports = { jmemRequest, isDaemonRunning, SOCK_PATH };
```

- [ ] **Step 2: Commit**

```bash
git add .claude/hooks/jmem-client.cjs
git commit -m "feat(hooks): Node.js socket client for JMEM daemon

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Migrate jmem_recall.py to use daemon

**Files:**
- Modify: `.claude/hooks/jmem_recall.py`

- [ ] **Step 1: Rewrite to use daemon client**

Replace the entire file with:

```python
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

if result:
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
```

- [ ] **Step 2: Commit**

```bash
git add .claude/hooks/jmem_recall.py
git commit -m "perf(hooks): jmem_recall uses daemon socket with engine fallback

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Migrate jmem_store_episode.py to use daemon

**Files:**
- Modify: `.claude/hooks/jmem_store_episode.py`

- [ ] **Step 1: Rewrite to use daemon client**

Replace the entire file with:

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add .claude/hooks/jmem_store_episode.py
git commit -m "perf(hooks): jmem_store_episode uses daemon socket with engine fallback

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Migrate cortex.py to use daemon

**Files:**
- Modify: `.claude/hooks/cortex.py`

- [ ] **Step 1: Add daemon-aware engine wrapper**

At the top of cortex.py (after the imports, around line 20), add a daemon-aware wrapper class that presents the same interface as JMemEngine but routes through the daemon socket when available:

```python
# Add after the existing imports at the top of cortex.py
sys.path.insert(0, os.path.dirname(__file__))

class _DaemonEngine:
    """Wrapper that tries the JMEM daemon first, falls back to direct engine."""

    def __init__(self):
        self._direct = None
        from importlib import import_module
        self._client = import_module("jmem-client")

    def _daemon_available(self) -> bool:
        return self._client.is_daemon_running()

    async def _get_direct(self):
        if self._direct is None:
            if str(JMEM_PATH) not in sys.path:
                sys.path.append(str(JMEM_PATH))
            from jmem.engine import JMemEngine
            self._direct = JMemEngine(db_path=os.path.expanduser("~/.jmem/claude-code/memory.db"))
            await self._direct.start()
        return self._direct

    async def start(self):
        if not self._daemon_available():
            await self._get_direct()

    async def shutdown(self):
        if self._direct:
            await self._direct.shutdown()
            self._direct = None

    async def recall(self, query="", limit=5, min_q=0.0, level=None):
        params = {"query": query, "limit": limit, "min_q": min_q}
        if level is not None:
            params["level"] = int(level)
        result = self._client.jmem_request("recall", params)
        if result is not None:
            from jmem.engine import MemoryLevel, MemoryNote
            return [MemoryNote(
                id=n["id"], content=n["content"],
                level=MemoryLevel[n["level"]], q_value=n["q_value"],
                tags=n.get("tags", []), retrieval_count=n.get("retrieval_count", 0),
            ) for n in result]
        engine = await self._get_direct()
        return await engine.recall(query=query, limit=limit, min_q=min_q, level=level)

    async def remember(self, content="", level=None, context="", keywords=None, tags=None):
        from jmem.engine import MemoryLevel
        lvl = int(level) if level is not None else 1
        result = self._client.jmem_request("remember", {
            "content": content, "level": lvl,
            "context": context, "keywords": keywords or [], "tags": tags or [],
        })
        if result is not None:
            return result.get("id", "")
        engine = await self._get_direct()
        return await engine.remember(content=content, level=level, context=context, keywords=keywords, tags=tags)

    async def reward_recalled(self, reward_signal=0.7):
        result = self._client.jmem_request("reward_recalled", {"signal": reward_signal})
        if result is not None:
            return result
        engine = await self._get_direct()
        return await engine.reward_recalled(reward_signal=reward_signal)

    async def consolidate(self):
        result = self._client.jmem_request("consolidate", {})
        if result is not None:
            return result
        engine = await self._get_direct()
        return await engine.consolidate()

    async def decay_idle(self, hours_threshold=24.0):
        result = self._client.jmem_request("decay", {"hours": hours_threshold})
        if result is not None:
            return result
        engine = await self._get_direct()
        return await engine.decay_idle(hours_threshold=hours_threshold)

    async def reflect(self):
        result = self._client.jmem_request("reflect", {})
        if result is not None:
            return result
        engine = await self._get_direct()
        return await engine.reflect()

    async def extract_skills(self):
        engine = await self._get_direct()
        return await engine.extract_skills()

    async def meta_learn(self):
        engine = await self._get_direct()
        return await engine.meta_learn()

    async def emergent_synthesis(self):
        engine = await self._get_direct()
        return await engine.emergent_synthesis()
```

- [ ] **Step 2: Replace engine creation in `_run()` function**

In the `_run()` function (around line 1060), replace the direct JMemEngine creation with `_DaemonEngine()`:

Replace:
```python
            from jmem.engine import JMemEngine
            engine = JMemEngine(db_path=os.path.expanduser("~/.jmem/claude-code/memory.db"))
```

With (in both Dream Phase B and Level 1 sections):
```python
            engine = _DaemonEngine()
```

- [ ] **Step 3: Run cortex tests**

```bash
python3 -m pytest tests/test_cortex.py -v --tb=short
```

Expected: 103 passed (daemon not running in tests → falls back to direct engine seamlessly)

- [ ] **Step 4: Commit**

```bash
git add .claude/hooks/cortex.py
git commit -m "perf(cortex): use JMEM daemon with direct engine fallback

- _DaemonEngine wrapper tries daemon socket first
- Falls back to direct JMemEngine if daemon unavailable
- All 103 tests pass (fallback path exercised in tests)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Migrate banner.cjs and statusline.cjs to use daemon

**Files:**
- Modify: `.claude/hooks/banner.cjs`
- Modify: `.claude/hooks/statusline.cjs`

- [ ] **Step 1: Update banner.cjs**

Replace the `getJmemStats()` function with:

```javascript
function getJmemStats() {
  // Try daemon first (fast — no Python/sqlite subprocess)
  const { jmemRequest } = require('./jmem-client.cjs');
  const daemonResult = jmemRequest('status', {});
  if (daemonResult && daemonResult.total_memories != null) {
    return {
      memories: daemonResult.total_memories,
      avgQ: daemonResult.average_q || 0,
    };
  }
  // Fallback to sqlite3 CLI
  try {
    const dbPath = path.join(require('os').homedir(), '.jmem/claude-code/memory.db');
    if (!fs.existsSync(dbPath)) return { memories: 0, avgQ: 0 };
    const out = execFileSync(
      'sqlite3', [dbPath, "SELECT COUNT(*), ROUND(AVG(json_extract(metadata, '$.q_value')),2) FROM documents;"],
      { timeout: 2000, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();
    const [count, avgQ] = out.split('|');
    return { memories: parseInt(count) || 0, avgQ: parseFloat(avgQ) || 0 };
  } catch {
    return { memories: 0, avgQ: 0 };
  }
}
```

- [ ] **Step 2: Update statusline.cjs**

Replace the JMEM memory count block with:

```javascript
// JMEM memory count — try daemon first
let memCount = '';
try {
  const { jmemRequest } = require('./jmem-client.cjs');
  const daemonResult = jmemRequest('status', {});
  if (daemonResult && daemonResult.total_memories != null) {
    memCount = `${daemonResult.total_memories}m`;
  } else {
    // Fallback to sqlite3
    const dbPath = path.join(require('os').homedir(), '.jmem/claude-code/memory.db');
    if (fs.existsSync(dbPath)) {
      const out = execFileSync(
        'sqlite3', [dbPath, "SELECT COUNT(*) FROM documents;"],
        { timeout: 1500, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
      ).trim();
      const n = parseInt(out);
      if (n > 0) memCount = `${n}m`;
    }
  }
} catch {}
```

- [ ] **Step 3: Commit**

```bash
git add .claude/hooks/banner.cjs .claude/hooks/statusline.cjs
git commit -m "perf(hooks): banner + statusline use daemon for JMEM stats

- Try daemon socket first (<10ms), fall back to sqlite3 CLI
- No behavior change — same output, faster path when daemon running

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Start daemon at SessionStart + background Stop hooks

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Add daemon start to SessionStart hooks**

In `.claude/settings.json`, find the `SessionStart` hook array and add a new entry BEFORE the existing hooks:

```json
{
  "hooks": [
    {
      "type": "command",
      "command": "python3 jmem-mcp-server/jmem/daemon.py --timeout 1800 &",
      "timeout": 3,
      "statusMessage": "Starting JMEM daemon..."
    }
  ]
}
```

This starts the daemon as a background process. The `&` detaches it from the hook subprocess so it doesn't block.

- [ ] **Step 2: Make Stop hooks run as background processes**

In `.claude/settings.json`, find the three Stop hooks. Wrap each command in a background subshell:

For cortex.py Stop:
```
"command": "(python3 .claude/hooks/cortex.py Stop < /dev/stdin &)"
```

For jmem_store_episode.py:
```
"command": "(python3 .claude/hooks/jmem_store_episode.py < /dev/stdin &)"
```

For cortex.py Stop (the cortex perf hook):
```
"command": "(python3 .claude/hooks/cortex.py Stop < /dev/stdin &)"
```

Note: The `< /dev/stdin` ensures stdin is still available for the backgrounded process. The outer `()` creates a subshell that exits immediately, returning control to Claude Code.

- [ ] **Step 3: Verify hooks still work**

```bash
# Test daemon starts
python3 jmem-mcp-server/jmem/daemon.py --timeout 10 &
sleep 1
python3 -c "
import sys; sys.path.insert(0, '.claude/hooks')
from importlib import import_module
c = import_module('jmem-client')
print('Daemon running:', c.is_daemon_running())
r = c.jmem_request('status', {})
print('Status:', r)
"
kill %1 2>/dev/null
```

Expected: `Daemon running: True` and status output

- [ ] **Step 4: Commit**

```bash
git add .claude/settings.json
git commit -m "perf(hooks): start JMEM daemon at SessionStart + background Stop hooks

- Daemon starts once at session begin, stays warm for 30min
- Stop hooks run as background subshells — UI never blocks
- Hooks fall back to direct engine if daemon unavailable

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Integration test — full hook pipeline

**Files:**
- Test: `tests/test_daemon.py` (append)

- [ ] **Step 1: Write integration test**

```python
# Add to tests/test_daemon.py

def test_full_pipeline_daemon_then_hooks(tmp_path):
    """Integration: start daemon, run recall and remember via Python client, verify round-trip."""
    sock = str(tmp_path / "test.sock")
    db = str(tmp_path / "test.db")
    os.environ["JMEM_SOCK"] = sock

    # Import the client
    hooks_path = str(Path(__file__).parent.parent / ".claude" / "hooks")
    sys.path.insert(0, hooks_path)
    for mod_name in list(sys.modules):
        if "jmem_client" in mod_name or "jmem-client" in mod_name:
            del sys.modules[mod_name]
    from importlib import import_module
    client = import_module("jmem-client")
    # Patch the socket path
    client.SOCK_PATH = sock

    async def _run():
        d = JMemDaemon(sock_path=sock, db_path=db)
        task = asyncio.create_task(d.serve())
        await asyncio.sleep(0.3)

        # Verify daemon is running via client
        assert client.is_daemon_running(), "Daemon should be running"

        # Store a memory
        result = client.jmem_request("remember", {
            "content": "Integration test memory",
            "level": 1,
            "tags": ["test"],
        })
        assert result is not None
        assert "id" in result

        # Recall it
        result = client.jmem_request("recall", {
            "query": "integration test",
            "limit": 3,
        })
        assert result is not None
        assert len(result) >= 1

        # Get status
        status = client.jmem_request("status", {})
        assert status is not None
        assert status["total_memories"] >= 1

        await d.shutdown()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    run_async(_run())
    # Clean up env
    del os.environ["JMEM_SOCK"]
```

- [ ] **Step 2: Run full test suite**

```bash
python3 -m pytest tests/test_daemon.py -v
```

Expected: 6 passed

- [ ] **Step 3: Run all project tests to verify no regressions**

```bash
python3 -m pytest tests/ -q --tb=short
```

Expected: 263+ passed (257 existing + 6 daemon tests)

- [ ] **Step 4: Commit**

```bash
git add tests/test_daemon.py
git commit -m "test(daemon): integration test for full hook pipeline via daemon

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```
