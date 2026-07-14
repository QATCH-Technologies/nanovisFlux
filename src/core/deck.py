import json
from pathlib import Path
from typing import Dict, Union

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

    def get_slot(self, slot_id: str) -> SlotSchema:
        if slot_id not in self._slots:
            raise KeyError(f"No slot '{slot_id}' defined in deck layout.")
        return self._slots[slot_id]

    def resolve_mm(self, location: DeckLocation) -> Dict[str, float]:
        slot = self.get_slot(location.slot_id)
        return {
            "X": slot.x_offset_mm + location.x_mm,
            "Y": slot.y_offset_mm + location.y_mm,
            "Z": slot.z_offset_mm + location.z_mm,
        }
