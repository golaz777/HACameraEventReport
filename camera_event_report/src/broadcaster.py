from __future__ import annotations
import asyncio
import logging

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Pub/sub hub for real-time motion events over SSE."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def publish(self, data: dict) -> None:
        dead: set[asyncio.Queue] = set()
        for q in self._subscribers:
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                dead.add(q)
        for q in dead:
            self._subscribers.discard(q)
            logger.debug("Dropped slow SSE subscriber")
