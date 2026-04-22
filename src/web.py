from __future__ import annotations
import asyncio
import base64
import json
import logging
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
import aiohttp.web as web
from jinja2 import Environment, FileSystemLoader

from src.config import Config
from src.ha_client import HAClient
from src.report import list_reports
from src.snapshot import _slugify
from src.store import EventStore

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


class WebServer:
    def __init__(self, config: Config, ha_client: HAClient, broadcaster=None):
        self._config = config
        self._ha = ha_client
        self._broadcaster = broadcaster
        self._store = EventStore(config.media_path)
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )
        self._locks: dict[str, asyncio.Lock] = {}
        self._app = web.Application()
        self._app.router.add_get("/", self._handle_reports)
        self._app.router.add_get("/camera-test", self._handle_root)
        self._app.router.add_get("/live", self._handle_live)
        self._app.router.add_get("/analytics", self._handle_analytics)
        self._app.router.add_get("/events/stream", self._handle_events_stream)
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

    async def _handle_live(self, request: web.Request) -> web.Response:
        ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")
        template = self._env.get_template("live.html.j2")
        html = template.render(ingress_path=ingress_path)
        return web.Response(text=html, content_type="text/html")

    async def _handle_events_stream(self, request: web.Request) -> web.StreamResponse:
        if self._broadcaster is None:
            return web.Response(status=503, text="Event broadcaster not available")

        resp = web.StreamResponse()
        resp.headers["Content-Type"] = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        await resp.prepare(request)

        q = self._broadcaster.subscribe()
        try:
            while True:
                try:
                    data = await asyncio.wait_for(q.get(), timeout=25.0)
                    payload = json.dumps(data)
                    await resp.write(f"data: {payload}\n\n".encode())
                except asyncio.TimeoutError:
                    await resp.write(b": heartbeat\n\n")
        except (ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            self._broadcaster.unsubscribe(q)
        return resp

    async def _handle_reports(self, request: web.Request) -> web.Response:
        ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")
        all_reports = list_reports(self._config.media_path)

        # Parse filter params
        start_str = request.rel_url.query.get("start", "")
        end_str = request.rel_url.query.get("end", "")
        try:
            min_events = int(request.rel_url.query.get("min_events", "0"))
        except (ValueError, TypeError):
            min_events = 0

        # Apply date range filter
        if start_str:
            try:
                start_date = date.fromisoformat(start_str)
                all_reports = [r for r in all_reports if date.fromisoformat(r["date"]) >= start_date]
            except ValueError:
                pass

        if end_str:
            try:
                end_date = date.fromisoformat(end_str)
                all_reports = [r for r in all_reports if date.fromisoformat(r["date"]) <= end_date]
            except ValueError:
                pass

        # Apply min_events filter
        if min_events > 0:
            all_reports = [r for r in all_reports if r.get("event_count", 0) >= min_events]

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
            filter_start=start_str,
            filter_end=end_str,
            filter_min_events=min_events,
        )
        return web.Response(text=html, content_type="text/html")

    async def _handle_analytics(self, request: web.Request) -> web.Response:
        ingress_path = request.headers.get("X-Ingress-Path", "").rstrip("/")

        # Parse days param (default 30)
        try:
            days = int(request.rel_url.query.get("days", "30"))
            days = max(1, min(days, 365))  # Clamp to 1-365
        except (ValueError, TypeError):
            days = 30

        # Compute date range
        end = date.today()
        start = end - timedelta(days=days - 1)

        # Read events for the range
        events_by_date = self._store.read_range(start, end)

        # Aggregate stats
        per_day = {}
        per_camera = {}
        by_hour = {}
        total_events = 0

        # Initialize per_day with all dates in range
        current = start
        while current <= end:
            per_day[current.isoformat()] = 0
            current += timedelta(days=1)

        # Initialize by_hour
        for h in range(24):
            by_hour[h] = 0

        # Process all events
        for d, events in events_by_date.items():
            per_day[d.isoformat()] = len(events)
            for event in events:
                total_events += 1
                hour = event.timestamp.hour
                by_hour[hour] = by_hour.get(hour, 0) + 1

                camera = event.camera_name
                per_camera[camera] = per_camera.get(camera, 0) + 1

        # Find peak day and busiest camera
        peak_day = None
        peak_count = 0
        for d, count in per_day.items():
            if count > peak_count:
                peak_count = count
                peak_day = d

        busiest_camera = None
        busiest_count = 0
        for camera, count in per_camera.items():
            if count > busiest_count:
                busiest_count = count
                busiest_camera = camera

        # Prepare data for template
        per_day_sorted = [(d, per_day[d]) for d in sorted(per_day.keys())]
        per_camera_sorted = sorted(per_camera.items(), key=lambda x: x[1], reverse=True)
        by_hour_sorted = [(h, by_hour.get(h, 0)) for h in range(24)]

        # Compute max values for chart scaling
        max_per_day = max([count for _, count in per_day_sorted], default=1)
        max_per_camera = max([count for _, count in per_camera_sorted], default=1) if per_camera_sorted else 1
        max_by_hour = max(by_hour.values(), default=1)

        template = self._env.get_template("analytics.html.j2")
        html = template.render(
            ingress_path=ingress_path,
            total_events=total_events,
            peak_day=peak_day,
            peak_count=peak_count,
            busiest_camera=busiest_camera,
            busiest_count=busiest_count,
            per_day=per_day_sorted,
            per_camera=per_camera_sorted,
            by_hour=by_hour_sorted,
            max_per_day=max_per_day,
            max_per_camera=max_per_camera,
            max_by_hour=max_by_hour,
            days=days,
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
