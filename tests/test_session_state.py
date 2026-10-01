import json
from datetime import datetime, timezone

from src.session_state import SessionState


def test_load_missing_file_returns_none(tmp_path):
    assert SessionState(tmp_path / "session.json").load() is None


def test_save_then_load_round_trips(tmp_path):
    state = SessionState(tmp_path / "session.json")
    start = datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
    state.save(start)
    assert state.load() == start


def test_save_creates_parent_directory(tmp_path):
    state = SessionState(tmp_path / "nested" / "session.json")
    state.save(datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc))
    assert (tmp_path / "nested" / "session.json").exists()


def test_save_leaves_no_tmp_file(tmp_path):
    state = SessionState(tmp_path / "session.json")
    state.save(datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc))
    assert [p.name for p in tmp_path.iterdir()] == ["session.json"]


def test_clear_removes_file_and_tolerates_missing(tmp_path):
    state = SessionState(tmp_path / "session.json")
    state.save(datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc))
    state.clear()
    assert state.load() is None
    state.clear()  # second clear must not raise


def test_load_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "session.json"
    path.write_text("{not json")
    assert SessionState(path).load() is None


def test_load_missing_key_returns_none(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"something": "else"}))
    assert SessionState(path).load() is None


def test_load_naive_timestamp_returns_none(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps({"away_start": "2026-10-01T20:00:00"}))
    assert SessionState(path).load() is None


def test_save_to_unwritable_location_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    # Parent "directory" is a regular file, so mkdir/open fail.
    SessionState(blocker / "session.json").save(
        datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc)
    )
