from __future__ import annotations
from abc import ABC


class Tool(ABC):
    """Anything mountable on a carriage: pipette, touch probe, gripper,
    camera... To add a tool, subclass this and expose the behaviour you
    want. Nothing else in the stack changes -- that is the extension seam.
    """
    name: str = "tool"

    def __init__(self):
        self._mount = None
        self._robot = None

    def uses_plunger(self) -> bool:
        """Whether this tool drives the mount's plunger axis (B/C)."""
        return False

    def on_attach(self, mount, robot) -> None:
        self._mount = mount
        self._robot = robot

    def on_detach(self) -> None:
        self._mount = None
        self._robot = None

    @property
    def mount(self):
        return self._mount
