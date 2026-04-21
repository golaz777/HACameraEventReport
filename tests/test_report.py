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
