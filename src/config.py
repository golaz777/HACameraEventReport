from __future__ import annotations
import json
from dataclasses import dataclass, field


@dataclass
class CameraConfig:
    entity_id: str
    motion_entity: str
    name: str = ""


@dataclass
class EmailConfig:
    enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    recipient: str
    sender: str


@dataclass
class MonitoringConfig:
    toggle_entity: str  # empty string = feature disabled


@dataclass
class Config:
    cameras: list[CameraConfig]
    email: EmailConfig
    ha_persistent: bool
    event_cooldown_seconds: int = 30
    media_path: str = "/data/camera_events"
    retention_days: int | None = 30
    monitoring: MonitoringConfig = field(
        default_factory=lambda: MonitoringConfig(toggle_entity="")
    )


def load_config(path: str = "/data/options.json") -> Config:
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Options file not found: {path}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    cameras = [
        CameraConfig(
            entity_id=c["entity_id"],
            motion_entity=c["motion_entity"],
            name=c.get("name") or c["entity_id"].split(".")[-1],
        )
        for c in data.get("cameras", [])
    ]

    try:
        email_data = data["report"]["email"]
    except KeyError as exc:
        raise ValueError(f"Missing required config key: {exc}") from exc

    email = EmailConfig(
        enabled=email_data["enabled"],
        smtp_host=email_data["smtp_host"],
        smtp_port=email_data["smtp_port"],
        smtp_user=email_data["smtp_user"],
        smtp_password=email_data["smtp_password"],
        recipient=email_data["recipient"],
        sender=email_data["sender"],
    )

    try:
        ha_persistent = data["notification"]["ha_persistent"]
    except KeyError as exc:
        raise ValueError(f"Missing required config key: {exc}") from exc

    monitoring_data = data.get("monitoring", {})
    monitoring = MonitoringConfig(
        toggle_entity=monitoring_data.get("toggle_entity", "")
    )

    _retention_sentinel = object()
    raw_retention = data.get("retention_days", _retention_sentinel)
    if raw_retention is _retention_sentinel:
        retention_days: int | None = 30  # default when key absent
    elif raw_retention in (None, ""):
        retention_days = None  # explicit empty = disabled
    else:
        retention_days = int(raw_retention)

    return Config(
        cameras=cameras,
        email=email,
        ha_persistent=ha_persistent,
        event_cooldown_seconds=data.get("event_cooldown_seconds", 30),
        media_path=data.get("media_path", "/data/camera_events"),
        retention_days=retention_days,
        monitoring=monitoring,
    )
