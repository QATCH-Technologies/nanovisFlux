from __future__ import annotations

from abc import ABC, abstractmethod


class InputSource(ABC):
    """A source of jog action names. Concrete backends (keyboard, gamepad)
    subclass this; the session loop just calls run(session)."""

    @abstractmethod
    def run(self, session) -> None:
        """Block, translating input into session calls until quit. Held
        keys/buttons/sticks should call session.press(action) then
        session.release(action) on release so movement is continuous;
        one-shot inputs call session.handle(action)."""


class ScriptedInput(InputSource):
    """Feeds a fixed list of action names via session.handle() -- each one
    fires and completes immediately (a bounded nudge for movement actions),
    so no matching release() is needed. For tests and demos, no deps."""

    def __init__(self, actions):
        self.actions = list(actions)

    def run(self, session) -> None:
        for action in self.actions:
            if not session.running:
                break
            session.handle(action)
