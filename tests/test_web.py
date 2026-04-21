from __future__ import annotations
import asyncio
import base64
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from aiohttp.test_utils import TestClient, TestServer

from src.config import CameraConfig
from src.web import WebServer


def _make_camera(name: str) -> CameraConfig:
    return CameraConfig(
        entity_id=f"camera.{name.lower().replace(' ', '_')}",
        motion_entity=f"binary_sensor.{name.lower().replace(' ', '_')}_motion",
        name=name,
    )


def _make_server(cameras=None, connected=True, media_path: str = "/nonexistent") -> WebServer:
    config = MagicMock()
    config.cameras = cameras if cameras is not None else []
    config.media_path = media_path
    ha = MagicMock()
    ha.connected = connected
    return WebServer(config, ha)


async def test_get_root_returns_200_reports_page():
    server = _make_server()
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert "Camera Reports" in text
    finally:
        await client.close()


async def test_get_camera_test_returns_200_with_camera_name():
    server = _make_server(cameras=[_make_camera("Front Door")])
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/camera-test")
        assert resp.status == 200
        text = await resp.text()
        assert "Front Door" in text
    finally:
        await client.close()


async def test_get_camera_test_no_cameras_shows_placeholder():
    server = _make_server(cameras=[])
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/camera-test")
        assert resp.status == 200
        text = await resp.text()
        assert "No cameras configured" in text
    finally:
        await client.close()


async def test_get_camera_test_slug_in_button():
    server = _make_server(cameras=[_make_camera("Back Yard")])
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/camera-test")
        text = await resp.text()
        assert "back_yard" in text
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# POST /test/{slug} tests
# ---------------------------------------------------------------------------

async def test_post_test_unknown_slug_returns_404():
    server = _make_server(cameras=[_make_camera("Front Door")])
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.post("/test/nonexistent_camera")
        assert resp.status == 404
    finally:
        await client.close()


async def test_post_test_not_connected_returns_503():
    server = _make_server(cameras=[_make_camera("Front Door")], connected=False)
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.post("/test/front_door")
        assert resp.status == 503
    finally:
        await client.close()


async def test_post_test_concurrent_returns_409():
    server = _make_server(cameras=[_make_camera("Front Door")])
    server._locks["front_door"] = asyncio.Lock()
    await server._locks["front_door"].acquire()
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.post("/test/front_door")
        assert resp.status == 409
    finally:
        server._locks["front_door"].release()
        await client.close()


async def test_post_test_snapshot_success():
    camera = _make_camera("Front Door")
    server = _make_server(cameras=[camera])
    fake_jpeg = b"\xff\xd8\xff" + b"\x00" * 20
    expected_b64 = base64.b64encode(fake_jpeg).decode()

    async def fake_snapshot(entity_id, filepath):
        import os
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(fake_jpeg)
        return True

    server._ha.camera_snapshot = fake_snapshot

    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.post("/test/front_door")
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["snapshot_b64"] == expected_b64
    finally:
        await client.close()


async def test_post_test_snapshot_failure_returns_ok_false():
    camera = _make_camera("Front Door")
    server = _make_server(cameras=[camera])
    server._ha.camera_snapshot = AsyncMock(return_value=False)

    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.post("/test/front_door")
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is False
        assert data["snapshot_b64"] is None
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# DELETE /reports/delete/{date}/{filename}
# ---------------------------------------------------------------------------

async def test_delete_report_removes_file(tmp_path):
    day = tmp_path / "2026-04-12"
    day.mkdir()
    report = day / "report_06-30-00.html"
    report.write_text("<html>old report</html>")

    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.delete("/reports/delete/2026-04-12/report_06-30-00.html")
        assert resp.status == 204
        assert not report.exists()
    finally:
        await client.close()


async def test_delete_report_removes_empty_day_dir(tmp_path):
    day = tmp_path / "2026-04-12"
    day.mkdir()
    (day / "report_06-30-00.html").write_text("<html/>")

    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        await client.delete("/reports/delete/2026-04-12/report_06-30-00.html")
        assert not day.exists()
    finally:
        await client.close()


async def test_delete_report_not_found_returns_404(tmp_path):
    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.delete("/reports/delete/2026-04-12/report_06-30-00.html")
        assert resp.status == 404
    finally:
        await client.close()


async def test_delete_report_rejects_path_traversal(tmp_path):
    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.delete("/reports/delete/../../../etc/report_00-00-00.html")
        assert resp.status in (400, 404)
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# GET / (reports home) and GET /reports/view/{date}/{filename}
# ---------------------------------------------------------------------------

from pathlib import Path as _Path


async def test_get_reports_empty_dir(tmp_path):
    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert "No reports" in text
    finally:
        await client.close()


async def test_get_reports_lists_report_files(tmp_path):
    day = tmp_path / "2026-04-12"
    day.mkdir()
    (day / "report_20-45-00.html").write_text("<html>night report</html>")

    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert "2026-04-12" in text
        assert "report_20-45-00.html" in text
    finally:
        await client.close()


async def test_get_report_view_serves_file(tmp_path):
    day = tmp_path / "2026-04-12"
    day.mkdir()
    (day / "report_20-45-00.html").write_text("<html>my report</html>")

    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/reports/view/2026-04-12/report_20-45-00.html")
        assert resp.status == 200
        text = await resp.text()
        assert "my report" in text
    finally:
        await client.close()


async def test_get_report_view_not_found(tmp_path):
    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/reports/view/2026-04-12/report_20-45-00.html")
        assert resp.status == 404
    finally:
        await client.close()


async def test_get_report_view_rejects_path_traversal(tmp_path):
    server = _make_server(media_path=str(tmp_path))
    client = TestClient(TestServer(server._app))
    await client.start_server()
    try:
        resp = await client.get("/reports/view/../../../etc/passwd/report_00-00-00.html")
        assert resp.status in (400, 404)
    finally:
        await client.close()
