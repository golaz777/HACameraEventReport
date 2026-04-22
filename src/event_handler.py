from __future__ import annotations
import base64
import logging
import os
from datetime import datetime, timezone

from src.config import CameraConfig, Config
from src.snapshot import take_snapshot
from src.store import EventStore, MotionEvent

logger = logging.getLogger(__name__)


class EventHandler:
    def __init__(self, config: Config, ha_client, store: EventStore, presence_guard=None, broadcaster=None):
        self._config = config
        self._ha = ha_client
        self._store = store
        self._presence_guard = presence_guard
        self._broadcaster = broadcaster
        self._last_trigger: dict[str, datetime] = {}

    def _in_cooldown(self, camera: CameraConfig, now: datetime) -> bool:
        last = self._last_trigger.get(camera.entity_id)
        if last is None:
            return False
        return (now - last).total_seconds() < self._config.event_cooldown_seconds

    async def on_motion(self, camera: CameraConfig) -> None:
        monitoring_active = self._presence_guard is not None and self._presence_guard.is_away
        if not monitoring_active:
            return

        now = datetime.now(tz=timezone.utc)
        if self._in_cooldown(camera, now):
            logger.debug("Cooldown active for %s — skipping", camera.name)
            return

        self._last_trigger[camera.entity_id] = now
        logger.info("Motion: %s at %s", camera.name, now.isoformat())

        screenshot_path = await take_snapshot(
            self._ha, camera, now, self._config.media_path
        )
        if screenshot_path is None:
            logger.warning("Snapshot unavailable for %s", camera.name)

        event = MotionEvent(
            timestamp=now,
            camera_name=camera.name,
            camera_entity=camera.entity_id,
            screenshot_path=screenshot_path,
        )
        self._store.append(now.date(), event)

        if self._broadcaster is not None:
            screenshot_b64: str | None = None
            if screenshot_path and os.path.exists(screenshot_path):
                try:
                    with open(screenshot_path, "rb") as f:
                        screenshot_b64 = base64.b64encode(f.read()).decode("ascii")
                except Exception:
                    pass
            self._broadcaster.publish({
                "timestamp": now.isoformat(),
                "camera_name": camera.name,
                "camera_entity": camera.entity_id,
                "screenshot_b64": screenshot_b64,
            })

    async def on_ha_state_changed(self, ha_event: dict) -> None:
        """HA fallback: handle binary_sensor state_changed events."""
        data = ha_event.get("data", {})
        entity_id = data.get("entity_id", "")
        new_state = (data.get("new_state") or {}).get("state", "")

        if new_state != "on":
            return

        camera = next(
            (c for c in self._config.cameras if c.motion_entity == entity_id), None
        )
        if camera is None:
            return

        await self.on_motion(camera)
