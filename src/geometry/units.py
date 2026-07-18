from __future__ import annotations
from dataclasses import dataclass

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
