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


def test_list_dates_returns_sorted_dates(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    dates = [date(2026, 4, 10), date(2026, 4, 12), date(2026, 4, 11)]

    for d in dates:
        store.append(
            d,
            MotionEvent(
                timestamp=datetime(d.year, d.month, d.day, 10, 0, 0, tzinfo=timezone.utc),
                camera_name="Cam",
                camera_entity="camera.cam",
                screenshot_path=None,
            ),
        )

    result = store.list_dates()
    assert result == sorted(dates)


def test_list_dates_empty(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    assert store.list_dates() == []


def test_read_range_single_date(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    d = date(2026, 4, 12)
    event = MotionEvent(
        timestamp=datetime(2026, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
        camera_name="Cam",
        camera_entity="camera.cam",
        screenshot_path=None,
    )
    store.append(d, event)

    result = store.read_range(d, d)
    assert len(result) == 1
    assert d in result
    assert len(result[d]) == 1
    assert result[d][0].camera_name == "Cam"


def test_read_range_multiple_dates(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    start = date(2026, 4, 10)
    end = date(2026, 4, 12)

    for i in range(3):
        d = start + timedelta(days=i)
        store.append(
            d,
            MotionEvent(
                timestamp=datetime(d.year, d.month, d.day, 10, 0, 0, tzinfo=timezone.utc),
                camera_name=f"Cam{i}",
                camera_entity=f"camera.cam{i}",
                screenshot_path=None,
            ),
        )

    result = store.read_range(start, end)
    assert len(result) == 3
    assert all(d in result for d in [start, start + timedelta(days=1), end])


def test_read_range_includes_zero_days(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    start = date(2026, 4, 10)
    end = date(2026, 4, 12)

    # Only add event on start date
    store.append(
        start,
        MotionEvent(
            timestamp=datetime(start.year, start.month, start.day, 10, 0, 0, tzinfo=timezone.utc),
            camera_name="Cam",
            camera_entity="camera.cam",
            screenshot_path=None,
        ),
    )

    result = store.read_range(start, end)
    # Should include all dates, with empty lists for dates with no events
    assert len(result) == 3
    assert len(result[start]) == 1
    assert len(result[start + timedelta(days=1)]) == 0
    assert len(result[end]) == 0


def test_read_range_empty(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    result = store.read_range(date(2026, 4, 10), date(2026, 4, 12))
    assert len(result) == 3
    assert all(len(events) == 0 for events in result.values())


def _event(ts, entity="camera.front", path="/snap.jpg", detected=None, conf=None):
    return MotionEvent(
        timestamp=ts,
        camera_name=entity.split(".")[-1],
        camera_entity=entity,
        screenshot_path=path,
        human_detected=detected,
        human_confidence=conf,
    )


def test_detection_verdicts_round_trip(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 10, 1)
    ts = datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)

    store.append(night, _event(ts, detected=True, conf=0.91))
    store.append(night, _event(ts.replace(minute=5), detected=False, conf=0.02))

    first, second = store.read(night)
    assert (first.human_detected, first.human_confidence) == (True, 0.91)
    assert (second.human_detected, second.human_confidence) == (False, 0.02)


def test_unanalysed_event_round_trips_as_none(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 10, 1)
    store.append(night, _event(datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)))

    event = store.read(night)[0]
    assert event.human_detected is None
    assert event.human_confidence is None


def test_read_accepts_logs_written_before_detection_existed(tmp_path):
    """Logs from older versions have no detection keys and must still load."""
    night = date(2026, 10, 1)
    day_dir = tmp_path / night.isoformat()
    day_dir.mkdir()
    (day_dir / "events.json").write_text(
        '{"timestamp": "2026-10-01T22:00:00+00:00", "camera_name": "Front Door", '
        '"camera_entity": "camera.front_door", "screenshot_path": "/a.jpg"}\n',
        encoding="utf-8",
    )

    events = EventStore(base_path=str(tmp_path)).read(night)

    assert len(events) == 1
    assert events[0].camera_name == "Front Door"
    assert events[0].human_detected is None


def test_update_detections_persists_verdicts(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 10, 1)
    t1 = datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 1, 22, 30, tzinfo=timezone.utc)
    store.append(night, _event(t1, entity="camera.front"))
    store.append(night, _event(t2, entity="camera.back"))

    analysed = [
        _event(t1, entity="camera.front", detected=True, conf=0.88),
        _event(t2, entity="camera.back", detected=False, conf=0.01),
    ]
    store.update_detections(night, analysed)

    front, back = store.read(night)
    assert (front.human_detected, front.human_confidence) == (True, 0.88)
    assert (back.human_detected, back.human_confidence) == (False, 0.01)


def test_update_detections_leaves_unmatched_records_untouched(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 10, 1)
    t1 = datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc)
    store.append(night, _event(t1, entity="camera.front"))
    store.append(night, _event(t2, entity="camera.back"))

    store.update_detections(
        night, [_event(t1, entity="camera.front", detected=True, conf=0.7)]
    )

    front, back = store.read(night)
    assert front.human_detected is True
    assert back.human_detected is None
    assert back.camera_entity == "camera.back"


def test_update_detections_matches_on_camera_not_just_time(tmp_path):
    """Two cameras can fire in the same second — verdicts must not cross over."""
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 10, 1)
    ts = datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)
    store.append(night, _event(ts, entity="camera.front"))
    store.append(night, _event(ts, entity="camera.back"))

    store.update_detections(
        night, [_event(ts, entity="camera.back", detected=True, conf=0.9)]
    )

    by_entity = {e.camera_entity: e for e in store.read(night)}
    assert by_entity["camera.back"].human_detected is True
    assert by_entity["camera.front"].human_detected is None


def test_update_detections_is_noop_without_log(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 10, 1)
    ts = datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)

    store.update_detections(night, [_event(ts, detected=True, conf=0.5)])

    assert store.read(night) == []


def test_update_detections_leaves_no_temp_file_behind(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    night = date(2026, 10, 1)
    ts = datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)
    store.append(night, _event(ts))

    store.update_detections(night, [_event(ts, detected=True, conf=0.6)])

    day_dir = tmp_path / night.isoformat()
    assert sorted(p.name for p in day_dir.iterdir()) == ["events.json"]


def test_purge_old_keeps_directories_from_keep_from(tmp_path):
    store = EventStore(base_path=str(tmp_path))
    today = date(2026, 4, 22)
    session_day = today - timedelta(days=40)
    older = today - timedelta(days=41)
    for d in (session_day, older):
        (tmp_path / d.isoformat()).mkdir()

    with patch("src.store.date") as mock_date:
        mock_date.today.return_value = today
        mock_date.fromisoformat = date.fromisoformat
        store.purge_old(retention_days=30, keep_from=session_day)

    assert (tmp_path / session_day.isoformat()).exists()
    assert not (tmp_path / older.isoformat()).exists()
