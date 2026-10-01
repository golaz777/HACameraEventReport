import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from src.ha_client import HAClient


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_session(mock_ws):
    session = AsyncMock()
    session.ws_connect = AsyncMock(return_value=mock_ws)
    session.get = AsyncMock()
    session.close = AsyncMock()
    return session


async def test_connect_sends_auth_token(mock_ws, mock_session):
    mock_ws.receive_json = AsyncMock(
        side_effect=[
            {"type": "auth_required"},
            {"type": "auth_ok", "ha_version": "2026.4.1"},
        ]
    )

    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "test_token"}):
        client = HAClient()
        await client.connect()

    mock_ws.send_json.assert_called_once_with(
        {"type": "auth", "access_token": "test_token"}
    )


async def test_dispatch_resolves_pending_future(mock_ws, mock_session):
    states = [
        {"entity_id": "sun.sun", "state": "below_horizon"},
        {"entity_id": "binary_sensor.front_door", "state": "off"},
    ]
    mock_ws.receive_json = AsyncMock(
        side_effect=[{"type": "auth_required"}, {"type": "auth_ok"}]
    )

    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = HAClient()
        await client.connect()
        fut = asyncio.get_event_loop().create_future()
        client._pending[1] = fut
        await client._dispatch(
            {"type": "result", "id": 1, "success": True, "result": states}
        )
        result = await fut

    assert result == states


async def test_dispatch_fires_event_callback(mock_ws, mock_session):
    mock_ws.receive_json = AsyncMock(
        side_effect=[{"type": "auth_required"}, {"type": "auth_ok"}]
    )
    received = []

    async def callback(event):
        received.append(event)

    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = HAClient()
        await client.connect()
        client._event_callbacks.append(("state_changed", callback))
        await client._dispatch(
            {
                "type": "event",
                "event": {
                    "event_type": "state_changed",
                    "data": {"entity_id": "binary_sensor.front_door"},
                },
            }
        )

    assert len(received) == 1
    assert received[0]["event_type"] == "state_changed"


async def test_camera_snapshot_saves_file(mock_ws, mock_session, tmp_path):
    mock_ws.receive_json = AsyncMock(
        side_effect=[{"type": "auth_required"}, {"type": "auth_ok"}]
    )
    fake_image = b"\xff\xd8\xff" + b"\x00" * 50

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=fake_image)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = AsyncMock(return_value=mock_response)

    filepath = str(tmp_path / "snap" / "image.jpg")

    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = HAClient()
        await client.connect()
        result = await client.camera_snapshot("camera.front_door", filepath)

    assert result is True
    headers = mock_session.get.call_args[1].get("headers", {})
    assert headers.get("Authorization") == "Bearer tok"
    from pathlib import Path
    assert Path(filepath).read_bytes() == fake_image


async def test_camera_snapshot_retries_on_500(mock_ws, mock_session, tmp_path):
    """On HTTP 500, snapshot retries once and succeeds on the second attempt."""
    mock_ws.receive_json = AsyncMock(
        side_effect=[{"type": "auth_required"}, {"type": "auth_ok"}]
    )
    fake_image = b"\xff\xd8\xff" + b"\x00" * 50

    bad_resp = AsyncMock()
    bad_resp.status = 500
    bad_resp.__aenter__ = AsyncMock(return_value=bad_resp)
    bad_resp.__aexit__ = AsyncMock(return_value=False)

    good_resp = AsyncMock()
    good_resp.status = 200
    good_resp.read = AsyncMock(return_value=fake_image)
    good_resp.__aenter__ = AsyncMock(return_value=good_resp)
    good_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session.get = AsyncMock(side_effect=[bad_resp, good_resp])
    filepath = str(tmp_path / "snap" / "image.jpg")

    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}), \
         patch("src.ha_client.asyncio.sleep", new=AsyncMock()):
        client = HAClient()
        await client.connect()
        result = await client.camera_snapshot("camera.front_door", filepath)

    assert result is True
    assert mock_session.get.call_count == 2
    from pathlib import Path
    assert Path(filepath).read_bytes() == fake_image


async def test_camera_snapshot_returns_false_after_two_500s(mock_ws, mock_session, tmp_path):
    """Returns False when both attempts return HTTP 500."""
    mock_ws.receive_json = AsyncMock(
        side_effect=[{"type": "auth_required"}, {"type": "auth_ok"}]
    )

    def make_500():
        r = AsyncMock()
        r.status = 500
        r.__aenter__ = AsyncMock(return_value=r)
        r.__aexit__ = AsyncMock(return_value=False)
        return r

    mock_session.get = AsyncMock(side_effect=[make_500(), make_500()])
    filepath = str(tmp_path / "snap" / "image.jpg")

    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}), \
         patch("src.ha_client.asyncio.sleep", new=AsyncMock()):
        client = HAClient()
        await client.connect()
        result = await client.camera_snapshot("camera.front_door", filepath)

    assert result is False
    assert mock_session.get.call_count == 2


async def test_connected_false_before_connect():
    client = HAClient()
    assert client.connected is False


async def test_connected_true_after_connect(mock_ws, mock_session):
    mock_ws.closed = False
    mock_ws.receive_json = AsyncMock(
        side_effect=[
            {"type": "auth_required"},
            {"type": "auth_ok", "ha_version": "2026.4.1"},
        ]
    )
    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = HAClient()
        await client.connect()
    assert client.connected is True


async def test_connected_false_when_ws_closed(mock_ws, mock_session):
    mock_ws.closed = True
    mock_ws.receive_json = AsyncMock(
        side_effect=[
            {"type": "auth_required"},
            {"type": "auth_ok", "ha_version": "2026.4.1"},
        ]
    )
    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = HAClient()
        await client.connect()
    assert client.connected is False


def _resp(status):
    r = AsyncMock()
    r.status = status
    r.__aenter__ = AsyncMock(return_value=r)
    r.__aexit__ = AsyncMock(return_value=False)
    return r


async def _connected_client(mock_ws, mock_session):
    mock_ws.receive_json = AsyncMock(
        side_effect=[{"type": "auth_required"}, {"type": "auth_ok"}]
    )
    client = HAClient()
    await client.connect()
    return client


async def test_set_state_posts_state_and_attributes(mock_ws, mock_session):
    mock_session.post = AsyncMock(return_value=_resp(201))
    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = await _connected_client(mock_ws, mock_session)
        ok = await client.set_state("sensor.x", "5", {"friendly_name": "X"})

    assert ok is True
    args, kwargs = mock_session.post.call_args
    assert args[0] == "http://supervisor/core/api/states/sensor.x"
    assert kwargs["headers"]["Authorization"] == "Bearer tok"
    assert kwargs["json"] == {"state": "5", "attributes": {"friendly_name": "X"}}


async def test_set_state_returns_false_on_http_error(mock_ws, mock_session):
    mock_session.post = AsyncMock(return_value=_resp(401))
    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = await _connected_client(mock_ws, mock_session)
        assert await client.set_state("sensor.x", "5", {}) is False


async def test_set_state_returns_false_on_connection_error(mock_ws, mock_session):
    mock_session.post = AsyncMock(side_effect=OSError("refused"))
    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = await _connected_client(mock_ws, mock_session)
        assert await client.set_state("sensor.x", "5", {}) is False


async def test_fire_event_sends_websocket_message(mock_ws, mock_session):
    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = await _connected_client(mock_ws, mock_session)
        await client.fire_event("camera_event_report_motion", {"camera_name": "Front"})

    msg = mock_ws.send_json.call_args[0][0]
    assert msg["type"] == "fire_event"
    assert msg["event_type"] == "camera_event_report_motion"
    assert msg["event_data"] == {"camera_name": "Front"}
    assert isinstance(msg["id"], int)


async def test_set_state_uses_short_timeout(mock_ws, mock_session):
    """A hung HA REST API must not stall event dispatch for the 5 min default."""
    mock_session.post = AsyncMock(return_value=_resp(200))
    with patch("src.ha_client.aiohttp.ClientSession", return_value=mock_session), \
         patch.dict("os.environ", {"SUPERVISOR_TOKEN": "tok"}):
        client = await _connected_client(mock_ws, mock_session)
        await client.set_state("sensor.x", "1", {})

    assert mock_session.post.call_args.kwargs["timeout"].total <= 10
