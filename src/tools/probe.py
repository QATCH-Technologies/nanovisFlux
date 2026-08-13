from __future__ import annotations

from ..core import AxisId
from ..geometry.coordinates import DeckPoint
from ..protocol.commands import ProbeMode
from .base import Tool


class TouchProbe(Tool):
    """A conductive touch sensor used to find surface heights for
    calibration. Wraps the firmware G38 probe cycle in deck-space terms."""

    def __init__(self, name: str = "touch-probe", length_mm: float = 0.0, brand: str = ""):
        super().__init__()
        self.name = name  # instance identity, e.g. a specific probe's own name
        self.brand = brand  # vendor/manufacturer -- "" when unknown/custom
        #: Fixed distance from the mount's nozzle reference to the probe's
        #: contact end -- same role as a pipette tip's length_mm, but fixed
        #: rather than swappable, so it needs no current_tip-style
        #: bookkeeping: tip_offset_mm() below reports it unconditionally.
        self.length_mm = length_mm

    def tip_offset_mm(self) -> float:
        """Read by the robot to make Z moves place the probe's contact end
        rather than the bare nozzle -- see Robot.tip_offset."""
        return self.length_mm

    def probe_down(self, to_z_mm: float, feed: int = 100):
        """Probe the mount's vertical axis toward the deck until contact.
        Returns the contact point in deck coordinates, or None on no-touch."""
        cal = self._robot.calibration
        side = self._mount.side
        vertical = self._mount.vertical
        target = cal.deck_to_motor(DeckPoint(0, 0, to_z_mm), side)[vertical]
        result = self._robot.controller.probe(
            vertical, target, feed=feed, mode=ProbeMode.TOWARD_OR_FAIL
        )
        if not result.contacted:
            return None
        pos = self._robot.controller.report_position()
        x_mm, y_mm = cal.motor_to_deck_xy(pos.get(AxisId.X, 0), pos.get(AxisId.Y, 0), side)
        return DeckPoint(x_mm, y_mm, to_z_mm)
