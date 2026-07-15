from __future__ import annotations
import asyncio
import json
import logging
import os
from typing import Callable, Awaitable

import aiohttp

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict], Awaitable[None]]


class HAClient:
    def __init__(self):
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._event_callbacks: list[tuple[str, EventCallback]] = []

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        token = os.environ["SUPERVISOR_TOKEN"]
        self._ws = await self._session.ws_connect("http://supervisor/core/websocket")
        msg = await self._ws.receive_json()
        if msg["type"] != "auth_required":
            raise RuntimeError(f"Expected auth_required, got {msg}")
        await self._ws.send_json({"type": "auth", "access_token": token})
        msg = await self._ws.receive_json()
        if msg["type"] != "auth_ok":
            raise RuntimeError(f"HA WebSocket auth failed: {msg}")
        logger.info("Connected to HA WebSocket API (HA %s)", msg.get("ha_version", "?"))

    async def subscribe_events(self, event_type: str, callback: EventCallback) -> None:
        self._msg_id += 1
        self._event_callbacks.append((event_type, callback))
        await self._ws.send_json(
            {"id": self._msg_id, "type": "subscribe_events", "event_type": event_type}
        )

    async def get_state(self, entity_id: str) -> dict | None:
        self._msg_id += 1
        msg_id = self._msg_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        try:
            await self._ws.send_json({"id": msg_id, "type": "get_states"})
        except Exception:
            del self._pending[msg_id]
            raise
        states: list[dict] = await fut
        return next((s for s in states if s["entity_id"] == entity_id), None)

    async def camera_snapshot(self, entity_id: str, filepath: str) -> bool:
        """Download camera image via HA camera proxy. Returns True on success.

        Retries once after a short delay when HA returns HTTP 500, which can
        happen transiently while the ONVIF stream is active.
        """
        token = os.environ["SUPERVISOR_TOKEN"]
        url = f"http://supervisor/core/api/camera_proxy/{entity_id}"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            for attempt in range(2):
                if attempt:
                    await asyncio.sleep(1.5)
                _resp = await self._session.get(url, headers=headers)
                async with _resp as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        dirpart = os.path.dirname(filepath)
                        if dirpart:
                            os.makedirs(dirpart, exist_ok=True)
                        with open(filepath, "wb") as f:
                            f.write(data)
                        return True
                    logger.warning(
                        "Snapshot failed for %s: HTTP %d (attempt %d)",
                        entity_id, resp.status, attempt + 1,
                    )
            return False
        except Exception as exc:
            logger.warning("Snapshot error for %s: %s", entity_id, exc)
            return False

    async def send_notification(self, title: str, message: str) -> None:
        self._msg_id += 1
        await self._ws.send_json(
            {
                "id": self._msg_id,
                "type": "call_service",
                "domain": "persistent_notification",
                "service": "create",
                "service_data": {"title": title, "message": message},
            }
        )

    async def listen(self) -> None:
        """Message receive loop — run as the main asyncio task."""
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                await self._dispatch(data)
            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                logger.warning("HA WebSocket closed: %s", msg)
                break

    async def _dispatch(self, data: dict) -> None:
        if data.get("type") == "result":
            msg_id = data["id"]
            if msg_id in self._pending:
                if data["success"]:
                    self._pending[msg_id].set_result(data["result"])
                else:
                    self._pending[msg_id].set_exception(
                        Exception(str(data.get("error")))
                    )
                del self._pending[msg_id]
        elif data.get("type") == "event":
            event = data.get("event", {})
            event_type = event.get("event_type")
            for reg_type, cb in self._event_callbacks:
                if reg_type == event_type:
                    await cb(event)

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
