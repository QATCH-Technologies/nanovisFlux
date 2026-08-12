from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeckPoint:
    """A location in deck space, in millimetres, with a conventional origin
    that is independent of where the motors happen to home."""

    x: float
    y: float
    z: float = 0.0

    def __add__(self, other: "DeckPoint") -> "DeckPoint":
        return DeckPoint(self.x + other.x, self.y + other.y, self.z + other.z)
