import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from pydantic import BaseModel

from src.core.config_schema import DeckLayoutSchema, SlotSchema
from src.utils.logger import logger

DEFAULT_DECK_LAYOUT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "deck_layout.json"
)


class DeckLocation(BaseModel):
    slot_id: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    z_mm: float = 0.0


def build_grid_layout(
    rows: int,
    cols: int,
    slot_width_mm: float,
    slot_depth_mm: float,
    gap_mm: float = 0.0,
    x_pitch_mm: Optional[float] = None,
    y_pitch_mm: Optional[float] = None,
    origin_x_mm: float = 0.0,
    origin_y_mm: float = 0.0,
    trash_position: Optional[Tuple[int, int]] = None,
    trash_slot_id: str = "trash",
    trash_width_mm: Optional[float] = None,
    trash_depth_mm: Optional[float] = None,
) -> Dict[str, SlotSchema]:
    """Lays out `rows` x `cols` slots on an evenly spaced grid, numbered "1"
    upward row-major starting at the bottom-left (row 0, col 0), with one
    cell reserved for a trash slot instead of a number.

    `trash_position` is (row, col), 0-indexed from the bottom-left, and
    defaults to the top-right cell -- the standard OT-2-style deck
    convention. Pitch defaults to slot size plus `gap_mm` (the physical
    separator between adjacent slots); pass explicit `x_pitch_mm`/
    `y_pitch_mm` to override directly. The trash slot's own footprint can be
    sized independently via `trash_width_mm`/`trash_depth_mm` (defaults to
    the standard slot size) -- its origin still sits at its cell's grid
    position, so a larger footprint extends into the deck's outer margin
    rather than displacing neighboring slots.
    """
    x_pitch_mm = slot_width_mm + gap_mm if x_pitch_mm is None else x_pitch_mm
    y_pitch_mm = slot_depth_mm + gap_mm if y_pitch_mm is None else y_pitch_mm
    trash_width_mm = slot_width_mm if trash_width_mm is None else trash_width_mm
    trash_depth_mm = slot_depth_mm if trash_depth_mm is None else trash_depth_mm
    if trash_position is None:
        trash_position = (rows - 1, cols - 1)

    slots: Dict[str, SlotSchema] = {}
    next_id = 1
    for row in range(rows):
        for col in range(cols):
            is_trash = (row, col) == trash_position
            slot_id = trash_slot_id if is_trash else str(next_id)
            if not is_trash:
                next_id += 1
            slots[slot_id] = SlotSchema(
                x_offset_mm=origin_x_mm + col * x_pitch_mm,
                y_offset_mm=origin_y_mm + row * y_pitch_mm,
                width_mm=trash_width_mm if is_trash else slot_width_mm,
                depth_mm=trash_depth_mm if is_trash else slot_depth_mm,
                is_trash=is_trash,
            )
    return slots


class Deck:
    def __init__(self, slots: Dict[str, SlotSchema]):
        self._slots = slots

    @classmethod
    def from_config(cls, deck_layout_data: dict) -> "Deck":
        validated = DeckLayoutSchema.model_validate(deck_layout_data)
        logger.debug(f"Loaded deck layout with slots: {sorted(validated.slots.keys())}")
        return cls(validated.slots)

    @classmethod
    def load(cls, path: Union[str, Path] = DEFAULT_DECK_LAYOUT_PATH) -> "Deck":
        with open(path, "r") as file:
            return cls.from_config(json.load(file))

    @classmethod
    def standard_grid(cls, **grid_kwargs) -> "Deck":
        """Builds a Deck directly from build_grid_layout()'s parameters --
        see that function for the full argument list."""
        slots = build_grid_layout(**grid_kwargs)
        return cls(slots)

    def get_slot(self, slot_id: str) -> SlotSchema:
        if slot_id not in self._slots:
            raise KeyError(f"No slot '{slot_id}' defined in deck layout.")
        return self._slots[slot_id]

    def slot_ids(self) -> List[str]:
        return list(self._slots.keys())

    def trash_slot_ids(self) -> List[str]:
        return [slot_id for slot_id, slot in self._slots.items() if slot.is_trash]

    def resolve_mm(self, location: DeckLocation) -> Dict[str, float]:
        slot = self.get_slot(location.slot_id)
        return {
            "X": slot.x_offset_mm + location.x_mm,
            "Y": slot.y_offset_mm + location.y_mm,
            "Z": slot.z_offset_mm + location.z_mm,
        }
