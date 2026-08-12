from __future__ import annotations

from dataclasses import dataclass

from ..core import AxisId, MountSide

#: Fixed mechanical offset from the gantry's single X/Y reference point to
#: each mount, in deck mm -- LEFT/RIGHT are two carriages 32.5 mm apart
#: straddling that reference point; REAR (the fixed ultrasonic sensor mount)
#: sits 50 mm behind them, centered. ``mount_deck_pos = reference_deck_pos +
#: MOUNT_OFFSET_MM[side]``. The single source of truth for this geometry --
#: consumed by DeckCalibration (deck_to_motor/motor_to_deck_xy, so real
#: motion actually lands on the commanded mount instead of always landing
#: where LEFT would) and by the deck view (marker rendering).
MOUNT_OFFSET_MM: dict = {
    MountSide.LEFT: (-16.25, 0.0),
    MountSide.RIGHT: (16.25, 0.0),
    MountSide.REAR: (0.0, 50.0),
}


@dataclass
class Mount:
    """A carriage the gantry can raise/lower, carrying an optional Tool.
    LEFT uses vertical Z + plunger B; RIGHT uses vertical A + plunger C.

    A mount can exist with no plunger-driving tool attached (e.g. a bare
    sensor), in which case the B/C axis is simply never commanded -- which
    matches hardware where the C plunger may not be wired at all.
    """

    side: MountSide
    tool: object = None  # a tools.Tool; typed loosely to avoid an import cycle

    @property
    def vertical(self) -> AxisId | None:
        """None for REAR: it's fixed to the gantry frame, with no axis of
        its own -- it only ever travels along with X/Y."""
        if self.side is MountSide.LEFT:
            return AxisId.Z
        if self.side is MountSide.RIGHT:
            return AxisId.A
        return None

    @property
    def plunger(self) -> AxisId | None:
        if self.side is MountSide.LEFT:
            return AxisId.B
        if self.side is MountSide.RIGHT:
            return AxisId.C
        return None

    def attach(self, tool) -> None:
        self.tool = tool

    def detach(self):
        tool, self.tool = self.tool, None
        return tool
