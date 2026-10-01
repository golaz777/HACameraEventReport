from __future__ import annotations
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_CET = ZoneInfo("Europe/Paris")

from src.broadcaster import EventBroadcaster
from src.config import load_config, Config
from src.detector import HumanDetector
from src.ha_client import HAClient
from src.presence_guard import PresenceGuard
from src.event_handler import EventHandler
from src.ha_publisher import HAPublisher
from src.report import ReportEngine, build_manifest, load_report_info
from src.session_state import SessionState
from src.notifier import Notifier
from src.store import EventStore, MotionEvent
from src.web import WebServer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class App:
    def __init__(self):
        self.config: Config | None = None
        self.ha: HAClient | None = None
        self.presence_guard: PresenceGuard | None = None
        self.store: EventStore | None = None
        self.handler: EventHandler | None = None
        self.notifier: Notifier | None = None
        self.detector: HumanDetector | None = None
        self.session_state: SessionState | None = None
        self.publisher: HAPublisher | None = None
        # Set when startup saw the toggle unavailable/unknown with a session on disk.
        self._resume_pending = False
        self._away_start: datetime | None = None
        self._listen_task: asyncio.Task | None = None
        self._web_server: WebServer | None = None
        self._broadcaster: EventBroadcaster | None = None

    async def setup(self) -> None:
        self.config = load_config()
        self.ha = HAClient()
        await self.ha.connect()
        self._listen_task = asyncio.create_task(self.ha.listen())

        self._broadcaster = EventBroadcaster()
        self._web_server = WebServer(self.config, self.ha, self._broadcaster)
        await self._web_server.start()

        self.store = EventStore(self.config.media_path)
        if self.config.retention_days is not None:
            self.store.purge_old(self.config.retention_days)
        self.session_state = SessionState(Path(self.config.media_path) / "session.json")

        # Create PresenceGuard before EventHandler so it can be passed in
        if self.config.monitoring.toggle_entity:
            self.presence_guard = PresenceGuard()

        self.publisher = HAPublisher(
            self.ha,
            publish_entities=self.config.homeassistant.publish_entities,
            fire_events=self.config.homeassistant.fire_events,
        )
        self.handler = EventHandler(
            self.config, self.ha, self.store, self.presence_guard, self._broadcaster,
            self.publisher,
        )
        self.notifier = Notifier(self.config, self.ha)

        if self.config.detection.enabled:
            self.detector = HumanDetector(
                self.config.detection.model_path, self.config.detection.confidence
            )

        # Seed and wire PresenceGuard
        if self.presence_guard:
            toggle_state = await self.ha.get_state(
                self.config.monitoring.toggle_entity
            )
            if toggle_state:
                self.presence_guard.update_state(toggle_state["state"])
                self._restore_session(toggle_state["state"])
            else:
                logger.warning(
                    "Toggle entity %s not found in HA",
                    self.config.monitoring.toggle_entity,
                )
            self.presence_guard.on_away(self._on_away)
            self.presence_guard.on_home(self._on_home)

        await self._publish_initial(
            self.presence_guard is not None and self.presence_guard.is_away
        )

        await self.ha.subscribe_events("state_changed", self._on_ha_state_changed)

    async def _on_ha_state_changed(self, event: dict) -> None:
        data = event.get("data", {})
        entity_id = data.get("entity_id", "")

        if self.presence_guard and entity_id == self.config.monitoring.toggle_entity:
            new_state = (data.get("new_state") or {}).get("state", "")
            await self.presence_guard.handle_toggle_change(new_state)
            if new_state == "off" and self._resume_pending:
                # The deferred session ended while HA was unavailable.
                logger.warning("Away session ended while the toggle was unavailable — no report generated")
                self._resume_pending = False
                self.session_state.clear()
        else:
            await self.handler.on_ha_state_changed(event)

    def _restore_session(self, toggle_state: str) -> None:
        """Recover the away start persisted before a restart.

        Only an explicit "off" discards it: "unavailable"/"unknown" while HA
        boots must not truncate a session that is still running.
        """
        if self.presence_guard.is_away:
            self._away_start = self.session_state.load()
            if self._away_start is None:
                self._away_start = datetime.now(tz=timezone.utc)
                self.session_state.save(self._away_start)
            else:
                logger.info("Resumed away session started %s", self._away_start.isoformat())
        elif self.session_state.load() is not None:
            if toggle_state == "off":
                logger.warning(
                    "Away session ended while the add-on was not running — no report generated"
                )
                self.session_state.clear()
            else:
                self._resume_pending = True

    async def _on_away(self) -> None:
        now = datetime.now(tz=timezone.utc)
        persisted = None
        if self.session_state and self._resume_pending:
            persisted = self.session_state.load()
        self._resume_pending = False
        self._away_start = persisted or now
        if self.session_state:
            self.session_state.save(self._away_start)
        logger.info("Away monitoring started")
        if self.publisher:
            if persisted:
                # Resumed: the counters must include events before the outage.
                await self._publish_initial(True)
            else:
                await self.publisher.on_session_start(self._away_start)

    async def _publish_initial(self, is_away: bool) -> None:
        """Push full state to HA. Reading the store can fail (e.g. a log
        truncated by a power cut); that must not stop monitoring."""
        try:
            now = datetime.now(tz=timezone.utc)
            session_events = (
                self._session_events(self._away_start, now)
                if is_away and self._away_start
                else []
            )
            await self.publisher.publish_initial(
                is_away,
                self._away_start if is_away else None,
                session_events,
                load_report_info(self.config.media_path),
            )
        except Exception:
            logger.warning("Could not rebuild state for Home Assistant", exc_info=True)

    def _session_events(self, start: datetime, end: datetime) -> list[MotionEvent]:
        """Events in [start, end], read across every day log the window touches."""
        events: list[MotionEvent] = []
        d = start.date()
        while d <= end.date():
            events.extend(self.store.read(d))
            d += timedelta(days=1)
        events.sort(key=lambda e: e.timestamp)
        return [e for e in events if e.timestamp >= start]

    async def _on_home(self) -> None:
        now = datetime.now(tz=timezone.utc)
        now_cet = now.astimezone(_CET)
        start = self._away_start or now
        logger.info("Away monitoring ended — generating report")

        end_date = now.date()
        events = self._session_events(start, now)

        human_count = await self._detect_humans(events)

        detection_enabled = self.detector is not None and self.detector.available
        engine = ReportEngine()
        html = engine.generate(
            night=end_date,
            events=events,
            sunset_time=start.astimezone(_CET).strftime("%H:%M"),
            sunrise_time=now_cet.strftime("%H:%M"),
            human_count=human_count,
            detection_enabled=detection_enabled,
        )
        manifest = build_manifest(
            events,
            window_start=start,
            window_end=now,
            human_count=human_count,
            detection_enabled=detection_enabled,
        )
        report_path = engine.save(html, end_date, self.config.media_path, ts=now, manifest=manifest)
        if self.session_state:
            self.session_state.clear()

        await self.notifier.send_ha_notification(
            end_date, len(events), report_path, human_count=human_count
        )
        await self.notifier.send_email(end_date, len(events), html)
        if self.publisher:
            await self.publisher.on_report(
                night=end_date,
                report_path=report_path,
                event_count=len(events),
                human_count=human_count,
                detection_enabled=detection_enabled,
                ts=now,
            )
        logger.info(
            "Away report sent (%d events, %d with humans)", len(events), human_count
        )

    async def _detect_humans(self, events: list) -> int:
        """Analyse the session's snapshots and persist the verdicts.

        Returns the number of events containing a person, or 0 when detection
        is disabled or unavailable. Failures here are swallowed: a report
        without verdicts beats no report at all.
        """
        if not self.detector or not events:
            return 0
        try:
            human_count = await self.detector.analyze(events)
        except Exception:
            logger.exception("Human detection failed — continuing without verdicts")
            return 0

        # The away window can span days, and each day has its own event log.
        by_day: dict[date, list] = {}
        for event in events:
            by_day.setdefault(event.timestamp.date(), []).append(event)
        for day, day_events in by_day.items():
            try:
                self.store.update_detections(day, day_events)
            except Exception:
                logger.exception("Could not persist detection verdicts for %s", day)
        return human_count

    async def run(self) -> None:
        await self.setup()
        logger.info("Camera Event Report addon running")
        try:
            # Listen loop was started in setup() — wait for it to finish
            if self._listen_task:
                await self._listen_task
        finally:
            if self._web_server:
                await self._web_server.stop()
            if self.ha:
                await self.ha.close()


async def main() -> None:
    backoff = 1
    while True:
        try:
            app = App()
            await app.run()
        except Exception as exc:
            logger.error("App crashed: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        else:
            backoff = 1


if __name__ == "__main__":
    asyncio.run(main())
