from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from src.hardware.dispatcher import AXES


def _reject_unknown_axes(axes: Dict[str, float]) -> None:
    unknown = {axis.upper() for axis in axes} - AXES
    if unknown:
        raise ValueError(f"Unknown axes: {unknown}. Must be a subset of {AXES}.")


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
