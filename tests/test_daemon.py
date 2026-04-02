"""Tests for JMEM daemon Unix socket server."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid

import pytest

# Ensure jmem package is importable from jmem-mcp-server
_mcp_path = os.path.join(os.path.dirname(__file__), "..", "jmem-mcp-server")
sys.path.insert(0, _mcp_path)
for mod_name in list(sys.modules):
    if mod_name.startswith("jmem"):
        del sys.modules[mod_name]

from jmem.daemon import JMemDaemon


def run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _send(sock_path: str, method: str, params: dict | None = None) -> dict:
    """Send a JSON-RPC request to the daemon and return the parsed response."""
    reader, writer = await asyncio.open_unix_connection(sock_path)
    request = {"method": method, "params": params or {}}
    writer.write(json.dumps(request).encode() + b"\n")
    await writer.drain()
    line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(line.decode())


def _short_sock() -> str:
    """Return a short /tmp socket path (macOS AF_UNIX limit is 104 chars)."""
    return f"/tmp/jt-{uuid.uuid4().hex[:8]}.sock"


async def _start_daemon(tmp_dir: str, sock_path: str) -> JMemDaemon:
    db = os.path.join(tmp_dir, "memory.db")
    pid = os.path.join(tmp_dir, "jmem.pid")
    d = JMemDaemon(sock_path=sock_path, db_path=db, pid_path=pid, idle_timeout=300)
    await d.start()
    return d


class TestDaemon:
    """JMEM daemon tests -- all use tmp dirs for db/pid, short /tmp paths for sockets."""

    def test_daemon_starts_and_stops(self, tmp_path):
        """Socket file created on start, cleaned up on stop."""
        sock = _short_sock()
        pid = str(tmp_path / "jmem.pid")

        async def _test():
            d = JMemDaemon(
                sock_path=sock,
                db_path=str(tmp_path / "memory.db"),
                pid_path=pid,
                idle_timeout=300,
            )
            await d.start()

            assert os.path.exists(sock), "Socket file should exist after start"
            assert os.path.exists(pid), "PID file should exist after start"

            with open(pid) as f:
                assert f.read().strip() == str(os.getpid())

            await d.stop()

            assert not os.path.exists(sock), "Socket should be cleaned up after stop"
            assert not os.path.exists(pid), "PID should be cleaned up after stop"

        try:
            run(_test())
        finally:
            # Safety cleanup in case test fails mid-way
            for p in (sock, pid):
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass

    def test_daemon_remember_and_recall(self, tmp_path):
        """Store a memory then recall it back."""
        sock = _short_sock()

        async def _test():
            d = await _start_daemon(str(tmp_path), sock)
            try:
                resp = await _send(d.sock_path, "remember", {
                    "content": "The capital of Australia is Canberra",
                    "level": 1,
                    "tags": ["geography"],
                })
                assert "result" in resp
                assert "note_id" in resp["result"]

                resp = await _send(d.sock_path, "recall", {
                    "query": "capital Australia",
                    "limit": 3,
                })
                assert "result" in resp
                results = resp["result"]
                assert len(results) >= 1
                assert "Canberra" in results[0]["content"]
            finally:
                await d.stop()

        try:
            run(_test())
        finally:
            try:
                os.unlink(sock)
            except FileNotFoundError:
                pass

    def test_daemon_status(self, tmp_path):
        """Status returns store info."""
        sock = _short_sock()

        async def _test():
            d = await _start_daemon(str(tmp_path), sock)
            try:
                await _send(d.sock_path, "remember", {"content": "test status memory"})
                resp = await _send(d.sock_path, "status")
                assert "result" in resp
                result = resp["result"]
                assert "namespace" in result
                assert "store" in result
            finally:
                await d.stop()

        try:
            run(_test())
        finally:
            try:
                os.unlink(sock)
            except FileNotFoundError:
                pass

    def test_daemon_ping(self, tmp_path):
        """Ping returns pong."""
        sock = _short_sock()

        async def _test():
            d = await _start_daemon(str(tmp_path), sock)
            try:
                resp = await _send(d.sock_path, "ping")
                assert resp == {"result": {"pong": True}}
            finally:
                await d.stop()

        try:
            run(_test())
        finally:
            try:
                os.unlink(sock)
            except FileNotFoundError:
                pass

    def test_daemon_unknown_method(self, tmp_path):
        """Unknown method returns error without crashing the daemon."""
        sock = _short_sock()

        async def _test():
            d = await _start_daemon(str(tmp_path), sock)
            try:
                resp = await _send(d.sock_path, "nonexistent_method", {"foo": "bar"})
                assert "error" in resp
                assert "Unknown method" in resp["error"]

                # Daemon should still be alive
                resp2 = await _send(d.sock_path, "ping")
                assert resp2 == {"result": {"pong": True}}
            finally:
                await d.stop()

        try:
            run(_test())
        finally:
            try:
                os.unlink(sock)
            except FileNotFoundError:
                pass
