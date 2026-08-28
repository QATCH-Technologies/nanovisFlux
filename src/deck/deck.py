"""Deck layout, slot geometry, and physical calibration-reference models.

This module defines the geometric representation of a robot deck and the
regions, fixtures, and reference points associated with it. Deck contents are
addressed semantically by slot name rather than by a fixed numbering scheme,
allowing the same abstractions to represent labware locations, trash areas,
tool docks, and other physical regions.

Slot geometry includes optional footprints, walls, and interior obstacles.
These properties are currently descriptive and are primarily consumed by
visualization and layout code rather than motion planning.

The module also provides helpers for resolving slot corners and inset
positions in deck coordinates, as well as named calibration marks that can be
used to establish the relationship between deck-space and motor-space
coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ..geometry.coordinates import DeckPoint


@dataclass
class SlotObstacle:
    """Describe a solid fixture occupying part of a deck slot.

    An obstacle is defined relative to the slot's origin and represents a
    rectangular solid extending upward from the slot floor. The geometry is
    currently descriptive and visualization-oriented; motion planning does not
    yet use these obstacles for collision avoidance.

    Attributes:
        offset: ``(x, y)`` position of the obstacle relative to the slot
            origin, in millimeters.
        size: ``(width, height)`` footprint of the obstacle, in millimeters.
        height_mm: Height of the obstacle above the slot floor, in millimeters.
    """

    offset: tuple  # (x, y) mm from the slot origin
    size: tuple  # (w, h) mm footprint
    height_mm: float  # solid from the slot floor up to this height


@dataclass
class Slot:
    """Represent a named physical region of the robot deck.

    A slot is a generic deck region that may contain labware, a trash
    container, a tool dock, or another physical fixture. It is not tied to a
    particular numbering convention.

    Optional wall and obstacle geometry can describe physically bounded or
    obstructed regions such as an integrated trash bin. This geometry is
    currently descriptive and may be used by visualization without imposing
    motion-planning constraints.

    Attributes:
        name: Unique name used to address the slot.
        origin: Deck-space reference point corresponding to the slot's
            front-left corner.
        size: ``(width, height)`` footprint of the slot in millimeters.
        wall_height_mm: Height of any perimeter walls above the slot floor.
            Defaults to ``0.0`` for an open, flat slot.
        wall_thickness_mm: Thickness of the slot's perimeter walls in
            millimeters.
        obstacles: Interior solid fixtures associated with the slot.
    """

    name: str
    origin: DeckPoint  # deck-space reference corner
    size: tuple = (0.0, 0.0)  # (w, h) mm, optional footprint
    wall_height_mm: float = 0.0
    wall_thickness_mm: float = 0.0
    obstacles: list = field(default_factory=list)  # list[SlotObstacle]


class Corner(Enum):
    """Identify a geometric corner of a slot footprint.

    Corner names follow the deck coordinate convention in which the front
    edge corresponds to minimum Y and the rear edge to maximum Y. Left and
    right correspond to minimum and maximum X respectively.

    Members:
        FRONT_LEFT: Minimum-X, minimum-Y corner.
        FRONT_RIGHT: Maximum-X, minimum-Y corner.
        REAR_LEFT: Minimum-X, maximum-Y corner.
        REAR_RIGHT: Maximum-X, maximum-Y corner.
    """

    FRONT_LEFT = "front_left"
    FRONT_RIGHT = "front_right"
    REAR_LEFT = "rear_left"
    REAR_RIGHT = "rear_right"


def corner_point(slot: Slot, corner: Corner) -> DeckPoint:
    """Return the requested geometric corner of a slot.

    The returned point is computed from the slot's origin and footprint. The
    origin itself represents the front-left corner, while the slot dimensions
    determine the offsets required for the right and rear corners.

    Args:
        slot: Slot whose footprint should be queried.
        corner: Corner of the slot to resolve.

    Returns:
        DeckPoint: Deck-space coordinates of the requested slot corner.

    Raises:
        ValueError: If the slot has no non-zero footprint dimensions.
    """
    if not slot.size or not slot.size[0] or not slot.size[1]:
        raise ValueError(f"slot {slot.name!r} has no footprint size; " "corners need slot.size")
    w, h = slot.size
    x = slot.origin.x if corner in (Corner.FRONT_LEFT, Corner.REAR_LEFT) else slot.origin.x + w
    y = slot.origin.y if corner in (Corner.FRONT_LEFT, Corner.FRONT_RIGHT) else slot.origin.y + h
    return DeckPoint(x, y, slot.origin.z)


def inset_corner_point(
    slot: Slot,
    corner: Corner,
    inset_x_mm: float,
    inset_y_mm: float,
) -> DeckPoint:
    """Return a point inset from a slot corner toward the slot interior.

    The signs of the X and Y offsets are selected automatically from the
    requested corner so that positive inset distances always move toward the
    interior of the slot.

    Args:
        slot: Slot whose corner should be used as the reference.
        corner: Corner from which the inset should be measured.
        inset_x_mm: Inset distance along X, in millimeters.
        inset_y_mm: Inset distance along Y, in millimeters.

    Returns:
        DeckPoint: Deck-space position of the inset point.

    Raises:
        ValueError: If the slot has no non-zero footprint dimensions.
    """
    pt = corner_point(slot, corner)
    dx = inset_x_mm if corner in (Corner.FRONT_LEFT, Corner.REAR_LEFT) else -inset_x_mm
    dy = inset_y_mm if corner in (Corner.FRONT_LEFT, Corner.FRONT_RIGHT) else -inset_y_mm
    return DeckPoint(pt.x + dx, pt.y + dy, pt.z)


@dataclass(frozen=True)
class CalibrationMark:
    """Describe a fixed physical reference used for deck calibration.

    A calibration mark identifies a known deck-space location associated with
    a named slot and slot corner. The mark describes the expected physical
    location; measuring the corresponding motor position is the responsibility
    of the calibration procedure that uses the mark.

    Attributes:
        name: Human-readable identifier for the calibration mark.
        slot: Name of the slot containing the mark.
        corner: Slot corner used to define the mark's location.
        point: Exact deck-space coordinates of the physical reference.
    """

    name: str
    slot: str
    corner: Corner
    point: DeckPoint


@dataclass
class Deck:
    """Represent the configured collection of named deck slots.

    ``Deck`` provides semantic access to physical regions of the robot's
    workspace. Slots are stored by name and may represent standard labware
    positions, trash containers, tool docks, or other deck fixtures.

    Optional margin and enclosure metadata describe the physical deck and
    robot frame for visualization and layout purposes. They do not currently
    impose motion or placement constraints.

    Attributes:
        slots: Mapping from slot names to :class:`Slot` objects.
        margins: Optional clearances between the deck plate boundary and the
            slot layout, in millimeters.
        frame_margins: Optional clearances between the deck plate and the
            robot's outer frame or chassis, in millimeters.
        enclosure_height_mm: Physical height of the robot enclosure or frame,
            in millimeters.
        calibration_marks: Mapping from calibration-mark names to
            :class:`CalibrationMark` objects.
    """

    slots: dict = field(default_factory=dict)
    margins: dict | None = None
    frame_margins: dict | None = None
    enclosure_height_mm: float | None = None
    calibration_marks: dict = field(default_factory=dict)  # name -> CalibrationMark

    def add(self, slot: Slot) -> Slot:
        """Add a slot to the deck by its name.

        An existing slot with the same name is replaced.

        Args:
            slot: Slot to add to the deck.

        Returns:
            Slot: The same slot instance that was added.
        """
        self.slots[slot.name] = slot
        return slot

    def __getitem__(self, name: str) -> Slot:
        """Return a deck slot by name.

        Args:
            name: Name of the slot to retrieve.

        Returns:
            Slot: The corresponding slot.

        Raises:
            KeyError: If no slot with ``name`` exists.
        """
        return self.slots[name]

    @classmethod
    def grid(
        cls,
        *,
        rows: int,
        cols: int,
        origin: DeckPoint,
        pitch: tuple,
        names=None,
    ) -> Deck:
        """Construct a regular rectangular grid of deck slots.

        Slots are generated in row-major order from the supplied origin. Each
        successive column advances by ``pitch[0]`` along X, and each successive
        row advances by ``pitch[1]`` along Y.

        When explicit names are not supplied, slots are named sequentially
        starting at ``"1"``.

        Args:
            rows: Number of slot rows to create.
            cols: Number of slot columns to create.
            origin: Deck-space position of the first slot.
            pitch: ``(dx, dy)`` spacing between adjacent slot origins, in
                millimeters.
            names: Optional sequence of slot names in row-major order. When
                omitted, numeric names are generated automatically.

        Returns:
            Deck: A newly constructed deck containing the requested slot grid.
        """
        deck = cls()
        i = 1
        for r in range(rows):
            for c in range(cols):
                name = str(i) if names is None else names[i - 1]
                pos = DeckPoint(origin.x + c * pitch[0], origin.y + r * pitch[1])
                deck.add(Slot(name=name, origin=pos))
                i += 1
        return deck
