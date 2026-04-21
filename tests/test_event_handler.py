import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from src.event_handler import EventHandler
from src.config import CameraConfig, Config, EmailConfig
from src.presence_guard import PresenceGuard


@pytest.fixture
def camera():
    return CameraConfig(
        entity_id="camera.front_door",
        motion_entity="binary_sensor.front_door_motion",
        name="Front Door",
    )


@pytest.fixture
def config(camera, tmp_path):
    return Config(
        cameras=[camera],
        email=EmailConfig(
            enabled=False,
            smtp_host="",
            smtp_port=587,
            smtp_user="",
            smtp_password="",
            recipient="",
            sender="",
        ),
        ha_persistent=False,
        event_cooldown_seconds=30,
        media_path=str(tmp_path),
    )


async def test_on_motion_records_event_when_away(camera, config):
    mock_ha = AsyncMock()
    mock_ha.camera_snapshot = AsyncMock(return_value=True)
    mock_store = MagicMock()

    presence_guard = PresenceGuard()
    presence_guard.update_state("on")  # is_away = True

    handler = EventHandler(config, mock_ha, mock_store, presence_guard)
    await handler.on_motion(camera)

    assert mock_store.append.called
    night, event = mock_store.append.call_args[0]
    assert event.camera_entity == "camera.front_door"
    assert event.camera_name == "Front Door"


async def test_on_motion_ignored_when_not_away(camera, config):
    mock_ha = AsyncMock()
    mock_store = MagicMock()

    presence_guard = PresenceGuard()
    # is_away defaults to False

    handler = EventHandler(config, mock_ha, mock_store, presence_guard)
    await handler.on_motion(camera)

    assert not mock_store.append.called


async def test_cooldown_suppresses_second_trigger(camera, config):
    config.event_cooldown_seconds = 30
    mock_ha = AsyncMock()
    mock_ha.camera_snapshot = AsyncMock(return_value=True)
    mock_store = MagicMock()

    presence_guard = PresenceGuard()
    presence_guard.update_state("on")

    handler = EventHandler(config, mock_ha, mock_store, presence_guard)
    await handler.on_motion(camera)
    await handler.on_motion(camera)  # within cooldown window

    assert mock_store.append.call_count == 1


async def test_snapshot_failure_still_records_event(camera, config):
    mock_ha = AsyncMock()
    mock_ha.camera_snapshot = AsyncMock(return_value=False)
    mock_store = MagicMock()

    presence_guard = PresenceGuard()
    presence_guard.update_state("on")

    handler = EventHandler(config, mock_ha, mock_store, presence_guard)
    await handler.on_motion(camera)

    assert mock_store.append.called
    _, event = mock_store.append.call_args[0]
    assert event.screenshot_path is None


async def test_on_ha_state_changed_triggers_motion(camera, config):
    mock_ha = AsyncMock()
    mock_ha.camera_snapshot = AsyncMock(return_value=True)
    mock_store = MagicMock()

    presence_guard = PresenceGuard()
    presence_guard.update_state("on")

    handler = EventHandler(config, mock_ha, mock_store, presence_guard)
    await handler.on_ha_state_changed({
        "event_type": "state_changed",
        "data": {
            "entity_id": "binary_sensor.front_door_motion",
            "new_state": {"state": "on"},
        },
    })

    assert mock_store.append.called


async def test_on_motion_blocked_with_no_presence_guard(camera, config):
    """Without presence_guard, monitoring is never active."""
    mock_ha = AsyncMock()
    mock_store = MagicMock()

    handler = EventHandler(config, mock_ha, mock_store)  # no presence_guard
    await handler.on_motion(camera)

    assert not mock_store.append.called


async def test_on_ha_state_changed_ignores_off_state(camera, config):
    mock_ha = AsyncMock()
    mock_store = MagicMock()

    presence_guard = PresenceGuard()
    presence_guard.update_state("on")

    handler = EventHandler(config, mock_ha, mock_store, presence_guard)
    await handler.on_ha_state_changed({
        "event_type": "state_changed",
        "data": {
            "entity_id": "binary_sensor.front_door_motion",
            "new_state": {"state": "off"},
        },
    })

    assert not mock_store.append.called
