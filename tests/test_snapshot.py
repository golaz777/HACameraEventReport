import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from src.snapshot import build_snapshot_path, take_snapshot
from src.config import CameraConfig


@pytest.fixture
def camera():
    return CameraConfig(
        entity_id="camera.front_door",
        motion_entity="binary_sensor.front_door_motion",
        name="Front Door",
    )


def test_build_snapshot_path(camera):
    ts = datetime(2026, 4, 12, 23, 14, 2, tzinfo=timezone.utc)
    path = build_snapshot_path("/media/camera_events", camera, ts)
    assert path == "/media/camera_events/2026-04-12/front_door_23-14-02.jpg"


def test_build_snapshot_path_slugifies_spaces():
    cam = CameraConfig(
        entity_id="camera.back_yard",
        motion_entity="binary_sensor.back_yard_motion",
        name="Back Yard Camera",
    )
    ts = datetime(2026, 4, 12, 1, 37, 55, tzinfo=timezone.utc)
    path = build_snapshot_path("/media/camera_events", cam, ts)
    assert path == "/media/camera_events/2026-04-12/back_yard_camera_01-37-55.jpg"


async def test_take_snapshot_calls_ha_proxy(camera, tmp_path):
    mock_ha = AsyncMock()
    mock_ha.camera_snapshot = AsyncMock(return_value=True)
    ts = datetime(2026, 4, 12, 23, 14, 2, tzinfo=timezone.utc)

    result = await take_snapshot(mock_ha, camera, ts, str(tmp_path))

    expected_path = f"{tmp_path}/2026-04-12/front_door_23-14-02.jpg"
    mock_ha.camera_snapshot.assert_called_once_with("camera.front_door", expected_path)
    assert result == expected_path


async def test_take_snapshot_returns_none_when_ha_fails(camera, tmp_path):
    mock_ha = AsyncMock()
    mock_ha.camera_snapshot = AsyncMock(return_value=False)
    ts = datetime(2026, 4, 12, 23, 14, 2, tzinfo=timezone.utc)

    result = await take_snapshot(mock_ha, camera, ts, str(tmp_path))

    assert result is None
