"""Geometry, calibration, and unit-conversion primitives for deck motion.

This package provides the geometric abstractions used to convert between
physical deck coordinates and controller motor coordinates while keeping
machine-specific calibration and unit scaling separate from higher-level
motion logic.

The public API includes:

* :class:`DeckPoint` -- Representation of a point in deck-space coordinates.
* :class:`AffineTransform2D` -- Two-dimensional affine transformation for
  coordinate-system conversion.
* :class:`DeckCalibration` -- Calibration state and transformations relating
  deck coordinates to gantry motor coordinates.
* :class:`ZContact` -- Representation of a calibrated Z contact/reference
  position.
* :class:`AxisScale` -- Conversion information between physical distances and
  controller microsteps.
* :func:`default_axis_scale` -- Construction of the default scale for a
  supported axis.
* :data:`MICROSTEPS_PER_STEP` -- Number of controller microsteps per full
  motor step.
* :data:`MEASURED_AXIS_TRAVEL_MM` -- Reference measured travel values used by
  the geometry and scaling layer.

These objects form the geometry boundary between physical deck-space
coordinates and the lower-level integer units used by the motion controller.
"""

from .calibration import DeckCalibration, ZContact
from .coordinates import DeckPoint
from .transform import AffineTransform2D
from .units import (
    MEASURED_AXIS_TRAVEL_MM,
    MICROSTEPS_PER_STEP,
    AxisScale,
    default_axis_scale,
)

__all__ = [
    "AffineTransform2D",
    "AxisScale",
    "DeckCalibration",
    "DeckPoint",
    "MEASURED_AXIS_TRAVEL_MM",
    "MICROSTEPS_PER_STEP",
    "ZContact",
    "default_axis_scale",
]
