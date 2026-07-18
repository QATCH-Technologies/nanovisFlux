from __future__ import annotations
from dataclasses import dataclass
from ..geometry.coordinates import DeckPoint


class Location:
    """Something that resolves to a deck-space point, given the robot. Lets
    routines be written against slots and wells, not raw coordinates."""
    def resolve(self, robot) -> DeckPoint:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass
class WellLocation(Location):
    """A named well of a loaded labware, resolved at a named reference
    height derived from the well's geometry: "top" (opening/rim), "bottom"
    (deepest point), or "clearance" (a safe standoff above the bottom -- the
    default, and what aspirate/dispense should normally use). ``offset`` is
    an escape-hatch fine-tuning applied after that resolution."""
    labware: str
    well: str
    ref: str = "clearance"
    clearance_mm: float | None = None
    offset: DeckPoint = DeckPoint(0, 0, 0)

    def resolve(self, robot) -> DeckPoint:
        base = robot.labware[self.labware].well(
            self.well, ref=self.ref, clearance_mm=self.clearance_mm)
        return base + self.offset


@dataclass
class SlotLocation(Location):
    """A deck slot's reference corner, plus an optional offset."""
    slot: str
    offset: DeckPoint = DeckPoint(0, 0, 0)

    def resolve(self, robot) -> DeckPoint:
        return robot.deck[self.slot].origin + self.offset


@dataclass
class PointLocation(Location):
    """A literal deck point (escape hatch)."""
    point: DeckPoint

    def resolve(self, robot) -> DeckPoint:
        return self.point
