"""
Touch-probe tool for deck-surface detection and calibration.

This module defines :class:`TouchProbe`, a concrete :class:`Tool`
implementation that uses the controller's firmware-supported probing cycle to
detect physical surfaces.

The probe operates in deck-space coordinates while delegating the underlying
probe motion to the controller's `G38` implementation. Its fixed physical
length is exposed through :meth:`TouchProbe.tip_offset_mm` so robot-level
coordinate transformations place the probe's contact end at the requested
deck-space Z position rather than its mounting reference point.

A probe operation can return the deck-space XY position at which contact was
requested, or `None` when the firmware reports that no contact occurred.
"""

from __future__ import annotations

from ..core import AxisId
from ..geometry.coordinates import DeckPoint
from ..protocol.commands import ProbeMode
from .base import Tool


class TouchProbe(Tool):
    """Provide surface probing for deck calibration.

    `TouchProbe` is a fixed-length tool used to locate physical surfaces
    along a mount's vertical axis. It wraps the controller's firmware probe
    cycle while exposing the operation in deck-space coordinates.

    The probe's fixed length is treated as a tip offset by the robot, ensuring
    that deck-space Z coordinates refer to the probe's contact end rather than
    the mount's nozzle reference.

    Args:
        name: Name used to identify this probe instance.
        length_mm: Fixed distance in millimeters from the mount reference to
            the probe's contact end.
        brand: Probe manufacturer or vendor name. May be empty when unknown
            or when using a custom probe.

    Attributes:
        name: Instance-specific probe name.
        brand: Probe manufacturer or vendor.
        length_mm: Fixed probe length in millimeters.
    """

    def __init__(
        self,
        name: str = "touch-probe",
        length_mm: float = 0.0,
        brand: str = "",
    ):
        """Initialize a touch probe.

        The probe starts detached from any robot mount. Its fixed length is stored
        as the tip offset used by robot-level deck-to-motor coordinate
        transformations.

        Args:
            name: Name used to identify this probe instance.
            length_mm: Fixed distance in millimeters from the mount reference to
                the probe's contact end.
            brand: Probe manufacturer or vendor name.
        """
        super().__init__()
        self.name = name
        self.brand = brand
        self.length_mm = length_mm

    def tip_offset_mm(self) -> float:
        """Return the fixed offset from the mount reference to the probe tip.

        Returns:
            Probe length in millimeters.
        """
        return self.length_mm

    def probe_down(self, to_z_mm: float, feed: int = 100) -> DeckPoint | None:
        """Probe toward a target deck-space Z height until contact or failure.

        Converts the requested deck-space Z coordinate to the motor coordinate
        corresponding to the mount's vertical axis, then executes a
        `ProbeMode.TOWARD_OR_FAIL` probe cycle. The probe's fixed tip offset is
        not applied explicitly here; it is accounted for by the calibration and
        robot-level coordinate conventions used to define the target.

        The probe must be attached to a robot mount, and the robot must have a
        valid deck calibration. The mount must also expose a configured vertical
        axis. If the controller reports successful contact, the current motor X/Y
        position is converted back to deck coordinates and returned as a
        :class:`DeckPoint`. The returned Z coordinate is the requested
        `to_z_mm` value, representing the deck-space surface being probed.

        Args:
            to_z_mm: Target surface height in deck-space millimeters. The probe
                moves toward this height and reports contact if the firmware
                detects the conductive surface before the target is exceeded.
            feed: Probe feed rate in controller units.

        Returns:
            The deck-space contact position as a :class:`DeckPoint` when the probe
            reports successful contact. Returns `None` when the probe reaches
            the configured limit without detecting contact.

        Raises:
            RuntimeError: If the probe is not attached to a robot or mount, the
                robot has no initialized calibration, or the mount has no
                configured vertical axis.
        """
        if self._robot is None or self._mount is None:
            raise RuntimeError("_robot and/or _mount is not initialized")
        cal = self._robot.calibration
        if cal is None:
            raise RuntimeError("calibration is not initialized")
        side = self._mount.side
        vertical = self._mount.vertical
        if vertical is None:
            raise RuntimeError("mount vertical axis is not initialized")
        target = cal.deck_to_motor(DeckPoint(0, 0, to_z_mm), side)[vertical]
        result = self._robot.controller.probe(
            vertical, target, feed=feed, mode=ProbeMode.TOWARD_OR_FAIL
        )
        if not result.contacted:
            return None
        pos = self._robot.controller.report_position()
        x_mm, y_mm = cal.motor_to_deck_xy(pos.get(AxisId.X, 0), pos.get(AxisId.Y, 0), side)
        return DeckPoint(x_mm, y_mm, to_z_mm)
