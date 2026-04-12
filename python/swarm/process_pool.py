"""
Pre-warmed Python worker pool — eliminates cold start on every team dispatch.

Workers pre-load expensive modules (anthropic, sentence_transformers) once at
startup, then stay alive accepting tasks via a stdin/stdout JSON-line protocol.

Python 3.15 features:
  - match/case for message routing
  - PEP 695 type aliases
  - asyncio.TaskGroup for structured concurrency
  - ExceptionGroup / except* for fault isolation
  - PYTHON_GIL=0 for free-threaded embedding inference
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, asdict
from typing import Any, TypeAlias

# ---------------------------------------------------------------------------
# PEP 695 type aliases
# ---------------------------------------------------------------------------
JsonDict: TypeAlias = dict[str, Any]
WorkerStatus: TypeAlias = str  # "ready" | "busy" | "error"

# ---------------------------------------------------------------------------
# Pre-load expensive modules
# ---------------------------------------------------------------------------
_SBERT = None


def _preload() -> dict[str, bool]:
    """Pre-import expensive modules at worker startup. Returns load report."""
    loaded: dict[str, bool] = {}

    try:
        import anthropic  # noqa: F401
        loaded["anthropic"] = True
    except ImportError:
        loaded["anthropic"] = False

    try:
        from sentence_transformers import SentenceTransformer
        global _SBERT
        _SBERT = SentenceTransformer(
            "sentence-transformers/all-mpnet-base-v2", device="cpu"
        )
        loaded["sentence_transformers"] = True
    except ImportError:
        loaded["sentence_transformers"] = False

    return loaded


# ---------------------------------------------------------------------------
# Worker dataclasses
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class WorkerEnvelope:
    """Wraps every outbound message from the worker."""
    type: str
    pid: int
    ts: float
    payload: JsonDict

    def to_json(self) -> str:
        return json.dumps(asdict(self))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def _emit(msg_type: str, payload: JsonDict | None = None) -> None:
    """Write a single JSON line to stdout and flush."""
    envelope = WorkerEnvelope(
        type=msg_type,
        pid=os.getpid(),
        ts=time.monotonic(),
        payload=payload or {},
    )
    sys.stdout.write(envelope.to_json() + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Task dispatcher — uses match/case for routing
# ---------------------------------------------------------------------------
async def _dispatch(payload: JsonDict) -> JsonDict:
    """Route an incoming task payload via match/case."""
    action: str = payload.get("action", "run_team")

    match action:
        case "run_team":
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from team_runner import run_team

            result = await run_team(payload["task"], payload["opts"])
            return asdict(result)

        case "ping":
            return {"pong": True, "pid": os.getpid()}

        case "reload":
            report = _preload()
            return {"reloaded": True, "modules": report}

        case _:
            return {"error": f"unknown action: {action}"}


# ---------------------------------------------------------------------------
# Main worker loop — never exits between tasks
# ---------------------------------------------------------------------------
async def worker_main() -> None:
    """
    Long-lived worker process.

    1. Pre-loads heavy modules.
    2. Signals 'ready' to the parent via stdout JSON.
    3. Reads task JSON lines from stdin forever.
    4. Runs each task, writes result JSON to stdout.
    5. Never exits between tasks — the parent reuses this process.
    """
    load_report = _preload()

    # Signal ready to parent
    _emit("ready", {"modules": load_report})

    # Set up async stdin reader
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            # stdin closed — parent is gone, exit gracefully
            break

        line = line.strip()
        if not line:
            continue

        task_start = time.monotonic()
        _emit("task_start", {})

        try:
            payload: JsonDict = json.loads(line)

            # Structured concurrency: wrap dispatch in a TaskGroup so any
            # spawned subtasks are properly awaited / cancelled on error.
            task_error_group = None
            try:
                async with asyncio.TaskGroup() as tg:
                    task = tg.create_task(_dispatch(payload), name="dispatch")
            except* Exception as eg:
                task_error_group = eg

            if task_error_group is not None:
                errors = [str(e) for e in task_error_group.exceptions]
                _emit("task_error", {
                    "errors": errors,
                    "duration_ms": int((time.monotonic() - task_start) * 1000),
                })
                continue

            result = task.result()
            _emit("task_done", {
                "result": result,
                "duration_ms": int((time.monotonic() - task_start) * 1000),
            })

        except json.JSONDecodeError as e:
            _emit("task_error", {
                "error": f"invalid JSON: {e}",
                "duration_ms": int((time.monotonic() - task_start) * 1000),
            })
        except Exception as e:
            _emit("task_error", {
                "error": str(e),
                "duration_ms": int((time.monotonic() - task_start) * 1000),
            })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Enable free-threading (Python 3.13+ / 3.15 default)
    os.environ["PYTHON_GIL"] = "0"

    # Ignore SIGINT so the parent controls lifecycle
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    asyncio.run(worker_main())
