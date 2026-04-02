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
