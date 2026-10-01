from __future__ import annotations
import base64
import binascii
import csv
import hashlib
import io
import json
import logging
import re
import zipfile
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from src.report import read_manifest
from src.snapshot import _slugify
from src.store import _deserialize

logger = logging.getLogger(__name__)

_CET = ZoneInfo("Europe/Paris")
_DATA_URI_RE = re.compile(r"data:image/(\w+);base64,([A-Za-z0-9+/=]+)")
_CSV_FIELDS = [
    "timestamp", "camera_name", "camera_entity",
    "human_detected", "human_confidence", "snapshot",
]
_HUMAN_CELL = {True: "yes", False: "no", None: ""}

AddFile = Callable[[str, bytes, bool], None]


def export_filename(report_path: Path) -> str:
    stamp = report_path.stem.removeprefix("report_")
    return f"camera-report_{report_path.parent.name}_{stamp}.zip"


def build_export_zip(report_path: Path, dest: Path) -> None:
    """Bundle a report, its original snapshots and event data into a ZIP.

    Reports saved before manifests existed fall back to the images inlined in
    their HTML.
    """
    report_path = Path(report_path)
    manifest = read_manifest(report_path)
    sums: list[tuple[str, str]] = []

    with zipfile.ZipFile(dest, "w") as zf:
        def add(name: str, data: bytes, compress: bool) -> None:
            zf.writestr(
                name, data,
                compress_type=zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED,
            )
            sums.append((hashlib.sha256(data).hexdigest(), name))

        html = report_path.read_bytes()
        add("report.html", html, True)
        if manifest is None:
            _add_inline_images(html, add)
        else:
            _add_manifest_files(manifest, add)

        listing = "".join(f"{digest}  {name}\n" for digest, name in sums)
        zf.writestr("SHA256SUMS", listing, compress_type=zipfile.ZIP_DEFLATED)


def _add_manifest_files(manifest: dict, add: AddFile) -> None:
    used: set[str] = set()
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=_CSV_FIELDS)
    writer.writeheader()

    for record in manifest["events"]:
        event = _deserialize(record)
        local = event.timestamp.astimezone(_CET)
        snapshot = ""
        if event.screenshot_path:
            src = Path(event.screenshot_path)
            try:
                data = src.read_bytes()
            except OSError:
                logger.warning("Snapshot missing from export: %s", src)
            else:
                stem = f"{local:%Y-%m-%d_%H-%M-%S}_{_slugify(event.camera_name) or 'camera'}"
                snapshot = f"snapshots/{_unique(stem, src.suffix or '.jpg', used)}"
                add(snapshot, data, False)
        writer.writerow({
            "timestamp": local.isoformat(),
            "camera_name": event.camera_name,
            "camera_entity": event.camera_entity,
            "human_detected": _HUMAN_CELL[event.human_detected],
            "human_confidence": "" if event.human_confidence is None else f"{event.human_confidence:.2f}",
            "snapshot": snapshot,
        })

    add("events.csv", out.getvalue().encode("utf-8"), True)
    add("events.json", json.dumps(manifest["events"], indent=2).encode("utf-8"), True)


def _add_inline_images(html: bytes, add: AddFile) -> None:
    text = html.decode("utf-8", errors="ignore")
    for i, match in enumerate(_DATA_URI_RE.finditer(text), 1):
        try:
            data = base64.b64decode(match.group(2), validate=True)
        except binascii.Error:
            logger.warning("Skipping undecodable inline image %d", i)
            continue
        ext = "jpg" if match.group(1) in ("jpeg", "jpg") else match.group(1)
        add(f"snapshots/snapshot_{i:03d}.{ext}", data, False)


def _unique(stem: str, suffix: str, used: set[str]) -> str:
    name = f"{stem}{suffix}"
    n = 2
    while name in used:
        name = f"{stem}_{n}{suffix}"
        n += 1
    used.add(name)
    return name
