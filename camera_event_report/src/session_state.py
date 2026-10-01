from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SessionState:
    """Persists the away-session start so a restart does not truncate the session.

    Every method swallows I/O errors: losing the session start degrades the
    report to "events since restart", which is better than not monitoring.
    """

    def __init__(self, path: Path):
        self._path = Path(path)

    def load(self) -> datetime | None:
        try:
            with open(self._path, encoding="utf-8") as f:
                start = datetime.fromisoformat(json.load(f)["away_start"])
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Ignoring unreadable session file %s: %s", self._path, exc)
            return None
        if start.tzinfo is None:
            logger.warning("Ignoring session file %s: timestamp has no timezone", self._path)
            return None
        return start

    def save(self, start: datetime) -> None:
        tmp = self._path.with_suffix(".json.tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"away_start": start.isoformat()}, f)
            os.replace(tmp, self._path)
        except OSError as exc:
            logger.warning("Could not persist session start to %s: %s", self._path, exc)

    def clear(self) -> None:
        try:
            self._path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove session file %s: %s", self._path, exc)
