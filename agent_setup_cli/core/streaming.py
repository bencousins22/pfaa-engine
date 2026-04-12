"""
Event Streaming — Real-time execution events for frontends.

Provides an async event bus that the framework uses to stream
progress, results, and errors to any connected client (WebSocket,
SSE, or in-process listener).

Events flow:
    Tool execution → EventBus → [WebSocket, CLI, Logger]

Python 3.15: lazy import, frozendict for immutable event payloads.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, TypeAlias

lazy import json

logger = logging.getLogger("pfaa.streaming")


class EventType(Enum):
    # Goal lifecycle
    GOAL_STARTED = auto()
    GOAL_DECOMPOSED = auto()
    GOAL_COMPLETED = auto()
    GOAL_FAILED = auto()

    # Subtask lifecycle
    TASK_STARTED = auto()
    TASK_COMPLETED = auto()
    TASK_FAILED = auto()
    TASK_RETRYING = auto()

    # Agent lifecycle
    AGENT_SPAWNED = auto()
    AGENT_PHASE_TRANSITION = auto()
    AGENT_REAPED = auto()

    # Memory
    MEMORY_PATTERN_LEARNED = auto()
    MEMORY_STRATEGY_LEARNED = auto()

    # System
    SYSTEM_STATUS = auto()
    LOG = auto()


@dataclass(frozen=True)
class Event:
    """Immutable event payload."""
    type: EventType
    timestamp: float
    id: str
    data: frozendict

    def to_dict(self) -> dict:
        return {
            "type": self.type.name,
            "timestamp": self.timestamp,
            "id": self.id,
            "data": dict(self.data),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


# Type alias for event handlers (Python 3.11 compatible)
EventHandler: TypeAlias = Callable[[Event], Any]


class EventBus:
    """
    Async event bus for streaming execution events.

    Usage:
        bus = EventBus()
        bus.subscribe(EventType.TASK_COMPLETED, my_handler)
        await bus.emit(EventType.TASK_COMPLETED, {"tool": "compute", "result": 42})

    For WebSocket streaming:
        async def ws_handler(event):
            await websocket.send_text(event.to_json())
        bus.subscribe_all(ws_handler)
    """

    _instance: EventBus | None = None

    def __init__(self):
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._history: list[Event] = []
        self._max_history: int = 1000

    @classmethod
    def get(cls) -> EventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to ALL event types."""
        self._global_handlers.append(handler)

    def unsubscribe_all_handlers(self) -> None:
        """Clear all subscriptions."""
        self._handlers.clear()
        self._global_handlers.clear()

    async def emit(self, event_type: EventType, data: dict | None = None) -> Event:
        """Emit an event to all subscribers."""
        event = Event(
            type=event_type,
            timestamp=time.time(),
            id=f"evt-{uuid.uuid4().hex[:8]}",
            data=frozendict(data or {}),
        )

        # Store in history
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # Dispatch to type-specific handlers
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Event handler error: %s", e)

        # Dispatch to global handlers
        for handler in self._global_handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error("Global event handler error: %s", e)

        return event

    def recent(self, n: int = 50, event_type: EventType | None = None) -> list[Event]:
        """Get recent events, optionally filtered by type."""
        if event_type:
            return [e for e in self._history if e.type == event_type][-n:]
        return self._history[-n:]

    @property
    def total_events(self) -> int:
        return len(self._history)
