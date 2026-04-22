from __future__ import annotations
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MotionEvent:
    timestamp: datetime
    camera_name: str
    camera_entity: str
    screenshot_path: str | None


class EventStore:
    def __init__(self, base_path: str = "/media/onvif_events"):
        self._base = Path(base_path)

    def _log_path(self, night: date) -> Path:
        return self._base / night.isoformat() / "events.json"

    def append(self, night: date, event: MotionEvent) -> None:
        if event.timestamp.tzinfo is None:
            raise ValueError("MotionEvent.timestamp must be timezone-aware")
        path = self._log_path(night)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": event.timestamp.isoformat(),
            "camera_name": event.camera_name,
            "camera_entity": event.camera_entity,
            "screenshot_path": event.screenshot_path,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def purge_old(self, retention_days: int) -> None:
        """Remove day directories older than retention_days from today."""
        cutoff = date.today() - timedelta(days=retention_days)
        if not self._base.exists():
            return
        for entry in self._base.iterdir():
            if not entry.is_dir():
                continue
            try:
                day = date.fromisoformat(entry.name)
            except ValueError:
                continue
            if day < cutoff:
                shutil.rmtree(entry)
                logger.info("Purged old event directory: %s", entry.name)

    def read(self, night: date) -> list[MotionEvent]:
        path = self._log_path(night)
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                events.append(
                    MotionEvent(
                        timestamp=datetime.fromisoformat(d["timestamp"]),
                        camera_name=d["camera_name"],
                        camera_entity=d["camera_entity"],
                        screenshot_path=d["screenshot_path"],
                    )
                )
        return events
