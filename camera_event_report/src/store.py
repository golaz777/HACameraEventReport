from __future__ import annotations
import json
import logging
import os
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
    # None = snapshot not analysed; False = analysed, no person found.
    human_detected: bool | None = None
    human_confidence: float | None = None


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
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(_serialize(event)) + "\n")

    def purge_old(self, retention_days: int, keep_from: date | None = None) -> None:
        """Remove day directories older than retention_days from today.

        Directories on or after keep_from (the start of a running away
        session) are kept so a long absence still gets a complete report.
        """
        cutoff = date.today() - timedelta(days=retention_days)
        if keep_from is not None:
            cutoff = min(cutoff, keep_from)
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
                events.append(_deserialize(json.loads(line)))
        return events

    def update_detections(self, night: date, events: list[MotionEvent]) -> None:
        """Rewrite a day's log with detection verdicts from `events`.

        Records are matched on (timestamp, camera_entity). Records with no
        matching event are preserved untouched. The log is replaced atomically
        so an interrupted write cannot truncate the event history.
        """
        path = self._log_path(night)
        if not path.exists():
            return
        verdicts = {
            (e.timestamp.isoformat(), e.camera_entity): e
            for e in events
            if e.human_detected is not None
        }
        if not verdicts:
            return

        tmp = path.with_suffix(".json.tmp")
        with open(path, encoding="utf-8") as src, open(tmp, "w", encoding="utf-8") as dst:
            for line in src:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                match = verdicts.get((d["timestamp"], d["camera_entity"]))
                if match is not None:
                    d["human_detected"] = match.human_detected
                    d["human_confidence"] = match.human_confidence
                dst.write(json.dumps(d) + "\n")
        os.replace(tmp, path)

    def list_dates(self) -> list[date]:
        """Return sorted list of dates that have events.json files."""
        if not self._base.exists():
            return []
        dates = []
        for entry in self._base.iterdir():
            if not entry.is_dir():
                continue
            try:
                d = date.fromisoformat(entry.name)
                dates.append(d)
            except ValueError:
                continue
        return sorted(dates)

    def read_range(self, start: date, end: date) -> dict[date, list[MotionEvent]]:
        """Read events for each date in [start, end] inclusive.

        Returns a dict mapping each date to a list of events.
        Dates with no events are included with empty lists.
        """
        result = {}
        current = start
        while current <= end:
            result[current] = self.read(current)
            current += timedelta(days=1)
        return result


def _serialize(event: MotionEvent) -> dict:
    return {
        "timestamp": event.timestamp.isoformat(),
        "camera_name": event.camera_name,
        "camera_entity": event.camera_entity,
        "screenshot_path": event.screenshot_path,
        "human_detected": event.human_detected,
        "human_confidence": event.human_confidence,
    }


def _deserialize(d: dict) -> MotionEvent:
    """Build a MotionEvent from a log record.

    Detection keys are read with .get() — logs written before human detection
    existed have no such keys and must still load.
    """
    confidence = d.get("human_confidence")
    return MotionEvent(
        timestamp=datetime.fromisoformat(d["timestamp"]),
        camera_name=d["camera_name"],
        camera_entity=d["camera_entity"],
        screenshot_path=d["screenshot_path"],
        human_detected=d.get("human_detected"),
        human_confidence=None if confidence is None else float(confidence),
    )
