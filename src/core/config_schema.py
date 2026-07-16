from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from src.backend.dispatcher import AXES


def _reject_unknown_axes(axes: Dict[str, float]) -> None:
    unknown = {axis.upper() for axis in axes} - AXES
    if unknown:
        raise ValueError(f"Unknown axes: {unknown}. Must be a subset of {AXES}.")


class PhysicalCoordinateSchema(BaseModel):
    """A single raw-step reading across the six physical axes -- the config
    shape of src.core.coordinate.PhysicalCoordinate. Any axis left out
    simply wasn't part of that reading."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None

    def as_steps(self) -> Dict[str, float]:
        axes = {"X": self.x, "Y": self.y, "Z": self.z, "A": self.a, "B": self.b, "C": self.c}
        return {axis: value for axis, value in axes.items() if value is not None}


class AxisCalibrationSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    steps_per_mm: float = Field(gt=0)
    home_offset_mm: float = 0.0


class CalibrationSchema(RootModel[Dict[str, AxisCalibrationSchema]]):
    @field_validator("root")
    @classmethod
    def _validate_axes(
        cls, value: Dict[str, AxisCalibrationSchema]
    ) -> Dict[str, AxisCalibrationSchema]:
        unknown = {axis.upper() for axis in value} - AXES
        if unknown:
            raise ValueError(f"Unknown axes in calibration config: {unknown}")
        return value


class SlotSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    x_offset_mm: float
    y_offset_mm: float
    z_offset_mm: float = 0.0
    width_mm: float = 0.0
    depth_mm: float = 0.0
    height_mm: float = 0.0
    is_trash: bool = False


class DeckLayoutSchema(BaseModel):
    slots: Dict[str, SlotSchema]


class PhysicalEnvelopeSchema(RootModel[List[Dict[str, float]]]):
    """A set of raw-step axis readings taken at the physical travel extremes
    (e.g. the corners of the reachable volume). Each reading need not cover
    every axis -- axes omitted from a corner, or held constant across all
    corners, simply aren't bounds-checked."""

    @field_validator("root")
    @classmethod
    def _validate_corners(cls, value: List[Dict[str, float]]) -> List[Dict[str, float]]:
        if len(value) < 2:
            raise ValueError("Physical envelope requires at least 2 corner readings.")
        for corner in value:
            _reject_unknown_axes(corner)
        return value


class MountOffsetSchema(RootModel[Dict[str, float]]):
    @field_validator("root")
    @classmethod
    def _validate_axes(cls, value: Dict[str, float]) -> Dict[str, float]:
        _reject_unknown_axes(value)
        return value


class MountOffsetsSchema(RootModel[Dict[str, MountOffsetSchema]]):
    pass


class DeckCalibrationSchema(BaseModel):
    """Three calibration readings that fix the deck plane's origin,
    orientation, and scale in raw steps: an origin (steps at deck mm
    (0, 0)) and one reading offset purely along each deck axis. Each
    reading is a physical coordinate across x, y, z, a, b, c."""

    model_config = ConfigDict(frozen=True)

    origin_steps: PhysicalCoordinateSchema
    x_reference_steps: PhysicalCoordinateSchema
    x_reference_mm: float = Field(gt=0)
    y_reference_steps: PhysicalCoordinateSchema
    y_reference_mm: float = Field(gt=0)


class DeckCalibrationPointsSchema(BaseModel):
    """Three raw-step readings taken during the standard deck-calibration
    jog -- cal_point_1 at the corner defining the deck origin, cal_point_2
    offset purely along deck +X, cal_point_3 offset purely along deck +Y --
    each a full physical coordinate (x, y, z, a, b, c).

    Unlike DeckCalibrationSchema, no mm distances are given here: they're
    derived from the deck's own slot geometry (see Deck.calibrate_from_config),
    using the slot/corner each point corresponds to. Defaults match the
    standard 11-slot/trash deck: slot 1's outer front-left corner (origin),
    slot 3's outer front-right corner (+X), slot 10's outer back-left corner
    (+Y)."""

    model_config = ConfigDict(frozen=True)

    cal_point_1: PhysicalCoordinateSchema
    cal_point_2: PhysicalCoordinateSchema
    cal_point_3: PhysicalCoordinateSchema
    origin_slot_id: str = "1"
    x_reference_slot_id: str = "3"
    y_reference_slot_id: str = "10"
    origin_corner: str = "front_left"
    x_reference_corner: str = "front_right"
    y_reference_corner: str = "back_left"
