from __future__ import annotations
import pytest
from src.presence_guard import PresenceGuard


def test_initial_state_is_not_away():
    guard = PresenceGuard()
    assert guard.is_away is False


def test_update_state_on_sets_away():
    guard = PresenceGuard()
    guard.update_state("on")
    assert guard.is_away is True


def test_update_state_off_clears_away():
    guard = PresenceGuard()
    guard.update_state("on")
    guard.update_state("off")
    assert guard.is_away is False


async def test_update_state_does_not_fire_callbacks():
    guard = PresenceGuard()
    called = []

    async def on_away():
        called.append("away")

    guard.on_away(on_away)
    guard.update_state("on")   # no callback — this is just seeding state

    assert called == []


async def test_away_callback_fires_on_transition():
    guard = PresenceGuard()
    called = []

    async def on_away():
        called.append("away")

    guard.on_away(on_away)
    guard.update_state("off")
    await guard.handle_toggle_change("on")

    assert called == ["away"]


async def test_home_callback_fires_on_transition():
    guard = PresenceGuard()
    called = []

    async def on_home():
        called.append("home")

    guard.on_home(on_home)
    guard.update_state("on")
    await guard.handle_toggle_change("off")

    assert called == ["home"]


async def test_no_duplicate_callback_on_same_state():
    guard = PresenceGuard()
    called = []

    async def on_away():
        called.append("away")

    guard.on_away(on_away)
    guard.update_state("on")
    # Already away — same state must not fire again
    await guard.handle_toggle_change("on")

    assert called == []


async def test_handle_toggle_change_updates_is_away():
    guard = PresenceGuard()
    await guard.handle_toggle_change("on")
    assert guard.is_away is True
    await guard.handle_toggle_change("off")
    assert guard.is_away is False
