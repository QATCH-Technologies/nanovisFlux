from __future__ import annotations
from dataclasses import dataclass
from ..core import AxisId, MountSide


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
