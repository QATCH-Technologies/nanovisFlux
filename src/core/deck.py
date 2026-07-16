"""
class Deck:
    lays out the slots
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from src.core.config_schema import DeckCalibrationPointsSchema, DeckLayoutSchema, SlotSchema
from src.core.coordinate import PhysicalCoordinate
from src.core.coordinate_system import DeckCalibration
from src.core.slot import Slot
from src.utils.logger import logger

DEFAULT_DECK_LAYOUT_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "deck_layout.json"


@dataclass(frozen=True)
class DeckLocation:
    """A position to move to, expressed as an offset in mm from the origin
    of a named deck slot."""

    slot_id: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    z_mm: float = 0.0


def build_grid_layout(
    rows: int,
    cols: int,
    slot_width_mm: float,
    slot_depth_mm: float,
    x_pitch_mm: Optional[float] = None,
    y_pitch_mm: Optional[float] = None,
    gap_mm: float = 0.0,
    trash_position: Optional[Tuple[int, int]] = None,
    trash_width_mm: Optional[float] = None,
    trash_depth_mm: Optional[float] = None,
) -> Dict[str, SlotSchema]:
    """Lays out `rows` x `cols` slots in a grid from the bottom-left corner
    (row 0, col 0 -> deck mm (0, 0)), numbered 1..N-1 in row-major order,
    skipping whichever cell hosts the trash (by default the top-right
    corner -- the last cell in that order).

    x_pitch_mm/y_pitch_mm default to the slot footprint plus gap_mm; an
    explicit pitch overrides gap_mm entirely rather than adding to it.
    """
    x_pitch = x_pitch_mm if x_pitch_mm is not None else slot_width_mm + gap_mm
    y_pitch = y_pitch_mm if y_pitch_mm is not None else slot_depth_mm + gap_mm
    trash_row, trash_col = trash_position if trash_position is not None else (rows - 1, cols - 1)

    slots: Dict[str, SlotSchema] = {}
    next_id = 1
    for row in range(rows):
        for col in range(cols):
            x_offset = col * x_pitch
            y_offset = row * y_pitch
            if (row, col) == (trash_row, trash_col):
                slots["trash"] = SlotSchema(
                    x_offset_mm=x_offset,
                    y_offset_mm=y_offset,
                    width_mm=trash_width_mm if trash_width_mm is not None else slot_width_mm,
                    depth_mm=trash_depth_mm if trash_depth_mm is not None else slot_depth_mm,
                    is_trash=True,
                )
            else:
                slots[str(next_id)] = SlotSchema(
                    x_offset_mm=x_offset,
                    y_offset_mm=y_offset,
                    width_mm=slot_width_mm,
                    depth_mm=slot_depth_mm,
                )
                next_id += 1
    return slots


class Deck:
    def __init__(self, slots: Dict[str, SlotSchema]):
        self._slots = dict(slots)

    @classmethod
    def from_config(cls, data: dict) -> "Deck":
        validated = DeckLayoutSchema.model_validate(data)
        logger.debug(f"Loaded deck layout with slots: {sorted(validated.slots.keys())}")
        return cls(validated.slots)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Deck":
        with open(path, "r") as file:
            data = json.load(file)
        deck = cls.from_config(data)
        logger.debug(f"Loaded deck layout from {path}")
        return deck

    @classmethod
    def standard_grid(
        cls, rows: int, cols: int, slot_width_mm: float, slot_depth_mm: float, **kwargs
    ) -> "Deck":
        return cls(build_grid_layout(rows, cols, slot_width_mm, slot_depth_mm, **kwargs))

    def get_slot(self, slot_id: str) -> SlotSchema:
        if slot_id not in self._slots:
            raise KeyError(f"No slot '{slot_id}' defined on this deck.")
        return self._slots[slot_id]

    def slot_view(self, slot_id: str) -> Slot:
        """A richer runtime Slot wrapper (availability/labware tracking) for
        a given slot_id, built fresh from this deck's static geometry."""
        return Slot(slot_id=slot_id, schema=self.get_slot(slot_id))

    def known_slots(self) -> List[str]:
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

    def calibrate(
        self,
        origin_slot_id: str,
        origin: PhysicalCoordinate,
        x_reference_slot_id: str,
        x_reference: PhysicalCoordinate,
        y_reference_slot_id: str,
        y_reference: PhysicalCoordinate,
        origin_corner: str = "front_left",
        x_reference_corner: str = "front_right",
        y_reference_corner: str = "back_left",
    ) -> DeckCalibration:
        """Builds a DeckCalibration from three raw-step corner readings taken
        during a calibration jog -- each a PhysicalCoordinate (x, y, z, a, b,
        c) -- using this deck's own slot geometry to resolve each reading's
        deck-mm position, with no manual mm bookkeeping required.

        Matches the standard procedure: jog to the outer front-left corner of
        the slot that defines the deck origin (its mm position must be
        (0, 0)), then to the outer front-right corner of a slot in that same
        row (pure +X offset), then to the outer back-left corner of a slot in
        that same column (pure +Y offset). E.g. on an 11-slot/trash deck
        where slot 1 sits at the front-left: origin_slot_id="1",
        x_reference_slot_id="3", y_reference_slot_id="10".
        """
        origin_mm = self.slot_view(origin_slot_id).corner_mm(origin_corner)
        if origin_mm != (0.0, 0.0):
            raise ValueError(
                f"Slot '{origin_slot_id}' corner '{origin_corner}' is at deck mm {origin_mm}, "
                "not (0, 0) -- pick the slot/corner that defines this deck's virtual origin."
            )

        x_reference_mm, x_reference_row = self.slot_view(x_reference_slot_id).corner_mm(
            x_reference_corner
        )
        if x_reference_row != 0.0:
            raise ValueError(
                f"Slot '{x_reference_slot_id}' corner '{x_reference_corner}' is not in the "
                f"origin's row (deck y={x_reference_row}, expected 0) -- it must be offset "
                "purely along X."
            )

        y_reference_col, y_reference_mm = self.slot_view(y_reference_slot_id).corner_mm(
            y_reference_corner
        )
        if y_reference_col != 0.0:
            raise ValueError(
                f"Slot '{y_reference_slot_id}' corner '{y_reference_corner}' is not in the "
                f"origin's column (deck x={y_reference_col}, expected 0) -- it must be offset "
                "purely along Y."
            )

        return DeckCalibration.from_three_points(
            origin_steps=origin.as_steps(),
            x_reference_steps=x_reference.as_steps(),
            x_reference_mm=x_reference_mm,
            y_reference_steps=y_reference.as_steps(),
            y_reference_mm=y_reference_mm,
        )

    def calibrate_from_config(self, data: dict) -> DeckCalibration:
        """Builds a DeckCalibration from three named calibration-point
        readings (cal_point_1/2/3, each a raw physical coordinate across
        x, y, z, a, b, c) plus which slot/corner each one corresponds to --
        this deck's own geometry supplies the mm distances, so none need be
        specified by hand. See DeckCalibrationPointsSchema for the config
        shape and its defaults."""
        validated = DeckCalibrationPointsSchema.model_validate(data)
        return self.calibrate(
            origin_slot_id=validated.origin_slot_id,
            origin=PhysicalCoordinate.from_steps(validated.cal_point_1.as_steps()),
            x_reference_slot_id=validated.x_reference_slot_id,
            x_reference=PhysicalCoordinate.from_steps(validated.cal_point_2.as_steps()),
            y_reference_slot_id=validated.y_reference_slot_id,
            y_reference=PhysicalCoordinate.from_steps(validated.cal_point_3.as_steps()),
            origin_corner=validated.origin_corner,
            x_reference_corner=validated.x_reference_corner,
            y_reference_corner=validated.y_reference_corner,
        )
