from __future__ import annotations
import logging
from datetime import date, datetime

from src.store import MotionEvent

logger = logging.getLogger(__name__)

# Public contract: user automations depend on these names. Tests pin them.
MONITORING = "binary_sensor.camera_event_report_monitoring"
SESSION_EVENTS = "sensor.camera_event_report_session_events"
LAST_MOTION = "sensor.camera_event_report_last_motion"
LAST_REPORT = "sensor.camera_event_report_last_report"
EVENT_MOTION = "camera_event_report_motion"
EVENT_REPORT_READY = "camera_event_report_report_ready"


class HAPublisher:
    """Mirrors add-on state into Home Assistant entities and events.

    Every public method swallows failures: HA being unreachable must never
    stop motion from being recorded or a report from being generated.
    """

    def __init__(self, ha_client, publish_entities: bool = True, fire_events: bool = True):
        self._ha = ha_client
        self._publish_entities = publish_entities
        self._fire_events = fire_events
        self._since: datetime | None = None
        self._per_camera: dict[str, int] = {}
        self._last_motion: MotionEvent | None = None

    async def publish_initial(
        self,
        is_away: bool,
        since: datetime | None,
        session_events: list[MotionEvent],
        last_report: dict | None,
    ) -> None:
        try:
            self._since = since if is_away else None
            self._per_camera = {}
            self._last_motion = None
            for event in sorted(session_events, key=lambda e: e.timestamp):
                self._count(event)
            await self._push_monitoring()
            await self._push_session_events()
            await self._push_last_motion()
            await self._push_last_report(last_report)
        except Exception:
            logger.warning("Could not publish initial state to HA", exc_info=True)

    async def on_session_start(self, since: datetime) -> None:
        try:
            self._since = since
            self._per_camera = {}
            self._last_motion = None
            await self._push_monitoring()
            await self._push_session_events()
        except Exception:
            logger.warning("Could not publish session start to HA", exc_info=True)

    async def on_motion(self, event: MotionEvent) -> None:
        try:
            self._count(event)
            await self._push_session_events()
            await self._push_last_motion()
            await self._fire(EVENT_MOTION, {
                "camera_name": event.camera_name,
                "camera_entity": event.camera_entity,
                "timestamp": event.timestamp.isoformat(),
                "snapshot_path": event.screenshot_path,
            })
        except Exception:
            logger.warning("Could not publish motion event to HA", exc_info=True)

    async def on_report(
        self,
        night: date,
        report_path: str,
        event_count: int,
        human_count: int,
        detection_enabled: bool,
        ts: datetime,
    ) -> None:
        try:
            self._since = None
            await self._push_monitoring()
            await self._push_last_report({
                "timestamp": ts.isoformat(),
                "event_count": event_count,
                "human_count": human_count,
                "detection_enabled": detection_enabled,
                "report_path": report_path,
            })
            await self._fire(EVENT_REPORT_READY, {
                "date": night.isoformat(),
                "report_path": report_path,
                "event_count": event_count,
                "human_count": human_count,
                "detection_enabled": detection_enabled,
            })
        except Exception:
            logger.warning("Could not publish report to HA", exc_info=True)

    def _count(self, event: MotionEvent) -> None:
        self._per_camera[event.camera_name] = self._per_camera.get(event.camera_name, 0) + 1
        if self._last_motion is None or event.timestamp >= self._last_motion.timestamp:
            self._last_motion = event

    async def _set(self, entity_id: str, state: str, attributes: dict) -> None:
        if self._publish_entities:
            await self._ha.set_state(entity_id, state, attributes)

    async def _fire(self, event_type: str, data: dict) -> None:
        if self._fire_events:
            await self._ha.fire_event(event_type, data)

    async def _push_monitoring(self) -> None:
        await self._set(MONITORING, "on" if self._since else "off", {
            "friendly_name": "Camera Event Report Monitoring",
            "icon": "mdi:shield-home",
            "since": self._since.isoformat() if self._since else None,
        })

    async def _push_session_events(self) -> None:
        await self._set(SESSION_EVENTS, str(sum(self._per_camera.values())), {
            "friendly_name": "Camera Event Report Session Events",
            "unit_of_measurement": "events",
            "state_class": "measurement",
            "per_camera": dict(self._per_camera),
        })

    async def _push_last_motion(self) -> None:
        e = self._last_motion
        await self._set(LAST_MOTION, e.timestamp.isoformat() if e else "unknown", {
            "friendly_name": "Camera Event Report Last Motion",
            "device_class": "timestamp",
            "camera_name": e.camera_name if e else None,
            "camera_entity": e.camera_entity if e else None,
            "snapshot_path": e.screenshot_path if e else None,
        })

    async def _push_last_report(self, info: dict | None) -> None:
        info = info or {}
        await self._set(LAST_REPORT, info.get("timestamp") or "unknown", {
            "friendly_name": "Camera Event Report Last Report",
            "device_class": "timestamp",
            "event_count": info.get("event_count"),
            "human_count": info.get("human_count"),
            "detection_enabled": info.get("detection_enabled"),
            "report_path": info.get("report_path"),
        })
