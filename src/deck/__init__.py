"""Labware and deck-layout models for physical workspace representation.

This package defines the static geometry and layout abstractions used to
describe a robot's deck, its slots, and the labware occupying those slots.

The public API includes:

* :class:`Deck` -- Represents the configured deck and its available slots.
* :class:`Slot` -- Describes an individual deck slot and its geometry.
* :class:`SlotObstacle` -- Represents regions that constrain motion within a
  slot or deck area.
* :class:`CalibrationMark` -- Defines a physical reference used for deck
  calibration.
* :class:`Corner` -- Identifies a slot or deck corner for geometric
  operations.
* :func:`corner_point` -- Resolves a named corner to a deck-space point.
* :func:`inset_corner_point` -- Resolves an inset position relative to a
  corner.
* :class:`Labware` -- Represents a placed piece of laboratory labware.
* :class:`Well` -- Represents an individual well within labware.
* :class:`WellGeometry` -- Describes the physical geometry of a well.
* :class:`WellShape` -- Identifies the geometric shape of a well.
* :class:`BottomShape` -- Describes the geometry of a well bottom.
* :class:`GridLabwareDefinition` -- Defines labware arranged on a regular
  well grid.
* :class:`WellPlateDefinition` -- Defines a multi-well plate.
* :class:`TipRackDefinition` -- Defines a pipette-tip rack.
* :class:`ReservoirDefinition` -- Defines a reservoir-style labware.

These models separate labware and deck geometry from runtime robot state,
allowing locations and motion routines to resolve physical coordinates from
semantic objects such as slots and wells.
"""

from .deck import (
    CalibrationMark,
    Corner,
    Deck,
    Slot,
    SlotObstacle,
    corner_point,
    inset_corner_point,
)
from .definitions import (
    GridLabwareDefinition,
    ReservoirDefinition,
    TipRackDefinition,
    WellPlateDefinition,
)
from .labware import BottomShape, Labware, Well, WellGeometry, WellShape

__all__ = [
    "BottomShape",
    "CalibrationMark",
    "Corner",
    "Deck",
    "GridLabwareDefinition",
    "Labware",
    "ReservoirDefinition",
    "Slot",
    "SlotObstacle",
    "TipRackDefinition",
    "Well",
    "WellGeometry",
    "WellPlateDefinition",
    "WellShape",
    "corner_point",
    "inset_corner_point",
]
