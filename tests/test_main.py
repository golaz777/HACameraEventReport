import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from src.main import App
from src.presence_guard import PresenceGuard


async def test_setup_connects_ha_and_subscribes_events():
    mock_config = MagicMock()
    mock_config.cameras = []
    mock_config.ha_persistent = False
    mock_config.media_path = "/media/camera_events"
    mock_config.event_cooldown_seconds = 30
    mock_config.retention_days = 30
    mock_config.monitoring.toggle_entity = ""

    mock_ha = AsyncMock()
    mock_ha.connect = AsyncMock()
    mock_ha.subscribe_events = AsyncMock()

    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=AsyncMock()):
        app = App()
        await app.setup()

    mock_ha.connect.assert_called_once()
    mock_ha.subscribe_events.assert_called_once_with(
        "state_changed", app._on_ha_state_changed
    )


async def test_setup_starts_web_server():
    mock_config = MagicMock()
    mock_config.cameras = []
    mock_config.ha_persistent = False
    mock_config.media_path = "/media/camera_events"
    mock_config.event_cooldown_seconds = 30
    mock_config.retention_days = 30
    mock_config.monitoring.toggle_entity = ""

    mock_ha = AsyncMock()
    mock_ha.connect = AsyncMock()
    mock_ha.subscribe_events = AsyncMock()

    mock_web = AsyncMock()
    mock_web.start = AsyncMock()

    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=mock_web) as mock_ws_cls:
        app = App()
        await app.setup()

    mock_ws_cls.assert_called_once_with(mock_config, mock_ha, mock_ws_cls.call_args[0][2])
    mock_web.start.assert_called_once()


async def test_run_stops_web_server_after_listen_ends():
    mock_config = MagicMock()
    mock_config.cameras = []
    mock_config.ha_persistent = False
    mock_config.media_path = "/media/camera_events"
    mock_config.event_cooldown_seconds = 30
    mock_config.retention_days = 30
    mock_config.monitoring.toggle_entity = ""

    mock_ha = AsyncMock()
    mock_ha.connect = AsyncMock()
    mock_ha.subscribe_events = AsyncMock()
    mock_ha.listen = AsyncMock(return_value=None)   # listen returns immediately

    mock_web = AsyncMock()
    mock_web.start = AsyncMock()
    mock_web.stop = AsyncMock()

    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=mock_web):
        app = App()
        await app.run()

    mock_web.stop.assert_called_once()
    mock_ha.close.assert_called_once()


async def test_run_closes_ha_client_on_exception():
    """ha.close() is called even when the listen loop raises an exception."""
    mock_config = MagicMock()
    mock_config.cameras = []
    mock_config.ha_persistent = False
    mock_config.media_path = "/media/camera_events"
    mock_config.event_cooldown_seconds = 30
    mock_config.retention_days = 30
    mock_config.monitoring.toggle_entity = ""

    mock_ha = AsyncMock()
    mock_ha.connect = AsyncMock()
    mock_ha.subscribe_events = AsyncMock()
    mock_ha.listen = AsyncMock(side_effect=RuntimeError("connection lost"))

    mock_web = AsyncMock()

    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=mock_web):
        app = App()
        with pytest.raises(RuntimeError):
            await app.run()

    mock_ha.close.assert_called_once()
    mock_web.stop.assert_called_once()


def _base_mock_config():
    mock_config = MagicMock()
    mock_config.cameras = []
    mock_config.ha_persistent = False
    mock_config.media_path = "/media/camera_events"
    mock_config.event_cooldown_seconds = 30
    mock_config.retention_days = 30
    mock_config.monitoring.toggle_entity = ""   # feature disabled by default
    return mock_config


async def test_setup_creates_presence_guard_when_toggle_entity_configured():
    mock_config = _base_mock_config()
    mock_config.monitoring.toggle_entity = "input_boolean.away_mode"

    mock_ha = AsyncMock()
    mock_ha.connect = AsyncMock()
    mock_ha.get_state = AsyncMock(return_value={"state": "off"})
    mock_ha.subscribe_events = AsyncMock()

    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=AsyncMock()):
        app = App()
        await app.setup()

    assert app.presence_guard is not None
    assert isinstance(app.presence_guard, PresenceGuard)


async def test_setup_skips_presence_guard_when_no_toggle_entity():
    mock_config = _base_mock_config()
    mock_config.monitoring.toggle_entity = ""

    mock_ha = AsyncMock()
    mock_ha.connect = AsyncMock()
    mock_ha.subscribe_events = AsyncMock()

    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=AsyncMock()):
        app = App()
        await app.setup()

    assert app.presence_guard is None


async def test_setup_seeds_away_start_when_toggle_already_on():
    mock_config = _base_mock_config()
    mock_config.monitoring.toggle_entity = "input_boolean.away_mode"

    mock_ha = AsyncMock()
    mock_ha.connect = AsyncMock()
    mock_ha.get_state = AsyncMock(return_value={"state": "on"})
    mock_ha.subscribe_events = AsyncMock()

    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=AsyncMock()):
        app = App()
        await app.setup()

    assert app._away_start is not None


async def test_on_ha_state_changed_routes_toggle_to_presence_guard():
    mock_config = _base_mock_config()
    mock_config.monitoring.toggle_entity = "input_boolean.away_mode"

    mock_ha = AsyncMock()
    mock_ha.connect = AsyncMock()
    mock_ha.get_state = AsyncMock(return_value={"state": "off"})
    mock_ha.subscribe_events = AsyncMock()

    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=AsyncMock()):
        app = App()
        await app.setup()

    await app._on_ha_state_changed({
        "event_type": "state_changed",
        "data": {
            "entity_id": "input_boolean.away_mode",
            "new_state": {"state": "on"},
        },
    })

    assert app.presence_guard.is_away is True


async def test_on_away_sets_away_start():
    app = App()
    app.config = MagicMock()
    assert app._away_start is None
    await app._on_away()
    assert app._away_start is not None


async def test_on_home_generates_report_and_sends_notifications():
    app = App()
    app.config = MagicMock()
    app.config.media_path = "/media/camera_events"

    now = datetime.now(tz=timezone.utc)
    app._away_start = now

    mock_store = MagicMock()
    mock_store.read = MagicMock(return_value=[])
    app.store = mock_store

    mock_notifier = AsyncMock()
    app.notifier = mock_notifier

    with patch("src.main.ReportEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.generate = MagicMock(return_value="<html>")
        mock_engine.save = MagicMock(return_value="/media/camera_events/2026-04-12/report.html")
        mock_engine_cls.return_value = mock_engine

        await app._on_home()

    mock_notifier.send_ha_notification.assert_called_once()
    mock_notifier.send_email.assert_called_once()


async def test_on_home_with_no_away_start_does_not_crash():
    app = App()
    app.config = MagicMock()
    app.config.media_path = "/media/camera_events"
    app._away_start = None   # toggle was already on when addon started; seeded to None

    mock_store = MagicMock()
    mock_store.read = MagicMock(return_value=[])
    app.store = mock_store

    mock_notifier = AsyncMock()
    app.notifier = mock_notifier

    with patch("src.main.ReportEngine") as mock_engine_cls:
        mock_engine = MagicMock()
        mock_engine.generate = MagicMock(return_value="<html>")
        mock_engine.save = MagicMock(return_value="/media/report.html")
        mock_engine_cls.return_value = mock_engine

        await app._on_home()   # must not raise

    mock_notifier.send_ha_notification.assert_called_once()


def _detection_app(events, detector=None):
    """An App wired just enough to exercise _on_home's detection path."""
    app = App()
    app.config = MagicMock()
    app.config.media_path = "/media/camera_events"
    app._away_start = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)

    app.store = MagicMock()
    app.store.read = MagicMock(return_value=events)
    app.store.update_detections = MagicMock()
    app.notifier = AsyncMock()
    app.detector = detector
    return app


def _snap_event(ts, entity="camera.front"):
    from src.store import MotionEvent

    return MotionEvent(
        timestamp=ts,
        camera_name=entity.split(".")[-1],
        camera_entity=entity,
        screenshot_path="/snap.jpg",
    )


def _patched_engine():
    engine = MagicMock()
    engine.generate = MagicMock(return_value="<html>")
    engine.save = MagicMock(return_value="/media/camera_events/report.html")
    return engine


async def test_on_home_analyses_snapshots_and_reports_humans():
    ts = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)
    event = _snap_event(ts)

    detector = AsyncMock()
    detector.available = True

    async def analyze(events):
        events[0].human_detected = True
        events[0].human_confidence = 0.93
        return 1

    detector.analyze = AsyncMock(side_effect=analyze)
    app = _detection_app([event], detector)

    engine = _patched_engine()
    with patch("src.main.ReportEngine", return_value=engine):
        await app._on_home()

    detector.analyze.assert_awaited_once()
    assert engine.generate.call_args.kwargs["human_count"] == 1
    assert engine.generate.call_args.kwargs["detection_enabled"] is True
    assert app.notifier.send_ha_notification.call_args.kwargs["human_count"] == 1
    app.store.update_detections.assert_called_once()


async def test_on_home_persists_verdicts_per_day():
    """An away window can span days, and each day has its own event log."""
    day1 = datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 2, 1, 0, tzinfo=timezone.utc)
    events = [_snap_event(day1), _snap_event(day2)]

    detector = AsyncMock()
    detector.available = True
    detector.analyze = AsyncMock(return_value=0)
    app = _detection_app(events, detector)
    # store.read is called once per day in the window; return everything once.
    app.store.read = MagicMock(side_effect=[events, []])

    with patch("src.main.ReportEngine", return_value=_patched_engine()):
        await app._on_home()

    persisted_days = [c.args[0] for c in app.store.update_detections.call_args_list]
    assert sorted(persisted_days) == [date(2026, 10, 1), date(2026, 10, 2)]


async def test_on_home_skips_detection_when_disabled():
    app = _detection_app([_snap_event(datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc))])

    engine = _patched_engine()
    with patch("src.main.ReportEngine", return_value=engine):
        await app._on_home()

    assert engine.generate.call_args.kwargs["human_count"] == 0
    assert engine.generate.call_args.kwargs["detection_enabled"] is False
    app.store.update_detections.assert_not_called()
    app.notifier.send_ha_notification.assert_awaited_once()


async def test_on_home_still_reports_when_detection_raises():
    """A detector failure must never cost us the report."""
    detector = AsyncMock()
    detector.available = True
    detector.analyze = AsyncMock(side_effect=RuntimeError("onnx exploded"))
    app = _detection_app(
        [_snap_event(datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc))], detector
    )

    engine = _patched_engine()
    with patch("src.main.ReportEngine", return_value=engine):
        await app._on_home()   # must not raise

    assert engine.generate.call_args.kwargs["human_count"] == 0
    app.notifier.send_ha_notification.assert_awaited_once()
    app.store.update_detections.assert_not_called()


async def test_on_home_reports_when_persisting_verdicts_fails():
    """A read-only media volume must not block the report either."""
    ts = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)
    detector = AsyncMock()
    detector.available = True

    async def analyze(events):
        events[0].human_detected = True
        return 1

    detector.analyze = AsyncMock(side_effect=analyze)
    app = _detection_app([_snap_event(ts)], detector)
    app.store.update_detections = MagicMock(side_effect=OSError("read-only fs"))

    engine = _patched_engine()
    with patch("src.main.ReportEngine", return_value=engine):
        await app._on_home()   # must not raise

    assert engine.generate.call_args.kwargs["human_count"] == 1


async def test_setup_creates_detector_when_enabled():
    mock_config = MagicMock()
    mock_config.cameras = []
    mock_config.media_path = "/media/camera_events"
    mock_config.retention_days = None
    mock_config.monitoring.toggle_entity = ""
    mock_config.detection.enabled = True
    mock_config.detection.model_path = "/app/models/ssd_mobilenet_v1_12.onnx"
    mock_config.detection.confidence = 0.4

    with patch("src.main.HAClient", return_value=AsyncMock()), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=AsyncMock()), \
         patch("src.main.EventStore"):
        app = App()
        await app.setup()

    assert app.detector is not None


async def test_setup_skips_detector_when_disabled():
    mock_config = MagicMock()
    mock_config.cameras = []
    mock_config.media_path = "/media/camera_events"
    mock_config.retention_days = None
    mock_config.monitoring.toggle_entity = ""
    mock_config.detection.enabled = False

    with patch("src.main.HAClient", return_value=AsyncMock()), \
         patch("src.main.load_config", return_value=mock_config), \
         patch("src.main.WebServer", return_value=AsyncMock()), \
         patch("src.main.EventStore"):
        app = App()
        await app.setup()

    assert app.detector is None


from pathlib import Path
from src.session_state import SessionState


def _toggle_config(tmp_path):
    cfg = _base_mock_config()
    cfg.media_path = str(tmp_path)
    cfg.monitoring.toggle_entity = "input_boolean.away_mode"
    cfg.detection.enabled = False
    return cfg


async def _setup_with_toggle(tmp_path, toggle_state):
    mock_ha = AsyncMock()
    mock_ha.get_state = AsyncMock(return_value={"state": toggle_state})
    with patch("src.main.HAClient", return_value=mock_ha), \
         patch("src.main.load_config", return_value=_toggle_config(tmp_path)), \
         patch("src.main.WebServer", return_value=AsyncMock()):
        app = App()
        await app.setup()
    return app


async def test_setup_restores_persisted_away_start(tmp_path):
    start = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
    SessionState(tmp_path / "session.json").save(start)

    app = await _setup_with_toggle(tmp_path, "on")

    assert app._away_start == start


async def test_setup_persists_away_start_when_no_file(tmp_path):
    app = await _setup_with_toggle(tmp_path, "on")

    assert app._away_start is not None
    assert SessionState(tmp_path / "session.json").load() == app._away_start


async def test_setup_clears_stale_session_when_toggle_off(tmp_path):
    SessionState(tmp_path / "session.json").save(
        datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
    )

    await _setup_with_toggle(tmp_path, "off")

    assert not (tmp_path / "session.json").exists()


async def test_setup_keeps_session_when_toggle_unavailable(tmp_path):
    start = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
    SessionState(tmp_path / "session.json").save(start)

    app = await _setup_with_toggle(tmp_path, "unavailable")
    assert SessionState(tmp_path / "session.json").load() == start

    # Toggle comes back "on": the session resumes from the persisted start.
    await app.presence_guard.handle_toggle_change("on")
    assert app._away_start == start


async def test_on_away_persists_start(tmp_path):
    app = App()
    app.config = MagicMock()
    app.session_state = SessionState(tmp_path / "session.json")

    await app._on_away()

    assert app.session_state.load() == app._away_start


async def test_on_home_clears_session_state(tmp_path):
    app = _detection_app([])
    app.session_state = SessionState(tmp_path / "session.json")
    app.session_state.save(app._away_start)

    with patch("src.main.ReportEngine", return_value=_patched_engine()):
        await app._on_home()

    assert app.session_state.load() is None


def test_session_events_spans_days_and_filters_window():
    start = datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc)
    before = _snap_event(datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc))
    late = _snap_event(datetime(2026, 10, 2, 1, 0, tzinfo=timezone.utc))
    early = _snap_event(datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc))

    app = App()
    app.store = MagicMock()
    app.store.read = MagicMock(
        side_effect=lambda d: {
            date(2026, 10, 1): [before, early],
            date(2026, 10, 2): [late],
        }[d]
    )

    assert app._session_events(start, end) == [early, late]


async def test_on_home_passes_manifest_to_save():
    ts = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)
    event = _snap_event(ts)
    app = _detection_app([event])
    # Only the event's own day has it; the window runs until the real "now".
    app.store.read = MagicMock(side_effect=lambda d: [event] if d == ts.date() else [])

    engine = _patched_engine()
    with patch("src.main.ReportEngine", return_value=engine):
        await app._on_home()

    manifest = engine.save.call_args.kwargs["manifest"]
    assert manifest["window_start"] == app._away_start.isoformat()
    assert len(manifest["events"]) == 1


async def test_setup_publishes_initial_state(tmp_path):
    start = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
    SessionState(tmp_path / "session.json").save(start)
    publisher = AsyncMock()

    with patch("src.main.HAPublisher", return_value=publisher):
        app = await _setup_with_toggle(tmp_path, "on")

    publisher.publish_initial.assert_awaited_once()
    args = publisher.publish_initial.call_args.args
    assert args[0] is True
    assert args[1] == start
    assert args[2] == []      # store is empty
    assert args[3] is None    # no reports yet
    assert app.handler._publisher is publisher


async def test_on_away_notifies_publisher():
    app = App()
    app.config = MagicMock()
    app.publisher = AsyncMock()
    await app._on_away()
    app.publisher.on_session_start.assert_awaited_once_with(app._away_start)


async def test_on_home_notifies_publisher():
    ts = datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc)
    event = _snap_event(ts)
    app = _detection_app([event])
    app.store.read = MagicMock(side_effect=lambda d: [event] if d == ts.date() else [])
    app.publisher = AsyncMock()

    with patch("src.main.ReportEngine", return_value=_patched_engine()):
        await app._on_home()

    kwargs = app.publisher.on_report.call_args.kwargs
    assert kwargs["report_path"] == "/media/camera_events/report.html"
    assert kwargs["event_count"] == 1
    assert kwargs["human_count"] == 0
