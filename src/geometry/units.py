from __future__ import annotations
from dataclasses import dataclass
from ..core import AxisId

MICROSTEPS_PER_STEP = 32  # firmware runs at 1/32 microstepping


@dataclass(frozen=True)
class AxisScale:
    """Converts millimetres to firmware microsteps for a single axis. Used
    mainly for the vertical (Z/A) and plunger (B/C) axes; the XY plane gets
    its scale from the calibrated affine transform instead."""
    steps_per_mm: float  # full motor steps per mm of travel

    @property
    def microsteps_per_mm(self) -> float:
        return self.steps_per_mm * MICROSTEPS_PER_STEP

    def to_microsteps(self, mm: float) -> int:
        return round(mm * self.microsteps_per_mm)

    def to_mm(self, microsteps: float) -> float:
        return microsteps / self.microsteps_per_mm

    def to_cm(self, microsteps: float) -> float:
        return self.to_mm(microsteps) / 10.0

    def cm_to_microsteps(self, cm: float) -> int:
        return self.to_microsteps(cm * 10.0)

    @classmethod
    def from_travel(cls, microsteps: float, mm: float) -> "AxisScale":
        """Build a scale from a measured full travel: ``microsteps`` of
        firmware motion covers ``mm`` of physical travel."""
        return cls(steps_per_mm=microsteps / mm / MICROSTEPS_PER_STEP)


#: Measured full-travel calibration, axis -> (microsteps, mm) from home to
#: the far end of travel. This is the source of truth for the default
#: per-axis scale (see ``default_axis_scale`` / ``motion.axis.default_axis_configs``)
#: and for deck-grid live-position display before a full 3-point XY
#: calibration has been done. Measured directly on the hardware:
#: X 60,000 microsteps -> 41 cm, Y 52,000 microsteps -> 31.5 cm,
#: Z/A 160,000 microsteps -> 20 cm (mount travel).
MEASURED_AXIS_TRAVEL_MM = {
    AxisId.X: (60000, 410.0),
    AxisId.Y: (52000, 315.0),
    AxisId.Z: (160000, 200.0),
    AxisId.A: (160000, 200.0),
}


def default_axis_scale(axis: AxisId) -> AxisScale:
    """The measured :class:`AxisScale` for ``axis``, from
    ``MEASURED_AXIS_TRAVEL_MM``. Raises ``KeyError`` for axes with no linear
    travel calibration (B/C, the plungers, are volumetric)."""
    microsteps, mm = MEASURED_AXIS_TRAVEL_MM[axis]
    return AxisScale.from_travel(microsteps, mm)
