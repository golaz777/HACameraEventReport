import base64
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from src.export import build_export_zip, export_filename
from src.report import build_manifest
from src.store import MotionEvent

JPEG_A = b"\xff\xd8\xff" + b"A" * 40
JPEG_B = b"\xff\xd8\xff" + b"B" * 40


def _report(tmp_path, events=None, html="<html><body>report</body></html>"):
    day = tmp_path / "2026-04-12"
    day.mkdir(exist_ok=True)
    report = day / "report_06-30-00.html"
    report.write_text(html)
    if events is not None:
        manifest = build_manifest(
            events,
            window_start=datetime(2026, 4, 11, 20, 0, tzinfo=timezone.utc),
            window_end=datetime(2026, 4, 12, 4, 30, tzinfo=timezone.utc),
            human_count=1,
            detection_enabled=True,
        )
        report.with_suffix(".json").write_text(json.dumps(manifest))
    return report


def _event(tmp_path, ts, name, data, human=None, conf=None, fname=None):
    path = None
    if data is not None:
        path = tmp_path / (fname or f"{name}-{ts:%H%M%S}.jpg")
        path.write_bytes(data)
    return MotionEvent(
        timestamp=ts, camera_name=name, camera_entity=f"camera.{name.lower()}",
        screenshot_path=str(path) if path else None,
        human_detected=human, human_confidence=conf,
    )


def _zip(tmp_path, report):
    dest = tmp_path / "out.zip"
    build_export_zip(report, dest)
    return zipfile.ZipFile(dest)


def _verify_sums(zf):
    lines = zf.read("SHA256SUMS").decode().splitlines()
    listed = {}
    for line in lines:
        digest, name = line.split("  ", 1)
        listed[name] = digest
    for name in zf.namelist():
        if name == "SHA256SUMS":
            continue
        assert listed[name] == hashlib.sha256(zf.read(name)).hexdigest()
    assert set(listed) == set(zf.namelist()) - {"SHA256SUMS"}


def test_export_filename():
    assert export_filename(Path("/m/2026-04-12/report_06-30-00.html")) == "camera-report_2026-04-12_06-30-00.zip"


def test_new_style_export_contents(tmp_path):
    ts1 = datetime(2026, 4, 11, 22, 14, 3, tzinfo=timezone.utc)
    ts2 = datetime(2026, 4, 12, 1, 0, 0, tzinfo=timezone.utc)
    events = [
        _event(tmp_path, ts1, "Driveway", JPEG_A, human=True, conf=0.912),
        _event(tmp_path, ts2, "Garden", JPEG_B, human=False, conf=None),
    ]
    report = _report(tmp_path, events)

    with _zip(tmp_path, report) as zf:
        names = set(zf.namelist())
        # 22:14:03 UTC on 2026-04-11 is 00:14:03 CEST on 2026-04-12
        assert names == {
            "report.html", "events.csv", "events.json", "SHA256SUMS",
            "snapshots/2026-04-12_00-14-03_driveway.jpg",
            "snapshots/2026-04-12_03-00-00_garden.jpg",
        }
        assert zf.read("report.html") == report.read_bytes()
        assert zf.read("snapshots/2026-04-12_00-14-03_driveway.jpg") == JPEG_A
        assert zf.getinfo("snapshots/2026-04-12_00-14-03_driveway.jpg").compress_type == zipfile.ZIP_STORED

        rows = list(csv.DictReader(io.StringIO(zf.read("events.csv").decode())))
        assert rows[0] == {
            "timestamp": "2026-04-12T00:14:03+02:00", "camera_name": "Driveway",
            "camera_entity": "camera.driveway", "human_detected": "yes",
            "human_confidence": "0.91", "snapshot": "snapshots/2026-04-12_00-14-03_driveway.jpg",
        }
        assert rows[1]["human_detected"] == "no"
        assert rows[1]["human_confidence"] == ""

        assert len(json.loads(zf.read("events.json"))) == 2
        _verify_sums(zf)


def test_unanalysed_event_has_empty_human_cell(tmp_path):
    ts = datetime(2026, 4, 11, 22, 0, tzinfo=timezone.utc)
    report = _report(tmp_path, [_event(tmp_path, ts, "Driveway", JPEG_A, human=None)])
    with _zip(tmp_path, report) as zf:
        rows = list(csv.DictReader(io.StringIO(zf.read("events.csv").decode())))
    assert rows[0]["human_detected"] == ""


def test_missing_snapshot_is_skipped(tmp_path):
    ts = datetime(2026, 4, 11, 22, 0, tzinfo=timezone.utc)
    event = _event(tmp_path, ts, "Driveway", JPEG_A)
    Path(event.screenshot_path).unlink()
    no_snap = _event(tmp_path, ts, "Garden", None)
    report = _report(tmp_path, [event, no_snap])

    with _zip(tmp_path, report) as zf:
        assert not [n for n in zf.namelist() if n.startswith("snapshots/")]
        rows = list(csv.DictReader(io.StringIO(zf.read("events.csv").decode())))
        assert [r["snapshot"] for r in rows] == ["", ""]
        _verify_sums(zf)


def test_unsluggable_and_colliding_names(tmp_path):
    ts = datetime(2026, 4, 11, 22, 0, tzinfo=timezone.utc)
    events = [
        _event(tmp_path, ts, "???", JPEG_A, fname="a.jpg"),
        _event(tmp_path, ts, "???", JPEG_B, fname="b.jpg"),
        _event(tmp_path, ts, "Vhod – dvorišče", JPEG_A, fname="c.jpg"),
    ]
    report = _report(tmp_path, events)
    with _zip(tmp_path, report) as zf:
        snaps = sorted(n for n in zf.namelist() if n.startswith("snapshots/"))
        assert snaps == [
            "snapshots/2026-04-12_00-00-00_camera.jpg",
            "snapshots/2026-04-12_00-00-00_camera_2.jpg",
            "snapshots/2026-04-12_00-00-00_vhod_dvori_e.jpg",
        ]
        assert zf.read("snapshots/2026-04-12_00-00-00_camera_2.jpg") == JPEG_B


def test_legacy_report_extracts_inline_images(tmp_path):
    a = base64.b64encode(JPEG_A).decode()
    b = base64.b64encode(JPEG_B).decode()
    html = f'<img src="data:image/jpeg;base64,{a}"><img src="data:image/png;base64,{b}">'
    report = _report(tmp_path, events=None, html=html)

    with _zip(tmp_path, report) as zf:
        assert set(zf.namelist()) == {
            "report.html", "SHA256SUMS",
            "snapshots/snapshot_001.jpg", "snapshots/snapshot_002.png",
        }
        assert zf.read("snapshots/snapshot_001.jpg") == JPEG_A
        _verify_sums(zf)


def test_corrupt_sidecar_falls_back_to_legacy(tmp_path):
    a = base64.b64encode(JPEG_A).decode()
    report = _report(tmp_path, html=f'<img src="data:image/jpeg;base64,{a}">')
    report.with_suffix(".json").write_text("{broken")

    with _zip(tmp_path, report) as zf:
        assert "events.csv" not in zf.namelist()
        assert zf.read("snapshots/snapshot_001.jpg") == JPEG_A


def test_sidecar_with_malformed_events_falls_back_to_legacy(tmp_path):
    a = base64.b64encode(JPEG_A).decode()
    report = _report(tmp_path, html=f'<img src="data:image/jpeg;base64,{a}">')
    report.with_suffix(".json").write_text(json.dumps({"version": 1, "events": [{"bogus": 1}]}))

    with _zip(tmp_path, report) as zf:
        assert set(zf.namelist()) == {"report.html", "SHA256SUMS", "snapshots/snapshot_001.jpg"}
        _verify_sums(zf)
