"""
JMEM Daemon — Unix socket server keeping JMemEngine warm in memory.

Eliminates per-request startup cost (3-8s -> <10ms) by maintaining
a persistent engine instance accessible via JSON-RPC over a Unix domain socket.

Usage:
    python -m jmem.daemon --sock /tmp/pfaa-jmem.sock --db ~/.jmem/default/memory.db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time

from jmem.engine import JMemEngine, MemoryLevel

logger = logging.getLogger("jmem.daemon")


def _serialize_notes(notes: list) -> list[dict]:
    """Convert MemoryNote list to JSON-serializable dicts."""
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


class JMemDaemon:
    """Async Unix socket daemon wrapping JMemEngine."""

    def __init__(
        self,
        sock_path: str = "/tmp/pfaa-jmem.sock",
        db_path: str | None = None,
        pid_path: str = "/tmp/pfaa-jmem.pid",
        idle_timeout: float = 1800.0,  # 30 minutes
    ):
        self.sock_path = sock_path
        self.db_path = db_path
        self.pid_path = pid_path
        self.idle_timeout = idle_timeout
        self.engine = JMemEngine(db_path=db_path)
        self._server: asyncio.AbstractServer | None = None
        self._start_time: float = time.monotonic()
        self._last_activity: float = self._start_time
        self._shutdown_event = asyncio.Event()
        self._watchdog_task: asyncio.Task | None = None

    # ── Lifecycle ────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialize engine, write PID, start socket server + idle watchdog."""
        await self.engine.start()
        logger.info("JMemEngine initialized (db=%s)", self.db_path)

        # Clean stale socket
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

        self._server = await asyncio.start_unix_server(
            self._handle_client, path=self.sock_path
        )

        # Write PID file
        with open(self.pid_path, "w") as f:
            f.write(str(os.getpid()))

        self._last_activity = time.monotonic()
        self._watchdog_task = asyncio.create_task(self._idle_watchdog())

        logger.info("Daemon listening on %s (PID %d)", self.sock_path, os.getpid())

    async def stop(self) -> None:
        """Graceful shutdown: close server, engine, clean up files."""
        logger.info("Daemon shutting down...")
        self._shutdown_event.set()

        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        await self.engine.shutdown()

        # Clean up socket + PID
        for path in (self.sock_path, self.pid_path):
            try:
                if os.path.exists(path):
                    os.unlink(path)
            except OSError:
                pass

        logger.info("Daemon stopped, files cleaned up")

    async def run_forever(self) -> None:
        """Block until shutdown event is set."""
        await self._shutdown_event.wait()

    # ── Idle Watchdog ────────────────────────────────────────────

    async def _idle_watchdog(self) -> None:
        """Shut down after idle_timeout seconds of inactivity."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(5)
            idle = time.monotonic() - self._last_activity
            if idle >= self.idle_timeout:
                logger.info("Idle timeout (%.0fs) reached, shutting down", self.idle_timeout)
                self._shutdown_event.set()
                return

    # ── Client Handler ───────────────────────────────────────────

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single client connection (newline-delimited JSON-RPC)."""
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                self._last_activity = time.monotonic()

                try:
                    request = json.loads(line.decode())
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    response = {"error": f"Invalid JSON: {e}"}
                    writer.write(json.dumps(response).encode() + b"\n")
                    await writer.drain()
                    continue

                method = request.get("method", "")
                params = request.get("params", {})

                response = await self._dispatch(method, params)
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    # ── Method Dispatch ──────────────────────────────────────────

    async def _dispatch(self, method: str, params: dict) -> dict:
        """Route JSON-RPC method to engine call."""
        try:
            match method:
                case "ping":
                    return {"result": {"pong": True, "uptime": round(time.monotonic() - self._start_time, 1)}}

                case "recall":
                    notes = await self.engine.recall(
                        query=params.get("query", ""),
                        limit=params.get("limit", 5),
                        min_q=params.get("min_q", 0.0),
                        level=MemoryLevel(params["level"]) if "level" in params else None,
                    )
                    return {"result": _serialize_notes(notes)}

                case "remember":
                    level = MemoryLevel(params.get("level", 1))
                    note_id = await self.engine.remember(
                        content=params.get("content", ""),
                        level=level,
                        context=params.get("context", ""),
                        keywords=params.get("keywords"),
                        tags=params.get("tags"),
                    )
                    return {"result": {"id": note_id}}

                case "status":
                    result = await self.engine.status()
                    return {"result": result}

                case "consolidate":
                    result = await self.engine.consolidate()
                    return {"result": result}

                case "reward_recalled":
                    signal_val = params.get("reward_signal", 0.7)
                    result = await self.engine.reward_recalled(reward_signal=signal_val)
                    return {"result": result}

                case "decay":
                    hours = params.get("hours_threshold", 24.0)
                    result = await self.engine.decay_idle(hours_threshold=hours)
                    return {"result": result}

                case "reflect":
                    result = await self.engine.reflect()
                    return {"result": result}

                case _:
                    return {"error": f"Unknown method: {method}"}

        except Exception as e:
            logger.exception("Error dispatching %s", method)
            return {"error": f"{type(e).__name__}: {e}"}


# ── Signal Handling ──────────────────────────────────────────────


def _install_signal_handlers(daemon: JMemDaemon, loop: asyncio.AbstractEventLoop) -> None:
    """Register SIGTERM/SIGINT to trigger graceful shutdown."""
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: daemon._shutdown_event.set())


# ── CLI Entry Point ──────────────────────────────────────────────


async def _async_main(args: argparse.Namespace) -> None:
    daemon = JMemDaemon(
        sock_path=args.sock,
        db_path=args.db,
        pid_path=args.pid,
        idle_timeout=args.timeout,
    )

    loop = asyncio.get_running_loop()
    _install_signal_handlers(daemon, loop)

    await daemon.start()
    try:
        await daemon.run_forever()
    finally:
        await daemon.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="JMEM Daemon — persistent memory server")
    parser.add_argument("--sock", default="/tmp/pfaa-jmem.sock", help="Unix socket path")
    parser.add_argument("--db", default=None, help="Database path (default: ~/.jmem/default/memory.db)")
    parser.add_argument("--pid", default="/tmp/pfaa-jmem.pid", help="PID file path")
    parser.add_argument("--timeout", type=float, default=1800.0, help="Idle timeout in seconds (default: 1800)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
