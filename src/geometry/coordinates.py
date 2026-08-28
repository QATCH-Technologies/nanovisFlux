"""Coordinate primitives for representing physical positions in deck space.

This module defines the lightweight coordinate types used by the geometry,
calibration, and motion layers. Deck-space coordinates are expressed in
millimeters and remain independent of the robot's motor-space origin or
current homed position.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeckPoint:
    """Represent a physical position in robot deck space.

    A ``DeckPoint`` uses a fixed, physical coordinate system whose origin is
    independent of the current motor position or homing state. Coordinates
    are expressed in millimeters.

    The type is immutable so deck coordinates can be safely used as values
    throughout calibration and motion planning. Points may also be added
    component-wise to apply positional offsets.

    Attributes:
        x: Horizontal deck coordinate along the X direction, in millimeters.
        y: Horizontal deck coordinate along the Y direction, in millimeters.
        z: Vertical deck coordinate, in millimeters. Defaults to ``0.0``.
    """

    x: float
    y: float
    z: float = 0.0

    def __add__(self, other: DeckPoint) -> DeckPoint:
        """Return the component-wise sum of two deck-space points.

        Args:
            other: Deck-space point whose coordinates are added to this point.

        Returns:
            DeckPoint: A new point whose X, Y, and Z coordinates are the sums of
            the corresponding coordinates of the two operands.
        """
        return DeckPoint(self.x + other.x, self.y + other.y, self.z + other.z)
