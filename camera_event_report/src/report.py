from __future__ import annotations
import base64
import logging
import os
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_CET = ZoneInfo("Europe/Paris")
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.store import MotionEvent

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class _RichEvent:
    """Wraps MotionEvent adding base64-encoded screenshot for template rendering."""

    def __init__(self, event: MotionEvent):
        self.timestamp = event.timestamp.astimezone(_CET)
        self.camera_name = event.camera_name
        self.camera_entity = event.camera_entity
        self.screenshot_b64 = self._load_b64(event.screenshot_path)
        self.human_detected = event.human_detected
        self.human_confidence = event.human_confidence

    @staticmethod
    def _load_b64(path: str | None) -> str | None:
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("ascii")
        except Exception as exc:
            logger.warning("Could not encode screenshot %s: %s", path, exc)
            return None


class ReportEngine:
    def __init__(self):
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

    def generate(
        self,
        night: date,
        events: list[MotionEvent],
        sunset_time: str,
        sunrise_time: str,
        human_count: int = 0,
        detection_enabled: bool = False,
    ) -> str:
        template = self._env.get_template("report.html.j2")
        return template.render(
            night=night.isoformat(),
            events=[_RichEvent(e) for e in events],
            sunset_time=sunset_time,
            sunrise_time=sunrise_time,
            human_count=human_count,
            detection_enabled=detection_enabled,
        )

    def save(self, html: str, night: date, base_path: str, ts: datetime | None = None) -> str:
        if ts is None:
            ts = datetime.now(tz=timezone.utc)
        ts_cet = ts.astimezone(_CET)
        out_dir = Path(base_path) / night.isoformat()
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = ts_cet.strftime("%H-%M-%S")
        report_path = out_dir / f"report_{stamp}.html"
        report_path.write_text(html, encoding="utf-8")
        logger.info("Report saved to %s", report_path)
        return str(report_path)


# The summary block wraps values in <span>, which the original pattern missed —
# every saved report parsed as an unknown count. The wrapper is optional here so
# reports saved by any version still parse.
_EVENT_COUNT_RE = re.compile(r"<strong>Total events:</strong>\s*(?:<span>)?\s*(\d+)")
_HUMAN_COUNT_RE = re.compile(
    r"<strong>Humans detected:</strong>\s*<span[^>]*>\s*(\d+)"
)


def _extract_counts(path: Path) -> tuple[int | None, int | None]:
    """Recover (event_count, human_count) from a saved report's summary block."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None, None
    ev = _EVENT_COUNT_RE.search(text)
    hu = _HUMAN_COUNT_RE.search(text)
    return (
        int(ev.group(1)) if ev else None,
        int(hu.group(1)) if hu else None,
    )


def _extract_event_count(path: Path) -> int | None:
    return _extract_counts(path)[0]


def list_reports(base_path: str) -> list[dict]:
    """Return all report HTML files under base_path, newest first.

    Each entry: {"date": "YYYY-MM-DD", "filename": "report_HH-MM-SS.html",
                 "event_count": int | None, "human_count": int | None}

    human_count is None for reports written before human detection existed, or
    when detection was disabled for that session.
    """
    base = Path(base_path)
    if not base.exists():
        return []
    reports = []
    for day_dir in sorted(base.iterdir(), reverse=True):
        if not day_dir.is_dir():
            continue
        for f in sorted(day_dir.glob("report*.html"), reverse=True):
            event_count, human_count = _extract_counts(f)
            reports.append({
                "date": day_dir.name,
                "filename": f.name,
                "event_count": event_count,
                "human_count": human_count,
            })
    return reports
