"""
PFAA Server — WebSocket + HTTP API for the framework.

Replaces Agent Zero's WebSocket monologue endpoint with a
proper streaming API that sends real-time events as goals execute.

Endpoints:
    WS  /ws/agent      — Send goals, receive streaming events
    GET /api/status     — Framework status
    GET /api/tools      — List available tools
    GET /api/memory     — Memory status + learned patterns
    POST /api/tool      — Execute a single tool
    POST /api/goal      — Execute a goal (returns when complete)
    GET /api/checkpoints — List saved goal checkpoints

Python 3.15: lazy import for FastAPI/uvicorn.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

lazy import json
lazy import uvicorn

from agent_setup_cli.core.framework import Framework
from agent_setup_cli.core.streaming import EventBus, EventType, Event

logger = logging.getLogger("pfaa.server")

# Lazy import FastAPI — only loads when server actually starts
lazy from fastapi import FastAPI, WebSocket, WebSocketDisconnect
lazy from fastapi.responses import JSONResponse
lazy from fastapi.middleware.cors import CORSMiddleware


def create_app(framework: Framework | None = None) -> FastAPI:
    """Create the PFAA FastAPI application."""
    app = FastAPI(
        title="PFAA — Phase-Fluid Agent Architecture",
        version="1.0.0",
        description="Self-improving agent framework with phase-fluid execution",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    fw = framework or Framework()
    bus = EventBus.get()

    # ── WebSocket Agent Endpoint ────────────────────────────────

    @app.websocket("/ws/agent")
    async def agent_websocket(websocket: WebSocket):
        """
        WebSocket endpoint for real-time agent interaction.

        Client sends:  {"type": "goal", "text": "analyze codebase..."}
                       {"type": "tool", "name": "compute", "args": ["sqrt(42)"]}
                       {"type": "status"}

        Server sends:  {"type": "event", "event_type": "TASK_COMPLETED", "data": {...}}
                       {"type": "result", "goal_id": "...", "status": "COMPLETED", ...}
                       {"type": "error", "message": "..."}
        """
        await websocket.accept()

        # Subscribe to events and forward to this WebSocket
        async def stream_event(event: Event):
            try:
                await websocket.send_text(json.dumps({
                    "type": "event",
                    "event_type": event.type.name,
                    "data": dict(event.data),
                    "timestamp": event.timestamp,
                }))
            except Exception:
                pass

        bus.subscribe_all(stream_event)

        try:
            # Send initial status
            await websocket.send_text(json.dumps({
                "type": "connected",
                "status": fw.status(),
            }))

            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON",
                    }))
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "goal":
                    text = msg.get("text", "")
                    if not text:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Missing 'text' field",
                        }))
                        continue

                    # Execute goal — events stream automatically via bus
                    state = await fw.run(text)

                    # Send final result
                    await websocket.send_text(json.dumps({
                        "type": "result",
                        "goal_id": state.goal_id,
                        "status": state.status.name,
                        "subtasks": [
                            {
                                "id": st.id,
                                "tool": st.tool_name or "claude",
                                "status": st.status,
                                "elapsed_us": st.elapsed_us,
                                "result": _safe_serialize(st.result),
                            }
                            for st in state.subtasks
                        ],
                    }))

                elif msg_type == "tool":
                    name = msg.get("name", "")
                    args = tuple(msg.get("args", []))
                    try:
                        result = await fw.tool(name, *args)
                        await websocket.send_text(json.dumps({
                            "type": "tool_result",
                            "tool": name,
                            "result": _safe_serialize(result),
                        }))
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": str(e),
                        }))

                elif msg_type == "status":
                    await websocket.send_text(json.dumps({
                        "type": "status",
                        "status": fw.status(),
                    }))

                elif msg_type == "memory":
                    await websocket.send_text(json.dumps({
                        "type": "memory",
                        "patterns": fw.learned_patterns(),
                        "strategies": fw.learned_strategies(),
                    }))

                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    }))

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as e:
            logger.error("WebSocket error: %s", e)

    # ── HTTP API Endpoints ──────────────────────────────────────

    @app.get("/api/status")
    async def get_status():
        return JSONResponse(fw.status())

    @app.get("/api/tools")
    async def get_tools():
        tools = fw._registry.list_tools()
        return JSONResponse([
            {
                "name": t.name,
                "description": t.description,
                "phase": t.phase.name,
                "isolated": t.isolated,
                "capabilities": list(t.capabilities),
            }
            for t in sorted(tools, key=lambda t: t.name)
        ])

    @app.get("/api/memory")
    async def get_memory():
        return JSONResponse({
            "status": fw._memory.status(),
            "patterns": fw.learned_patterns(),
            "strategies": fw.learned_strategies(),
        })

    @app.post("/api/tool")
    async def execute_tool(body: dict):
        name = body.get("name", "")
        args = tuple(body.get("args", []))
        try:
            result = await fw.tool(name, *args)
            return JSONResponse({"success": True, "result": _safe_serialize(result)})
        except Exception as e:
            return JSONResponse({"success": False, "error": str(e)}, status_code=400)

    @app.post("/api/goal")
    async def execute_goal(body: dict):
        text = body.get("text", "")
        if not text:
            return JSONResponse({"error": "Missing 'text'"}, status_code=400)
        state = await fw.run(text)
        return JSONResponse({
            "goal_id": state.goal_id,
            "status": state.status.name,
            "subtasks": [
                {
                    "id": st.id,
                    "tool": st.tool_name or "claude",
                    "status": st.status,
                    "elapsed_us": st.elapsed_us,
                }
                for st in state.subtasks
            ],
        })

    @app.get("/api/checkpoints")
    async def get_checkpoints():
        return JSONResponse(fw.checkpoints())

    @app.on_event("shutdown")
    async def on_shutdown():
        await fw.shutdown()

    return app


def _safe_serialize(obj: Any) -> Any:
    """Safely serialize an object for JSON, truncating large values."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_serialize(v) for v in obj[:100]]
    return str(obj)[:500]


def serve(host: str = "0.0.0.0", port: int = 8000):
    """Start the PFAA server."""
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    serve()
