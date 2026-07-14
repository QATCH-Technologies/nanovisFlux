from typing import Dict

from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator

from src.hardware.dispatcher import AXES


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


class DeckLayoutSchema(BaseModel):
    slots: Dict[str, SlotSchema]
