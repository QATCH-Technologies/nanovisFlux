"""Public routine-building API for semantic robot operations.

This package provides the high-level abstractions used to construct,
inspect, and execute robot routines without requiring callers to work
directly with raw deck coordinates or low-level hardware commands.

The public API is organized around three core concepts:

* :class:`Location` and its concrete implementations -- Semantic references
  to wells, deck slots, or explicit deck coordinates.
* :class:`Step` and its concrete implementations -- Individual executable
  robot operations such as movement, liquid handling, tip manipulation,
  mount switching, delays, and comments.
* :class:`Routine` -- An ordered collection of steps that can be inspected
  through a dry run and executed against a configured robot.

Additional helpers such as :class:`TipSequence` and the location abstractions
allow routines to remain independent of the robot's runtime deck
configuration. Locations are resolved only when their corresponding steps
execute, while mount selection can change dynamically during routine
execution through :class:`SwitchMountStep`.

The names listed in `__all__` constitute the intended public interface of
this package.
"""

from .location import Location, PointLocation, SlotLocation, WellLocation
from .routine import Routine
from .steps import (
    AspirateStep,
    BlowOutStep,
    CommentStep,
    DelayStep,
    DispenseStep,
    DropTipStep,
    HomeStep,
    MoveStep,
    PickUpTipStep,
    Step,
    SwitchMountStep,
)
from .tip_sequence import TipSequence

__all__ = [
    "AspirateStep",
    "BlowOutStep",
    "CommentStep",
    "DelayStep",
    "DispenseStep",
    "DropTipStep",
    "HomeStep",
    "Location",
    "MoveStep",
    "PickUpTipStep",
    "PointLocation",
    "Routine",
    "SlotLocation",
    "Step",
    "SwitchMountStep",
    "TipSequence",
    "WellLocation",
]
