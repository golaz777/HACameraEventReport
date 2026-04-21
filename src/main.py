from __future__ import annotations
import asyncio
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_CET = ZoneInfo("Europe/Paris")

from src.config import load_config, Config
from src.ha_client import HAClient
from src.presence_guard import PresenceGuard
from src.event_handler import EventHandler
from src.report import ReportEngine
from src.notifier import Notifier
from src.store import EventStore
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
        self._away_start: datetime | None = None
        self._listen_task: asyncio.Task | None = None
        self._web_server: WebServer | None = None

    async def setup(self) -> None:
        self.config = load_config()
        self.ha = HAClient()
        await self.ha.connect()
        self._listen_task = asyncio.create_task(self.ha.listen())

        self._web_server = WebServer(self.config, self.ha)
        await self._web_server.start()

        self.store = EventStore(self.config.media_path)

        # Create PresenceGuard before EventHandler so it can be passed in
        if self.config.monitoring.toggle_entity:
            self.presence_guard = PresenceGuard()

        self.handler = EventHandler(
            self.config, self.ha, self.store, self.presence_guard
        )
        self.notifier = Notifier(self.config, self.ha)

        # Seed and wire PresenceGuard
        if self.presence_guard:
            toggle_state = await self.ha.get_state(
                self.config.monitoring.toggle_entity
            )
            if toggle_state:
                self.presence_guard.update_state(toggle_state["state"])
                if self.presence_guard.is_away:
                    self._away_start = datetime.now(tz=timezone.utc)
            else:
                logger.warning(
                    "Toggle entity %s not found in HA",
                    self.config.monitoring.toggle_entity,
                )
            self.presence_guard.on_away(self._on_away)
            self.presence_guard.on_home(self._on_home)

        await self.ha.subscribe_events("state_changed", self._on_ha_state_changed)

    async def _on_ha_state_changed(self, event: dict) -> None:
        data = event.get("data", {})
        entity_id = data.get("entity_id", "")

        if self.presence_guard and entity_id == self.config.monitoring.toggle_entity:
            new_state = (data.get("new_state") or {}).get("state", "")
            await self.presence_guard.handle_toggle_change(new_state)
        else:
            await self.handler.on_ha_state_changed(event)

    async def _on_away(self) -> None:
        self._away_start = datetime.now(tz=timezone.utc)
        logger.info("Away monitoring started")

    async def _on_home(self) -> None:
        now = datetime.now(tz=timezone.utc)
        now_cet = now.astimezone(_CET)
        start = self._away_start or now
        logger.info("Away monitoring ended — generating report")

        # Collect events across all dates from start to now (handles multi-day absences)
        start_date = start.date()
        end_date = now.date()
        events = []
        d = start_date
        while d <= end_date:
            events.extend(self.store.read(d))
            d = date.fromordinal(d.toordinal() + 1)
        events.sort(key=lambda e: e.timestamp)
        # Keep only events that occurred during the away window
        events = [e for e in events if e.timestamp >= start]

        engine = ReportEngine()
        html = engine.generate(
            night=end_date,
            events=events,
            sunset_time=start.astimezone(_CET).strftime("%H:%M"),
            sunrise_time=now_cet.strftime("%H:%M"),
        )
        report_path = engine.save(html, end_date, self.config.media_path, ts=now)

        await self.notifier.send_ha_notification(end_date, len(events), report_path)
        await self.notifier.send_email(end_date, len(events), html)
        logger.info("Away report sent (%d events)", len(events))

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
