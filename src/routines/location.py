"""Location abstractions for resolving named labware references into deck coordinates.

This module provides lightweight, routine-friendly representations of
locations that can be resolved against a configured robot at execution time.
Routines can therefore target semantic objects such as wells and deck slots
rather than embedding raw :class:`DeckPoint` coordinates.

The module defines:

* :class:`Location` -- Base interface for objects that resolve to a deck-space
  position.
* :class:`WellLocation` -- Resolves a named well in loaded labware at a
  specified geometric reference height, with optional clearance and positional
  offset.
* :class:`SlotLocation` -- Resolves a deck slot's origin with an optional
  positional offset.
* :class:`PointLocation` -- Wraps an explicit :class:`DeckPoint` for cases
  where a literal coordinate is required.

Location resolution is intentionally deferred until a robot is available so
that labware placement, deck configuration, calibration, and other runtime
state can determine the final deck-space coordinate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..geometry.coordinates import DeckPoint

if TYPE_CHECKING:
    from ..robot import Robot


class Location:
    """Abstract interface for a location that resolves to deck coordinates.

    A location provides a semantic reference that can be resolved against a
    configured robot at execution time. This allows routines to refer to
    labware wells, deck slots, or explicit points without embedding robot-
    specific coordinates.

    Subclasses must implement :meth:`resolve`.

    Methods:
        resolve: Resolve the location to a deck-space coordinate for a robot.

    Note:
        Resolution is intentionally deferred until a robot instance is
        available so that the result can reflect the robot's current deck
        configuration, labware placement, and calibration state.
    """

    def resolve(self, robot: Robot) -> DeckPoint:
        raise NotImplementedError


@dataclass
class WellLocation(Location):
    """Semantic reference to a named well in loaded labware.

    The well is resolved against the robot at execution time using a named
    geometric reference within the well. Supported references include
    `"top"` for the well opening or rim, `"bottom"` for the deepest point,
    and `"clearance"` for a safe standoff above the bottom. The default
    `"clearance"` reference is intended for normal aspirate and dispense
    operations.

    An optional clearance value can override the labware's default clearance
    behavior. An additional positional offset can then be applied to the
    resolved point for fine-grained adjustment.

    Attributes:
        labware: Name of the loaded labware containing the target well.
        well: Name or identifier of the target well within the labware.
        ref: Geometric reference used to resolve the well. Typically `"top"`,
            `"bottom"`, or `"clearance"`.
        clearance_mm: Optional clearance distance, in millimeters, used when
            resolving the well's clearance reference.
        offset: Additional deck-space displacement applied after resolving the
            well reference. Defaults to the zero vector.

    Note:
        Well geometry and labware placement are resolved at runtime, allowing
        the same routine to operate with different deck configurations.
    """

    labware: str
    well: str
    ref: str = "clearance"
    clearance_mm: float | None = None
    offset: DeckPoint = field(default_factory=lambda: DeckPoint(0, 0, 0))

    def resolve(self, robot) -> DeckPoint:
        """Resolve the referenced well to a deck-space coordinate.

        The well is first resolved through the named labware using the requested
        geometric reference and optional clearance. The configured offset is then
        added to the resulting deck coordinate.

        Args:
            robot: Configured robot instance containing the referenced labware.

        Returns:
            DeckPoint: Deck-space coordinate corresponding to the requested well
            reference and positional offset.

        Raises:
            KeyError: If `labware` does not identify loaded labware on the
                robot.
            ValueError: If the well or reference configuration is invalid and the
                underlying labware implementation rejects it.
        """
        base = robot.labware[self.labware].well(
            self.well, ref=self.ref, clearance_mm=self.clearance_mm
        )
        return base + self.offset


@dataclass
class SlotLocation(Location):
    """Semantic reference to a deck slot.

    The location resolves to the slot's configured origin and optionally
    applies a positional offset. This provides a routine-friendly way to
    target deck locations without embedding literal coordinates.

    Attributes:
        slot: Name or identifier of the deck slot.
        offset: Additional deck-space displacement applied to the slot origin.
            Defaults to the zero vector.

    """

    slot: str
    offset: DeckPoint = field(default_factory=lambda: DeckPoint(0, 0, 0))

    def resolve(self, robot) -> DeckPoint:
        """Resolve the slot reference to a deck-space coordinate.

        The configured slot origin is obtained from the robot's deck and then
        adjusted by the location's positional offset.

        Args:
            robot: Configured robot instance containing the referenced deck slot.

        Returns:
            DeckPoint: Deck-space coordinate of the slot origin plus `offset`.

        Raises:
            KeyError: If `slot` does not identify a configured deck slot on the
                robot.
            RuntimError: If the deck is not configured.
        """
        deck = robot.deck
        if deck is None:
            raise RuntimeError("Cannot resolve slot location without a configured deck")
        return deck[self.slot].origin + self.offset


@dataclass
class PointLocation(Location):
    """Location wrapper for an explicit deck-space coordinate.

    This class provides an escape hatch for cases where a routine must use a
    literal coordinate rather than a semantic labware or deck reference.

    Attributes:
        point: Explicit deck-space coordinate represented by this location.
    """

    point: DeckPoint

    def resolve(self, robot: Robot) -> DeckPoint:
        """Return the stored deck-space coordinate.

        The robot is accepted for interface compatibility with other
        :class:`Location` implementations but is not used during resolution.

        Args:
            robot: Robot instance used by the common location-resolution
                interface. It is ignored for explicit point locations.

        Returns:
            DeckPoint: The explicit coordinate stored in `point`.
        """
        return self.point
