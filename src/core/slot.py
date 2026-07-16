"""
class Slot:

    slot_id
    virtual corner coordinates for each slot
    available?
    labware
"""

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from src.core.config_schema import SlotSchema

# Index into corners_mm(), which walks front-left -> front-right -> back-right
# -> back-left (clockwise from the front-left corner).
_CORNER_INDEX = {"front_left": 0, "front_right": 1, "back_right": 2, "back_left": 3}


@dataclass
class Slot:
    """Runtime view of one deck slot: its geometry (from SlotSchema) plus
    whatever labware currently occupies it, if any."""

    slot_id: str
    schema: SlotSchema
    labware: Optional[Any] = None

    @property
    def available(self) -> bool:
        return self.labware is None

    @property
    def is_trash(self) -> bool:
        return self.schema.is_trash

    def corners_mm(self) -> List[Tuple[float, float]]:
        """The four XY corners of this slot's footprint in deck mm, starting
        at the front-left corner and proceeding clockwise."""
        x0, y0 = self.schema.x_offset_mm, self.schema.y_offset_mm
        x1, y1 = x0 + self.schema.width_mm, y0 + self.schema.depth_mm
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def corner_mm(self, name: str) -> Tuple[float, float]:
        """One named corner -- 'front_left', 'front_right', 'back_right', or
        'back_left' -- in deck mm. Used during deck calibration, where the
        machine is jogged to a slot's outer corner and the reading is tied
        back to that corner's known deck mm position."""
        if name not in _CORNER_INDEX:
            raise KeyError(f"Unknown corner '{name}'. Must be one of {sorted(_CORNER_INDEX)}.")
        return self.corners_mm()[_CORNER_INDEX[name]]

    def place(self, labware: Any) -> None:
        if not self.available:
            raise RuntimeError(f"Slot '{self.slot_id}' is already occupied by {self.labware!r}.")
        self.labware = labware

    def clear(self) -> None:
        self.labware = None
