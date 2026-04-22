import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from src.store import EventStore, MotionEvent


def test_append_and_read_events(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 4, 12)
    event = MotionEvent(
        timestamp=datetime(2026, 4, 12, 23, 14, 2, tzinfo=timezone.utc),
        camera_name="Front Door",
        camera_entity="camera.front_door",
        screenshot_path="/media/onvif_events/2026-04-12/front_door_23-14-02.jpg",
    )

    store.append(night, event)
    events = store.read(night)

    assert len(events) == 1
    assert events[0].camera_name == "Front Door"
    assert events[0].screenshot_path == "/media/onvif_events/2026-04-12/front_door_23-14-02.jpg"
    assert events[0].timestamp == datetime(2026, 4, 12, 23, 14, 2, tzinfo=timezone.utc)


def test_append_multiple_events(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 4, 12)

    for i in range(3):
        store.append(
            night,
            MotionEvent(
                timestamp=datetime(2026, 4, 12, 23, i, 0, tzinfo=timezone.utc),
                camera_name="Cam",
                camera_entity="camera.cam",
                screenshot_path=f"/media/onvif_events/2026-04-12/cam_23-0{i}-00.jpg",
            ),
        )

    assert len(store.read(night)) == 3


def test_read_empty_returns_empty_list(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    assert store.read(date(2026, 4, 12)) == []


def test_purge_old_removes_expired_directories(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    today = date(2026, 4, 22)
    old_day = today - timedelta(days=31)
    recent_day = today - timedelta(days=5)

    # Create directories with events
    for d in (old_day, recent_day):
        store.append(
            d,
            MotionEvent(
                timestamp=datetime(d.year, d.month, d.day, 10, 0, 0, tzinfo=timezone.utc),
                camera_name="Cam",
                camera_entity="camera.cam",
                screenshot_path=None,
            ),
        )

    with patch("src.store.date") as mock_date:
        mock_date.today.return_value = today
        mock_date.fromisoformat = date.fromisoformat
        store.purge_old(retention_days=30)

    assert not (tmp_path / old_day.isoformat()).exists()
    assert (tmp_path / recent_day.isoformat()).exists()


def test_purge_old_skips_non_date_directories(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    misc_dir = tmp_path / "not-a-date"
    misc_dir.mkdir()

    with patch("src.store.date") as mock_date:
        mock_date.today.return_value = date(2026, 4, 22)
        mock_date.fromisoformat = date.fromisoformat
        store.purge_old(retention_days=30)

    assert misc_dir.exists()


def test_purge_old_noop_when_base_missing(tmp_path):
    store = EventStore(base_path=str(tmp_path / "nonexistent"))
    store.purge_old(retention_days=30)  # should not raise


def test_screenshot_path_can_be_none(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 4, 12)
    store.append(
        night,
        MotionEvent(
            timestamp=datetime(2026, 4, 12, 23, 0, 0, tzinfo=timezone.utc),
            camera_name="Cam",
            camera_entity="camera.cam",
            screenshot_path=None,
        ),
    )
    events = store.read(night)
    assert events[0].screenshot_path is None
