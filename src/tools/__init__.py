"""Tool implementations and calibration models for the motion-control stack.

This package defines the tools that can be attached to robot mounts, along
with the geometry and calibration models they use. Tools share the
:class:`Tool` extension interface while exposing tool-specific behavior such
as liquid handling, surface probing, and distance measurement.

The public API includes:

* :class:`Tool` -- base interface for mountable tools.
* :class:`Pipette` -- single- or multi-channel liquid-handling tool.
* :class:`PlungerModel` -- linear volume-to-microstep conversion model.
* :class:`PlungerCalibration` -- empirical bidirectional plunger calibration.
* :class:`PlungerCalibrationPoint` -- individual measured calibration point.
* :class:`TipGeometry` -- physical description of a disposable tip.
* :class:`TipPickup` -- parameters for mechanical tip pickup and seating.
* :class:`TouchProbe` -- conductive probe for surface-height measurements.
* :class:`UltrasonicSensor` -- fixed-position distance-measurement tool.

These names are re-exported at package level so callers can import the
supported tool types and associated models without depending on their
implementation modules.
"""

from .base import Tool
from .pipette import Pipette, PlungerCalibration, PlungerCalibrationPoint, PlungerModel
from .probe import TouchProbe
from .tips import TipGeometry, TipPickup
from .ultrasonic import UltrasonicSensor

__all__ = [
    "Pipette",
    "PlungerCalibration",
    "PlungerCalibrationPoint",
    "PlungerModel",
    "TipGeometry",
    "TipPickup",
    "Tool",
    "TouchProbe",
    "UltrasonicSensor",
]
