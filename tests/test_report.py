import pytest
from datetime import date, datetime, timezone
from pathlib import Path
from src.report import ReportEngine, list_reports
from src.store import MotionEvent


@pytest.fixture
def two_events():
    return [
        MotionEvent(
            timestamp=datetime(2026, 4, 12, 23, 14, 2, tzinfo=timezone.utc),
            camera_name="Front Door",
            camera_entity="camera.front_door",
            screenshot_path=None,
        ),
        MotionEvent(
            timestamp=datetime(2026, 4, 13, 1, 37, 55, tzinfo=timezone.utc),
            camera_name="Back Yard",
            camera_entity="camera.back_yard",
            screenshot_path=None,
        ),
    ]


def test_report_contains_event_times(two_events):
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 4, 12),
        events=two_events,
        sunset_time="20:45",
        sunrise_time="06:12",
    )
    # Timestamps are converted to CET/CEST — April is CEST (UTC+2)
    assert "01:14:02" in html
    assert "03:37:55" in html


def test_report_contains_camera_names(two_events):
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 4, 12),
        events=two_events,
        sunset_time="20:45",
        sunrise_time="06:12",
    )
    assert "Front Door" in html
    assert "Back Yard" in html


def test_report_contains_date(two_events):
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 4, 12),
        events=two_events,
        sunset_time="20:45",
        sunrise_time="06:12",
    )
    assert "2026-04-12" in html


def test_report_embeds_screenshot_as_base64(tmp_path):
    screenshot = tmp_path / "snap.jpg"
    screenshot.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

    events = [
        MotionEvent(
            timestamp=datetime(2026, 4, 12, 23, 14, 2, tzinfo=timezone.utc),
            camera_name="Front Door",
            camera_entity="camera.front_door",
            screenshot_path=str(screenshot),
        )
    ]
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 4, 12),
        events=events,
        sunset_time="20:45",
        sunrise_time="06:12",
    )
    assert "data:image/jpeg;base64," in html


def test_report_no_events_message():
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 4, 12),
        events=[],
        sunset_time="20:45",
        sunrise_time="06:12",
    )
    assert "No motion events detected" in html


def test_save_creates_html_file(two_events, tmp_path):
    ts = datetime(2026, 4, 12, 20, 45, 0, tzinfo=timezone.utc)
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 4, 12),
        events=two_events,
        sunset_time="20:45",
        sunrise_time="06:12",
    )
    path = engine.save(html, date(2026, 4, 12), str(tmp_path), ts=ts)
    assert Path(path).exists()
    assert "report_22-45-00.html" in path  # 20:45 UTC → 22:45 CEST (UTC+2)
    assert "2026-04-12" in path


def test_save_filename_uses_timestamp(two_events, tmp_path):
    ts = datetime(2026, 4, 13, 6, 12, 30, tzinfo=timezone.utc)
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 4, 12),
        events=two_events,
        sunset_time="20:45",
        sunrise_time="06:12",
    )
    path = engine.save(html, date(2026, 4, 12), str(tmp_path), ts=ts)
    assert "report_08-12-30.html" in path  # 06:12 UTC → 08:12 CEST (UTC+2)


def test_list_reports_empty(tmp_path):
    assert list_reports(str(tmp_path)) == []


def test_list_reports_returns_reports_newest_first(tmp_path):
    (tmp_path / "2026-04-11").mkdir()
    (tmp_path / "2026-04-11" / "report_20-00-00.html").write_text("a")
    (tmp_path / "2026-04-12").mkdir()
    (tmp_path / "2026-04-12" / "report_06-00-00.html").write_text("b")
    (tmp_path / "2026-04-12" / "report_21-00-00.html").write_text("c")

    reports = list_reports(str(tmp_path))

    assert len(reports) == 3
    # Newest first
    assert reports[0]["date"] == "2026-04-12"
    assert reports[0]["filename"] == "report_21-00-00.html"
    assert reports[1]["date"] == "2026-04-12"
    assert reports[2]["date"] == "2026-04-11"


def test_list_reports_ignores_non_report_files(tmp_path):
    (tmp_path / "2026-04-12").mkdir()
    (tmp_path / "2026-04-12" / "report_20-00-00.html").write_text("r")
    (tmp_path / "2026-04-12" / "events.json").write_text("{}")
    (tmp_path / "2026-04-12" / "snap.jpg").write_bytes(b"")

    reports = list_reports(str(tmp_path))

    assert len(reports) == 1
    assert reports[0]["filename"] == "report_20-00-00.html"


def _analysed(detected, confidence=0.9):
    return MotionEvent(
        timestamp=datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc),
        camera_name="Front Door",
        camera_entity="camera.front_door",
        screenshot_path=None,
        human_detected=detected,
        human_confidence=confidence,
    )


def test_report_shows_human_badge_for_detection():
    html = ReportEngine().generate(
        night=date(2026, 10, 1),
        events=[_analysed(True, 0.88)],
        sunset_time="20:00",
        sunrise_time="07:00",
        human_count=1,
        detection_enabled=True,
    )

    assert "<th>Person</th>" in html
    assert "badge-human" in html
    assert ">Human<" in html
    assert "0.88" in html


def test_report_shows_clear_badge_when_no_person():
    html = ReportEngine().generate(
        night=date(2026, 10, 1),
        events=[_analysed(False, 0.03)],
        sunset_time="20:00",
        sunrise_time="07:00",
        human_count=0,
        detection_enabled=True,
    )

    assert ">Clear<" in html
    assert ">Human<" not in html


def test_report_distinguishes_unanalysed_from_clear():
    """A frame never analysed must not be reported as free of people."""
    html = ReportEngine().generate(
        night=date(2026, 10, 1),
        events=[_analysed(None, None)],
        sunset_time="20:00",
        sunrise_time="07:00",
        detection_enabled=True,
    )

    assert "badge-unknown" in html
    assert ">Clear<" not in html
    assert ">Human<" not in html


def test_report_summarises_human_count():
    html = ReportEngine().generate(
        night=date(2026, 10, 1),
        events=[_analysed(True), _analysed(False, 0.1)],
        sunset_time="20:00",
        sunrise_time="07:00",
        human_count=1,
        detection_enabled=True,
    )

    assert "Humans detected:" in html
    assert "of 2 snapshot(s)" in html


def test_report_omits_detection_markup_when_disabled(two_events):
    html = ReportEngine().generate(
        night=date(2026, 10, 1),
        events=two_events,
        sunset_time="20:00",
        sunrise_time="07:00",
    )

    assert "<th>Person</th>" not in html
    assert "Humans detected:" not in html


def test_event_count_is_recoverable_from_saved_report(tmp_path, two_events):
    """Regression: the summary block is parsed back by the Reports page."""
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 10, 1),
        events=two_events,
        sunset_time="20:00",
        sunrise_time="07:00",
        human_count=1,
        detection_enabled=True,
    )
    engine.save(html, date(2026, 10, 1), str(tmp_path))

    report = list_reports(str(tmp_path))[0]
    assert report["event_count"] == 2
    assert report["human_count"] == 1


def test_human_count_is_none_for_reports_without_detection(tmp_path, two_events):
    engine = ReportEngine()
    html = engine.generate(
        night=date(2026, 10, 1),
        events=two_events,
        sunset_time="20:00",
        sunrise_time="07:00",
    )
    engine.save(html, date(2026, 10, 1), str(tmp_path))

    report = list_reports(str(tmp_path))[0]
    assert report["event_count"] == 2
    assert report["human_count"] is None


import json
from src.report import build_manifest, read_manifest, load_report_info


def _manifest(events):
    return build_manifest(
        events,
        window_start=datetime(2026, 4, 12, 20, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 4, 13, 4, 30, tzinfo=timezone.utc),
        human_count=1,
        detection_enabled=True,
    )


def test_build_manifest_shape(two_events):
    m = _manifest(two_events)
    assert m["version"] == 1
    assert m["window_start"] == "2026-04-12T20:00:00+00:00"
    assert m["window_end"] == "2026-04-13T04:30:00+00:00"
    assert m["human_count"] == 1
    assert m["detection_enabled"] is True
    assert [e["camera_entity"] for e in m["events"]] == ["camera.front_door", "camera.back_yard"]
    assert m["events"][0]["human_detected"] is None


def test_save_writes_sidecar_next_to_report(two_events, tmp_path):
    engine = ReportEngine()
    html = engine.generate(date(2026, 4, 12), two_events, "20:45", "06:12")
    ts = datetime(2026, 4, 13, 4, 30, tzinfo=timezone.utc)
    path = Path(engine.save(html, date(2026, 4, 12), str(tmp_path), ts=ts, manifest=_manifest(two_events)))

    sidecar = path.with_suffix(".json")
    assert sidecar.exists()
    assert json.loads(sidecar.read_text())["human_count"] == 1
    assert read_manifest(path)["version"] == 1


def test_save_without_manifest_writes_no_sidecar(two_events, tmp_path):
    engine = ReportEngine()
    html = engine.generate(date(2026, 4, 12), two_events, "20:45", "06:12")
    path = Path(engine.save(html, date(2026, 4, 12), str(tmp_path)))
    assert not path.with_suffix(".json").exists()


def test_sidecar_is_not_listed_as_report(two_events, tmp_path):
    engine = ReportEngine()
    html = engine.generate(date(2026, 4, 12), two_events, "20:45", "06:12")
    engine.save(html, date(2026, 4, 12), str(tmp_path), manifest=_manifest(two_events))
    reports = list_reports(str(tmp_path))
    assert len(reports) == 1
    assert reports[0]["filename"].endswith(".html")


def test_read_manifest_corrupt_returns_none(tmp_path):
    report = tmp_path / "report_06-30-00.html"
    report.write_text("<html/>")
    report.with_suffix(".json").write_text("{broken")
    assert read_manifest(report) is None


def test_load_report_info_none_when_no_reports(tmp_path):
    assert load_report_info(str(tmp_path)) is None


def test_load_report_info_uses_manifest(two_events, tmp_path):
    engine = ReportEngine()
    html = engine.generate(date(2026, 4, 12), two_events, "20:45", "06:12",
                           human_count=1, detection_enabled=True)
    ts = datetime(2026, 4, 13, 4, 30, tzinfo=timezone.utc)
    path = engine.save(html, date(2026, 4, 12), str(tmp_path), ts=ts, manifest=_manifest(two_events))

    info = load_report_info(str(tmp_path))
    assert info == {
        "timestamp": "2026-04-13T04:30:00+00:00",
        "event_count": 2,
        "human_count": 1,
        "detection_enabled": True,
        "report_path": path,
    }


def test_load_report_info_legacy_report_derives_timestamp(tmp_path):
    day = tmp_path / "2026-04-12"
    day.mkdir()
    (day / "report_06-30-00.html").write_text(
        "<strong>Total events:</strong> <span>3</span>"
    )
    info = load_report_info(str(tmp_path))
    assert info["event_count"] == 3
    assert info["human_count"] is None
    assert info["detection_enabled"] is False
    # 06:30 CEST on 2026-04-12
    assert info["timestamp"] == "2026-04-12T06:30:00+02:00"


def test_load_report_info_unparseable_name_has_no_timestamp(tmp_path):
    day = tmp_path / "2026-04-12"
    day.mkdir()
    (day / "report.html").write_text("<html/>")
    assert load_report_info(str(tmp_path))["timestamp"] is None


def test_load_report_info_corrupt_sidecar_falls_back(tmp_path):
    day = tmp_path / "2026-04-12"
    day.mkdir()
    report = day / "report_06-30-00.html"
    report.write_text("<strong>Total events:</strong> <span>3</span>")
    report.with_suffix(".json").write_text("{broken")
    info = load_report_info(str(tmp_path))
    assert info["event_count"] == 3
    assert info["timestamp"] == "2026-04-12T06:30:00+02:00"


def test_load_report_info_legacy_report_after_local_midnight(tmp_path):
    """Day dirs use the UTC date, filenames local time: 23:30 UTC on 04-12
    is 01:30 CEST on 04-13 and was saved as 2026-04-12/report_01-30-00.html."""
    day = tmp_path / "2026-04-12"
    day.mkdir()
    (day / "report_01-30-00.html").write_text("<html/>")
    assert load_report_info(str(tmp_path))["timestamp"] == "2026-04-13T01:30:00+02:00"


def test_load_report_info_non_date_directory_has_no_timestamp(tmp_path):
    day = tmp_path / "old-reports"
    day.mkdir()
    (day / "report_06-30-00.html").write_text("<html/>")
    assert load_report_info(str(tmp_path))["timestamp"] is None
