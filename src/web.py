from __future__ import annotations
import asyncio
import base64
import logging
import os
import tempfile
from pathlib import Path
import aiohttp.web as web
from jinja2 import Environment, FileSystemLoader

from src.config import Config
from src.ha_client import HAClient
from src.report import list_reports
from src.snapshot import _slugify

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class WebServer:
    def __init__(self, config: Config, ha_client: HAClient):
        self._config = config
        self._ha = ha_client
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )
        self._locks: dict[str, asyncio.Lock] = {}
        self._app = web.Application()
        self._app.router.add_get("/", self._handle_reports)
        self._app.router.add_get("/camera-test", self._handle_root)
        self._app.router.add_post("/test/{slug}", self._handle_test)
        self._app.router.add_get("/reports/view/{date}/{filename}", self._handle_report_file)
        self._app.router.add_delete("/reports/delete/{date}/{filename}", self._handle_report_delete)
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", 8099)
        await site.start()
        logger.info("Web panel started on port 8099")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("Web panel stopped")

    async def _handle_root(self, request: web.Request) -> web.Response:
        ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")
        cameras = [
            {
                "name": c.name,
                "slug": _slugify(c.name),
            }
            for c in self._config.cameras
        ]
        template = self._env.get_template("panel.html.j2")
        html = template.render(cameras=cameras, ingress_path=ingress_path)
        return web.Response(text=html, content_type="text/html")

    async def _handle_test(self, request: web.Request) -> web.Response:
        slug = request.match_info["slug"]

        camera = next(
            (c for c in self._config.cameras if _slugify(c.name) == slug), None
        )
        if camera is None:
            return web.Response(status=404, text="Camera not found")

        if not self._ha.connected:
            return web.Response(status=503, text="Service starting")

        if slug not in self._locks:
            self._locks[slug] = asyncio.Lock()
        lock = self._locks[slug]

        if lock.locked():
            return web.Response(status=409, text="Test already in progress")

        async with lock:
            # Live snapshot via HA camera proxy (5s timeout)
            snapshot_b64: str | None = None
            tmp_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp_path = tmp.name
                success = await asyncio.wait_for(
                    self._ha.camera_snapshot(camera.entity_id, tmp_path),
                    timeout=5.0,
                )
                if success:
                    with open(tmp_path, "rb") as f:
                        snapshot_b64 = base64.b64encode(f.read()).decode()
            except asyncio.TimeoutError:
                pass
            except Exception as exc:
                logger.debug("Snapshot error for %s: %s", camera.name, exc)
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

            return web.json_response(
                {
                    "ok": snapshot_b64 is not None,
                    "snapshot_b64": snapshot_b64,
                }
            )

    async def _handle_reports(self, request: web.Request) -> web.Response:
        ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")
        all_reports = list_reports(self._config.media_path)
        per_page = 100
        total = len(all_reports)
        total_pages = max(1, (total + per_page - 1) // per_page)
        try:
            page = max(1, min(int(request.rel_url.query.get("page", 1)), total_pages))
        except (ValueError, TypeError):
            page = 1
        offset = (page - 1) * per_page
        reports = all_reports[offset:offset + per_page]
        template = self._env.get_template("reports.html.j2")
        html = template.render(
            reports=reports,
            ingress_path=ingress_path,
            page=page,
            total_pages=total_pages,
            total=total,
        )
        return web.Response(text=html, content_type="text/html")

    async def _handle_report_file(self, request: web.Request) -> web.Response:
        date_str = request.match_info["date"]
        filename = request.match_info["filename"]
        if ".." in date_str or ".." in filename or "/" in filename:
            return web.Response(status=400, text="Bad request")
        path = Path(self._config.media_path) / date_str / filename
        if not path.exists() or not path.name.startswith("report") or path.suffix != ".html":
            return web.Response(status=404, text="Report not found")
        ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")
        html = path.read_text(encoding="utf-8")
        nav = (
            f'<nav style="margin-bottom:1.5rem;font-size:0.875rem;">'
            f'<a href="{ingress_path}/" style="color:#3b82f6;text-decoration:none;">&#8592; Camera Reports</a>'
            f'</nav>'
        )
        html = html.replace("<body>", f"<body>\n  {nav}", 1)
        return web.Response(text=html, content_type="text/html")

    async def _handle_report_delete(self, request: web.Request) -> web.Response:
        date_str = request.match_info["date"]
        filename = request.match_info["filename"]
        if ".." in date_str or ".." in filename or "/" in filename:
            return web.Response(status=400, text="Bad request")
        path = Path(self._config.media_path) / date_str / filename
        if not path.exists() or not path.name.startswith("report") or path.suffix != ".html":
            return web.Response(status=404, text="Report not found")
        path.unlink()
        # Remove the date directory if it is now empty
        try:
            path.parent.rmdir()
        except OSError:
            pass
        logger.info("Report deleted: %s", path)
        return web.Response(status=204)
