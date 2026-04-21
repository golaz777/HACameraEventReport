from __future__ import annotations
import logging
import os
import re
from datetime import datetime

from src.config import CameraConfig

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def build_snapshot_path(base_path: str, camera: CameraConfig, ts: datetime) -> str:
    date_str = ts.strftime("%Y-%m-%d")
    time_str = ts.strftime("%H-%M-%S")
    slug = _slugify(camera.name)
    return f"{base_path}/{date_str}/{slug}_{time_str}.jpg"


async def take_snapshot(
    ha_client,
    camera: CameraConfig,
    ts: datetime,
    base_path: str,
) -> str | None:
    filepath = build_snapshot_path(base_path, camera, ts)
    dirpart = os.path.dirname(filepath)
    if dirpart:
        os.makedirs(dirpart, exist_ok=True)
    success = await ha_client.camera_snapshot(camera.entity_id, filepath)
    return filepath if success else None
