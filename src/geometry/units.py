"""Unit conversions between physical distances and controller microsteps.

This module defines the axis scaling used to convert physical distances in
millimeters or centimeters into the integer microstep units expected by the
motion controller.

Linear travel calibration is provided for the X, Y, Z, and A axes from
measured full-travel distances. Plunger axes B and C intentionally have no
default linear distance calibration because their motion is volumetric rather
than a direct physical travel measurement.

The XY plane may use a calibrated affine transform for precise deck
positioning; these axis scales are primarily used for vertical and other
linear axes and for approximate position visualization before full XY
calibration.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import AxisId

MICROSTEPS_PER_STEP = 32  # firmware runs at 1/32 microstepping


@dataclass(frozen=True)
class AxisScale:
    """Convert physical linear distances to firmware microsteps for an axis.

    ``AxisScale`` stores the full motor-step density of an axis and derives the
    corresponding microstep density from the controller's configured
    microstepping factor. It provides conversions in both directions between
    millimeters, centimeters, and firmware microsteps.

    The scale is primarily intended for axes with a linear relationship
    between physical travel and motor position, such as the vertical Z/A
    axes. XY positioning normally uses a calibrated affine transform instead
    of this independent per-axis scale.

    Attributes:
        steps_per_mm: Number of full motor steps required for one millimeter
            of physical travel.
    """

    steps_per_mm: float

    @property
    def microsteps_per_mm(self) -> float:
        """Return the number of firmware microsteps per millimeter.

        Returns:
            float: Microsteps corresponding to one millimeter of physical travel,
            accounting for the configured microstepping factor.
        """
        return self.steps_per_mm * MICROSTEPS_PER_STEP

    def to_microsteps(self, mm: float) -> int:
        """Convert a physical distance in millimeters to microsteps.

        Args:
            mm: Distance in millimeters.

        Returns:
            int: Corresponding controller microstep count, rounded to the nearest
            integer.
        """
        return round(mm * self.microsteps_per_mm)

    def to_mm(self, microsteps: float) -> float:
        """Convert a controller position or distance from microsteps to millimeters.

        Args:
            microsteps: Distance or position expressed in firmware microsteps.

        Returns:
            float: Equivalent physical distance in millimeters.
        """
        return microsteps / self.microsteps_per_mm

    def to_cm(self, microsteps: float) -> float:
        """Convert a controller position or distance from microsteps to centimeters.

        Args:
            microsteps: Distance or position expressed in firmware microsteps.

        Returns:
            float: Equivalent physical distance in centimeters.
        """
        return self.to_mm(microsteps) / 10.0

    def cm_to_microsteps(self, cm: float) -> int:
        """Convert a physical distance in centimeters to microsteps.

        Args:
            cm: Distance in centimeters.

        Returns:
            int: Corresponding controller microstep count, rounded to the nearest
            integer.
        """
        return self.to_microsteps(cm * 10.0)

    @classmethod
    def from_travel(cls, microsteps: float, mm: float) -> AxisScale:
        """Construct an axis scale from a measured full-travel calibration.

        The supplied measurement defines how many firmware microsteps correspond
        to a known physical travel distance. The resulting scale stores the
        equivalent full-step density after accounting for the controller's
        microstepping factor.

        Args:
            microsteps: Number of firmware microsteps measured over the full
                physical travel.
            mm: Corresponding physical travel distance in millimeters.

        Returns:
            AxisScale: Scale derived from the measured travel.
        """
        return cls(steps_per_mm=microsteps / mm / MICROSTEPS_PER_STEP)


# Measured full-travel calibration values for linearly scaled axes.
#
# Each entry maps an axis to ``(microsteps, millimeters)`` measured from the
# home position to the far end of travel. These values provide the default
# linear axis scales and an approximate basis for position visualization
# before a full XY affine calibration is available.
MEASURED_AXIS_TRAVEL_MM = {
    AxisId.X: (60000, 410.0),
    AxisId.Y: (52000, 315.0),
    AxisId.Z: (160000, 200.0),
    AxisId.A: (160000, 200.0),
}


def default_axis_scale(axis: AxisId) -> AxisScale:
    """Return the measured default linear scale for an axis.

    The scale is derived from the corresponding entry in
    :data:`MEASURED_AXIS_TRAVEL_MM`.

    Args:
        axis: Axis for which the physical-to-microstep conversion should be
            returned.

    Returns:
        AxisScale: Measured linear travel scale for the requested axis.

    Raises:
        KeyError: If the axis does not have a linear travel calibration.
            Plunger axes such as B and C intentionally do not have default
            millimeter-based scales.
    """
    microsteps, mm = MEASURED_AXIS_TRAVEL_MM[axis]
    return AxisScale.from_travel(microsteps, mm)
