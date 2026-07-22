from __future__ import annotations
from dataclasses import dataclass
from ..core import AxisId
from ..geometry.units import default_axis_scale


@dataclass
class AxisConfig:
    """Static configuration for one axis. Load these from YAML/JSON so no
    magic numbers live in code. The defaults below mirror the firmware."""
    axis: AxisId
    endstop_limit: int          # microsteps; hard ceiling (M201 can only tighten)
    homing_dir_forward: bool
    invert: bool
    travel_speed: float         # microsteps/s
    homing_speed: float
    travel_accel: float
    endstop_bounce: int
    steps_per_mm: float | None = None


@dataclass
class Axis:
    """Runtime state wrapper around an AxisConfig."""
    config: AxisConfig
    homed: bool = False
    position: int = 0           # last known microsteps (abs, as firmware reports)

    @property
    def id(self) -> AxisId:
        return self.config.axis


#: The sequence the firmware homes axes in on a bare ``G28`` (see
#: OT2-stepper-controller.ino's G28 handler). NOTE: the .ino file's own
#: comment says "Homing order: A, Z, Y, X, B, C" but the code right below it
#: actually calls home_stepper in the order A, Z, X, Y, B, C -- a real
#: mismatch between the comment and what the firmware does. This constant
#: follows the documented/intended order (A, Z, Y, X, B, C) since that's
#: what was specified for the GUI's homing animation; it has no effect on
#: real axis order (fixed in firmware) and is purely for sequencing the
#: live-view animation to match operator expectations.
HOMING_ORDER = (AxisId.A, AxisId.Z, AxisId.Y, AxisId.X, AxisId.B, AxisId.C)


def default_axis_configs() -> dict:
    """The six axes as configured in the reference firmware."""
    limit = {AxisId.X: 60000, AxisId.Y: 52000, AxisId.Z: 160000,
             AxisId.A: 160000, AxisId.B: 20000, AxisId.C: 20000}
    travel = {AxisId.X: 16000, AxisId.Y: 16000, AxisId.Z: 32000,
              AxisId.A: 32000, AxisId.B: 6900, AxisId.C: 6900}
    # Matches firmware HOMING_SPEEDS[6] = {8000, 8000, 16000, 16000, 5000, 5000}
    # (order X, Y, Z, A, B, C).
    homing = {AxisId.X: 8000, AxisId.Y: 8000, AxisId.Z: 16000,
              AxisId.A: 16000, AxisId.B: 5000, AxisId.C: 5000}
    accel = {AxisId.X: 69000, AxisId.Y: 69000, AxisId.Z: 69000,
             AxisId.A: 69000, AxisId.B: 3200, AxisId.C: 3200}
    bounce = {AxisId.X: 1000, AxisId.Y: 1000, AxisId.Z: 1500,
              AxisId.A: 1500, AxisId.B: 1250, AxisId.C: 1250}
    homing_fwd = {AxisId.X: True, AxisId.Y: True, AxisId.Z: True,
                  AxisId.A: True, AxisId.B: False, AxisId.C: False}
    invert = {AxisId.X: True, AxisId.Y: True, AxisId.Z: True,
              AxisId.A: True, AxisId.B: False, AxisId.C: False}
    return {
        a: AxisConfig(
            axis=a, endstop_limit=limit[a], homing_dir_forward=homing_fwd[a],
            invert=invert[a], travel_speed=travel[a], homing_speed=homing[a],
            travel_accel=accel[a], endstop_bounce=bounce[a],
            steps_per_mm=(default_axis_scale(a).steps_per_mm
                          if a in (AxisId.X, AxisId.Y, AxisId.Z, AxisId.A) else None),
        )
        for a in AxisId
    }
