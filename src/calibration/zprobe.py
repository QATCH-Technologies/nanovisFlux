from __future__ import annotations
from dataclasses import dataclass
from ..core import AxisId, MountSide
from ..geometry.coordinates import DeckPoint
from ..protocol.commands import ProbeMode
from ..protocol.errors import ProbeError


@dataclass
class SurfaceContact:
    side: MountSide
    xy: DeckPoint
    contact_microsteps: int          # vertical-axis position at contact
    z_zero_microsteps: int           # implied nozzle-reference z_zero
    tip_length_mm: float


class ZProbeCalibrator:
    """Finds the vertical z_zero for a mount by touching a conductive surface.

    Works in raw microsteps for the descent, so it does NOT need a prior Z
    calibration (that would be circular). It only needs the XY affine to
    position over the target. Whatever is on the nozzle -- a bare calibration
    probe or a disposable tip -- is described by ``tip_length_mm``; the result
    is the tip-independent nozzle reference, written back into the calibration.
    """

    def __init__(self, robot, side: MountSide = MountSide.LEFT, *,
                 feed: int = 100, safe_up_microsteps: int = 2000,
                 max_descent_microsteps: int | None = None):
        self.robot = robot
        self.side = side
        self.feed = feed
        self.safe_up = safe_up_microsteps
        cal = robot.calibration
        self.vertical = cal.vertical_axis(side)
        self.max_descent = (max_descent_microsteps
                            or robot.axes[self.vertical].config.endstop_limit)

    def probe_surface(self, xy: DeckPoint, tip_length_mm: float = 0.0,
                      commit: bool = True) -> SurfaceContact:
        """Probe straight down at ``xy`` until contact and return the result.

        If ``commit`` is True the derived z_zero is stored on the calibration,
        so a subsequent ``deck_to_motor`` (with the working tip) is correct.
        """
        cal = self.robot.calibration
        ctrl = self.robot.controller

        # 1. Lift to a safe height, then position over the target in XY.
        ctrl.rapid_move({self.vertical: self.safe_up})
        mx, my = cal.xy.apply(xy.x, xy.y)
        ctrl.rapid_move({AxisId.X: round(mx), AxisId.Y: round(my)})

        # 2. Probe down (error if it never touches).
        result = ctrl.probe(self.vertical, self.max_descent, feed=self.feed,
                            mode=ProbeMode.TOWARD_OR_FAIL)
        if not result.contacted:
            raise ProbeError(f"no surface found probing {self.side.value} at "
                             f"({xy.x}, {xy.y})")

        # 3. Read the exact contact microsteps and derive the nozzle z_zero.
        contact = self.robot.controller.report_position()[self.vertical]
        z_zero = cal.z_zero_from_contact(contact, tip_length_mm)
        if commit:
            cal.z_zero[self.side] = z_zero

        # 4. Retract to safe height.
        ctrl.rapid_move({self.vertical: self.safe_up})
        return SurfaceContact(self.side, xy, contact, z_zero, tip_length_mm)

    def calibrate_z_scale(self, xy: DeckPoint, high_z_mm: float, low_z_mm: float,
                          tip_length_mm: float = 0.0):
        """Optional: recover microsteps-per-mm by probing two surfaces of
        known deck-height difference at the same XY (e.g. a calibration block
        and the deck). Returns the measured microsteps/mm; does not commit."""
        # This is a helper stub: probe two known heights and divide the
        # microstep delta by the mm delta. Left explicit for the operator to
        # wire to real reference features.
        raise NotImplementedError("wire this to your two reference surfaces")
