from __future__ import annotations
from ..core import AxisId
from ..protocol.commands import ProbeMode
from ..geometry.coordinates import DeckPoint
from .base import Tool


class TouchProbe(Tool):
    """A conductive touch sensor used to find surface heights for
    calibration. Wraps the firmware G38 probe cycle in deck-space terms."""
    name = "touch-probe"

    def probe_down(self, to_z_mm: float, feed: int = 100):
        """Probe the mount's vertical axis toward the deck until contact.
        Returns the contact point in deck coordinates, or None on no-touch."""
        cal = self._robot.calibration
        side = self._mount.side
        vertical = self._mount.vertical
        target = cal.deck_to_motor(DeckPoint(0, 0, to_z_mm), side)[vertical]
        result = self._robot.controller.probe(
            vertical, target, feed=feed, mode=ProbeMode.TOWARD_OR_FAIL)
        if not result.contacted:
            return None
        pos = self._robot.controller.report_position()
        x_mm, y_mm = cal.motor_to_deck_xy(pos.get(AxisId.X, 0), pos.get(AxisId.Y, 0))
        return DeckPoint(x_mm, y_mm, to_z_mm)
