import pytest
from datetime import datetime, timezone
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

    mock_ws_cls.assert_called_once_with(mock_config, mock_ha)
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
