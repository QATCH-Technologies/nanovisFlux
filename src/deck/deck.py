from __future__ import annotations
from dataclasses import dataclass, field
from ..geometry.coordinates import DeckPoint


@dataclass
class SlotObstacle:
    """A solid interior fixture inside a slot -- e.g. a raised pedestal cast
    into a trash bin's floor. ``offset`` is (x, y) mm from the slot's own
    origin (its front-left corner, same convention as ``Slot.origin``);
    everything inside the slot's walls that isn't an obstacle is empty.
    Purely descriptive/visual -- nothing in motion planning consults this
    yet, so it doesn't guard against a tip being driven into one."""
    offset: tuple                           # (x, y) mm from the slot origin
    size: tuple                             # (w, h) mm footprint
    height_mm: float                        # solid from the slot floor up to this height


@dataclass
class Slot:
    """A generic named region on the deck. Not tied to any numbering scheme:
    a slot can hold labware, a trash, a tool dock -- whatever you need.

    ``wall_height_mm``/``wall_thickness_mm`` describe a physical bin built
    into the slot (e.g. the trash slot's raised walls) -- 0 for a flat open
    slot, which is most of them. Walls are drawn flush with the slot's own
    footprint (``origin``/``size``), running around its full perimeter.
    ``obstacles`` lists any solid interior fixtures (see ``SlotObstacle``).
    Like ``wall_height_mm``, purely descriptive/visual today.
    """
    name: str
    origin: DeckPoint                       # deck-space reference corner
    size: tuple = (0.0, 0.0)                # (w, h) mm, optional footprint
    wall_height_mm: float = 0.0
    wall_thickness_mm: float = 0.0
    obstacles: list = field(default_factory=list)   # list[SlotObstacle]


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

    ``enclosure_height_mm`` is the physical machine enclosure's own height
    (floor to the top of its frame/housing) -- also purely descriptive,
    used only to draw the frame with a real height in the 3D deck view
    instead of a flat outline.
    """
    slots: dict = field(default_factory=dict)
    margins: dict | None = None
    frame_margins: dict | None = None
    enclosure_height_mm: float | None = None

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
