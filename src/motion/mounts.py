"""Robot mount definitions and shared mount-to-gantry geometry.

This module defines the mechanical mount abstraction used to associate robot
tools with the gantry's available mounting positions. It also provides the
single source of truth for the fixed deck-space offsets between the gantry's
reference X/Y position and each physical mount.

The supported mounts are:

* `LEFT` -- Uses the Z axis for vertical motion and the B axis for plunger
  motion.
* `RIGHT` -- Uses the A axis for vertical motion and the C axis for plunger
  motion.
* `REAR` -- A fixed mount centered behind the left/right carriages. It has
  no independent vertical or plunger axis and moves only with the gantry's
  X/Y motion.

:data:`MOUNT_OFFSET_MM` defines the mount positions relative to the common
gantry reference point in deck millimeters. This geometry is shared by motion
calibration and deck visualization so that commanded mount positions and
rendered mount positions remain consistent.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import AxisId, MountSide

MOUNT_OFFSET_MM: dict = {
    MountSide.LEFT: (-16.25, 0.0),
    MountSide.RIGHT: (16.25, 0.0),
    MountSide.REAR: (0.0, 50.0),
}
"""Fixed deck-space offsets from the gantry reference point to each mount.

Each value is an `(x_mm, y_mm)` offset in deck coordinates. The left and
right mounts are positioned symmetrically around the gantry's single X/Y
reference point, while the rear mount is centered behind them.

These offsets are the canonical representation of the robot's mount geometry
and should be used anywhere mount-specific deck coordinates are required,
including calibration transforms, motion planning, and deck visualization.
"""


@dataclass
class Mount:
    """Represent a physical carriage and its optionally attached tool.

    A mount identifies which physical mounting position is being addressed and
    provides the controller axes associated with that position's vertical and
    plunger motion.

    The left and right mounts provide independent vertical and plunger axes.
    The rear mount is fixed relative to the gantry frame and therefore has no
    dedicated vertical or plunger axis. A mount may exist without an attached
    tool, which is useful for hardware such as fixed sensors that do not
    require plunger control.

    Attributes:
        side: Physical mount position represented by this object.
        tool: Optional tool attached to the mount. The type is intentionally
            left loose to avoid an import dependency on the tool layer.
    """

    side: MountSide
    tool: object = None

    @property
    def vertical(self) -> AxisId | None:
        """Return the controller axis responsible for vertical mount motion.

        Returns:
            AxisId | None: `AxisId.Z` for the left mount,
            `AxisId.A` for the right mount, or `None` for the fixed rear
            mount.
        """
        if self.side is MountSide.LEFT:
            return AxisId.Z
        if self.side is MountSide.RIGHT:
            return AxisId.A
        return None

    @property
    def plunger(self) -> AxisId | None:
        """Return the controller axis responsible for plunger motion.

        Returns:
            AxisId | None: `AxisId.B` for the left mount,
            `AxisId.C` for the right mount, or `None` for the rear mount.
        """
        if self.side is MountSide.LEFT:
            return AxisId.B
        if self.side is MountSide.RIGHT:
            return AxisId.C
        return None

    def attach(self, tool) -> None:
        """Attach a tool to this mount.

        Any tool previously attached to the mount is replaced.

        Args:
            tool: Tool instance to associate with the mount.
        """
        self.tool = tool

    def detach(self):
        """Detach and return the tool currently attached to the mount.

        The mount's tool reference is cleared regardless of whether a tool was
        previously attached.

        Returns:
            object | None: Previously attached tool, or `None` if the mount was
            not carrying a tool.
        """
        tool, self.tool = self.tool, None
        return tool
