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
    def vertical(self) -> AxisId:
        return AxisId.Z if self.side is MountSide.LEFT else AxisId.A

    @property
    def plunger(self) -> AxisId:
        return AxisId.B if self.side is MountSide.LEFT else AxisId.C

    def attach(self, tool) -> None:
        self.tool = tool

    def detach(self):
        tool, self.tool = self.tool, None
        return tool
