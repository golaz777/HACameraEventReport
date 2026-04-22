import json
import pytest
from src.config import load_config, Config, CameraConfig, EmailConfig


def test_load_config_parses_cameras(tmp_path):
    options = {
        "cameras": [
            {
                "entity_id": "camera.front_door",
                "motion_entity": "binary_sensor.front_door_motion",
                "name": "Front Door",
            }
        ],
        "report": {
            "email": {
                "enabled": True,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "user@gmail.com",
                "smtp_password": "pass",
                "recipient": "dest@gmail.com",
                "sender": "ha@gmail.com",
            }
        },
        "notification": {"ha_persistent": True},
        "event_cooldown_seconds": 30,
    }
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert isinstance(config, Config)
    assert len(config.cameras) == 1
    cam = config.cameras[0]
    assert isinstance(cam, CameraConfig)
    assert cam.entity_id == "camera.front_door"
    assert cam.motion_entity == "binary_sensor.front_door_motion"
    assert cam.name == "Front Door"


def test_load_config_email(tmp_path):
    options = {
        "cameras": [],
        "report": {
            "email": {
                "enabled": True,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "user@gmail.com",
                "smtp_password": "pass",
                "recipient": "dest@gmail.com",
                "sender": "ha@gmail.com",
            }
        },
        "notification": {"ha_persistent": True},
        "event_cooldown_seconds": 30,
    }
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.email.enabled is True
    assert config.email.smtp_host == "smtp.gmail.com"
    assert config.email.smtp_port == 587
    assert config.email.smtp_user == "user@gmail.com"
    assert config.email.recipient == "dest@gmail.com"
    assert config.email.sender == "ha@gmail.com"
    assert config.event_cooldown_seconds == 30
    assert config.ha_persistent is True


def test_load_config_defaults_cooldown(tmp_path):
    options = {
        "cameras": [],
        "report": {
            "email": {
                "enabled": False,
                "smtp_host": "",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "recipient": "",
                "sender": "",
            }
        },
        "notification": {"ha_persistent": False},
    }
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))
    assert config.event_cooldown_seconds == 30


def test_load_config_missing_report_key_raises(tmp_path):
    options = {"cameras": [], "notification": {"ha_persistent": False}}
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))
    with pytest.raises((KeyError, ValueError)):
        load_config(str(options_file))


def test_load_config_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/options.json")


def test_load_config_parses_monitoring_toggle_entity(tmp_path):
    options = {
        "cameras": [],
        "report": {
            "email": {
                "enabled": False,
                "smtp_host": "",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "recipient": "",
                "sender": "",
            }
        },
        "notification": {"ha_persistent": False},
        "monitoring": {"toggle_entity": "input_boolean.away_mode"},
    }
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.monitoring.toggle_entity == "input_boolean.away_mode"


def test_load_config_parses_media_path(tmp_path):
    options = {
        "cameras": [],
        "report": {
            "email": {
                "enabled": False,
                "smtp_host": "",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "recipient": "",
                "sender": "",
            }
        },
        "notification": {"ha_persistent": False},
        "media_path": "/data/my_events",
    }
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.media_path == "/data/my_events"


def test_load_config_media_path_defaults_to_data(tmp_path):
    options = {
        "cameras": [],
        "report": {
            "email": {
                "enabled": False,
                "smtp_host": "",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "recipient": "",
                "sender": "",
            }
        },
        "notification": {"ha_persistent": False},
    }
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.media_path == "/data/camera_events"


def test_load_config_retention_days_default(tmp_path):
    options = _minimal_options([])
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.retention_days == 30


def test_load_config_retention_days_explicit(tmp_path):
    options = {**_minimal_options([]), "retention_days": 7}
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.retention_days == 7


def test_load_config_retention_days_empty_disables(tmp_path):
    options = {**_minimal_options([]), "retention_days": None}
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.retention_days is None


def test_load_config_monitoring_defaults_to_empty(tmp_path):
    options = {
        "cameras": [],
        "report": {
            "email": {
                "enabled": False,
                "smtp_host": "",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "recipient": "",
                "sender": "",
            }
        },
        "notification": {"ha_persistent": False},
    }
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.monitoring.toggle_entity == ""


def _minimal_options(cameras):
    return {
        "cameras": cameras,
        "report": {
            "email": {
                "enabled": False,
                "smtp_host": "",
                "smtp_port": 587,
                "smtp_user": "",
                "smtp_password": "",
                "recipient": "",
                "sender": "",
            }
        },
        "notification": {"ha_persistent": False},
    }


def test_load_config_camera_name_defaults_to_entity_id_suffix(tmp_path):
    options = _minimal_options([
        {"entity_id": "camera.front_door", "motion_entity": "binary_sensor.front_door_motion"}
    ])
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.cameras[0].name == "front_door"


def test_load_config_camera_name_explicit_overrides_default(tmp_path):
    options = _minimal_options([
        {
            "entity_id": "camera.front_door",
            "motion_entity": "binary_sensor.front_door_motion",
            "name": "My Cam",
        }
    ])
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))

    config = load_config(str(options_file))

    assert config.cameras[0].name == "My Cam"
