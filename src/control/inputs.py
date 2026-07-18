from __future__ import annotations
from abc import ABC, abstractmethod


class InputSource(ABC):
    """A source of jog action names. Concrete backends (keyboard, gamepad)
    subclass this; the session loop just calls run(session)."""

    @abstractmethod
    def run(self, session) -> None:
        """Block, translating input into session.handle(action) until quit."""


class ScriptedInput(InputSource):
    """Feeds a fixed list of action names -- for tests and demos, no deps."""

    def __init__(self, actions):
        self.actions = list(actions)

    def run(self, session) -> None:
        for action in self.actions:
            if not session.running:
                break
            session.handle(action)
