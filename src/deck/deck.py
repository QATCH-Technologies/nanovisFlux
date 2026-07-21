from __future__ import annotations
from dataclasses import dataclass, field
from ..geometry.coordinates import DeckPoint


@dataclass
class Slot:
    """A generic named region on the deck. Not tied to any numbering scheme:
    a slot can hold labware, a trash, a tool dock -- whatever you need."""
    name: str
    origin: DeckPoint                       # deck-space reference corner
    size: tuple = (0.0, 0.0)                # (w, h) mm, optional footprint


@dataclass
class Deck:
    """A generic collection of slots addressed by name.

    ``margins`` is purely descriptive (never consulted for motion/placement):
    the clearance from the plate's outer edge to the slot grid, keyed
    "front"/"left"/"right"/"rear"/"oversized" in mm -- "oversized" applies to
    any slot whose footprint differs from the deck's most common slot size
    (e.g. a bigger trash slot sitting close to the plate edge). Only used to
    draw the plate boundary; a deck built without it renders none.

    ``frame_margins`` is the next layer out: the clearance from the deck
    *plate*'s edge to the robot's outer frame/chassis, keyed
    "front"/"left"/"right"/"rear" in mm. Also purely descriptive.
    """
    slots: dict = field(default_factory=dict)
    margins: dict | None = None
    frame_margins: dict | None = None

    def add(self, slot: Slot) -> Slot:
        self.slots[slot.name] = slot
        return slot

    def __getitem__(self, name: str) -> Slot:
        return self.slots[name]

    @classmethod
    def grid(cls, *, rows: int, cols: int, origin: DeckPoint,
             pitch: tuple, names=None) -> "Deck":
        """Build a regular grid of slots. `pitch` is (dx, dy) in mm between
        slot origins. Names default to 1..rows*cols, row-major from origin."""
        deck = cls()
        i = 1
        for r in range(rows):
            for c in range(cols):
                name = str(i) if names is None else names[i - 1]
                pos = DeckPoint(origin.x + c * pitch[0], origin.y + r * pitch[1])
                deck.add(Slot(name=name, origin=pos))
                i += 1
        return deck
