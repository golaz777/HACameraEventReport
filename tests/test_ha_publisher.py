from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.ha_publisher import HAPublisher
from src.store import MotionEvent

T0 = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 1, 21, 15, tzinfo=timezone.utc)


def _event(ts=T1, name="Front Door", entity="camera.front_door", path="/snap.jpg"):
    return MotionEvent(timestamp=ts, camera_name=name, camera_entity=entity, screenshot_path=path)


@pytest.fixture
def ha():
    client = AsyncMock()
    client.set_state = AsyncMock(return_value=True)
    client.fire_event = AsyncMock()
    return client


def _states(ha):
    """Latest pushed (state, attributes) per entity id."""
    return {c.args[0]: (c.args[1], c.args[2]) for c in ha.set_state.call_args_list}


async def test_publish_initial_home_with_no_report(ha):
    await HAPublisher(ha).publish_initial(False, None, [], None)
    s = _states(ha)
    assert s["binary_sensor.camera_event_report_monitoring"][0] == "off"
    assert s["binary_sensor.camera_event_report_monitoring"][1]["since"] is None
    assert s["sensor.camera_event_report_session_events"][0] == "0"
    assert s["sensor.camera_event_report_last_motion"][0] == "unknown"
    assert s["sensor.camera_event_report_last_report"][0] == "unknown"
    ha.fire_event.assert_not_called()


async def test_publish_initial_away_rebuilds_counts(ha):
    events = [_event(), _event(ts=T0, name="Back Yard", entity="camera.back_yard")]
    report = {
        "timestamp": "2026-09-30T06:00:00+00:00", "event_count": 4, "human_count": 1,
        "detection_enabled": True, "report_path": "/media/2026-09-30/report_08-00-00.html",
    }
    await HAPublisher(ha).publish_initial(True, T0, events, report)
    s = _states(ha)
    assert s["binary_sensor.camera_event_report_monitoring"] == (
        "on", {"friendly_name": "Camera Event Report Monitoring", "icon": "mdi:shield-home",
               "since": T0.isoformat()})
    assert s["sensor.camera_event_report_session_events"][0] == "2"
    assert s["sensor.camera_event_report_session_events"][1]["per_camera"] == {"Front Door": 1, "Back Yard": 1}
    # Newest event wins, regardless of list order.
    assert s["sensor.camera_event_report_last_motion"][0] == T1.isoformat()
    assert s["sensor.camera_event_report_last_report"] == (
        "2026-09-30T06:00:00+00:00",
        {"friendly_name": "Camera Event Report Last Report", "device_class": "timestamp",
         "event_count": 4, "human_count": 1, "detection_enabled": True,
         "report_path": "/media/2026-09-30/report_08-00-00.html"})


async def test_on_session_start_resets_counts(ha):
    pub = HAPublisher(ha)
    await pub.on_motion(_event())
    await pub.on_session_start(T0)
    s = _states(ha)
    assert s["binary_sensor.camera_event_report_monitoring"][0] == "on"
    assert s["sensor.camera_event_report_session_events"] == (
        "0", {"friendly_name": "Camera Event Report Session Events",
              "unit_of_measurement": "events", "state_class": "measurement", "per_camera": {}})


async def test_on_motion_updates_entities_and_fires_event(ha):
    pub = HAPublisher(ha)
    await pub.on_session_start(T0)
    await pub.on_motion(_event())
    s = _states(ha)
    assert s["sensor.camera_event_report_session_events"][0] == "1"
    assert s["sensor.camera_event_report_last_motion"] == (
        T1.isoformat(),
        {"friendly_name": "Camera Event Report Last Motion", "device_class": "timestamp",
         "camera_name": "Front Door", "camera_entity": "camera.front_door",
         "snapshot_path": "/snap.jpg"})
    ha.fire_event.assert_awaited_once_with("camera_event_report_motion", {
        "camera_name": "Front Door", "camera_entity": "camera.front_door",
        "timestamp": T1.isoformat(), "snapshot_path": "/snap.jpg"})


async def test_on_report_turns_monitoring_off_and_fires_ready(ha):
    pub = HAPublisher(ha)
    await pub.on_session_start(T0)
    await pub.on_motion(_event())
    ts = datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc)
    await pub.on_report(date(2026, 10, 2), "/media/r.html", 1, 0, True, ts)
    s = _states(ha)
    assert s["binary_sensor.camera_event_report_monitoring"][0] == "off"
    # Last session's count stays visible after it ends.
    assert s["sensor.camera_event_report_session_events"][0] == "1"
    assert s["sensor.camera_event_report_last_report"][0] == ts.isoformat()
    ha.fire_event.assert_awaited_with("camera_event_report_report_ready", {
        "date": "2026-10-02", "report_path": "/media/r.html", "event_count": 1,
        "human_count": 0, "detection_enabled": True})


async def test_publish_entities_off_skips_set_state(ha):
    pub = HAPublisher(ha, publish_entities=False)
    await pub.on_session_start(T0)
    await pub.on_motion(_event())
    ha.set_state.assert_not_called()
    ha.fire_event.assert_awaited_once()


async def test_fire_events_off_skips_events(ha):
    pub = HAPublisher(ha, fire_events=False)
    await pub.on_motion(_event())
    await pub.on_report(date(2026, 10, 2), "/r.html", 1, 0, True, T1)
    ha.fire_event.assert_not_called()
    ha.set_state.assert_called()


async def test_failures_are_swallowed(ha):
    ha.set_state = AsyncMock(side_effect=RuntimeError("boom"))
    ha.fire_event = AsyncMock(side_effect=RuntimeError("boom"))
    pub = HAPublisher(ha)
    await pub.publish_initial(True, T0, [_event()], None)
    await pub.on_session_start(T0)
    await pub.on_motion(_event())
    await pub.on_report(date(2026, 10, 2), "/r.html", 1, 0, True, T1)
