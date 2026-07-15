from __future__ import annotations
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

AsyncCallback = Callable[[], Awaitable[None]]


class PresenceGuard:
    def __init__(self):
        self._is_away: bool = False
        self._away_callbacks: list[AsyncCallback] = []
        self._home_callbacks: list[AsyncCallback] = []

    @property
    def is_away(self) -> bool:
        return self._is_away

    def update_state(self, state: str) -> None:
        """Seed current state without firing callbacks (used at startup)."""
        self._is_away = (state == "on")

    def on_away(self, cb: AsyncCallback) -> None:
        self._away_callbacks.append(cb)

    def on_home(self, cb: AsyncCallback) -> None:
        self._home_callbacks.append(cb)

    async def handle_toggle_change(self, new_state: str) -> None:
        """Process toggle state change; fires callbacks on transitions only."""
        was_away = self._is_away
        self._is_away = (new_state == "on")
        if self._is_away and not was_away:
            logger.info("Away monitoring active")
            for cb in self._away_callbacks:
                await cb()
        elif not self._is_away and was_away:
            logger.info("Away monitoring ended")
            for cb in self._home_callbacks:
                await cb()
