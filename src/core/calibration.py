from typing import Dict

from src.core.config_schema import AxisCalibrationSchema, CalibrationSchema
from src.utils.logger import logger

CONFIG_KEY = "calibration"


def derive_axis_calibration(
    reference_mm: float, reference_steps: float, target_mm: float, target_steps: float
) -> AxisCalibrationSchema:
    """Fits steps_per_mm and home_offset_mm from two measured (mm, steps)
    reference points on one axis -- e.g. two calibration points whose deck
    mm positions are known by design and whose step positions were read off
    the machine, such as the centers of two slot separators."""
    delta_mm = target_mm - reference_mm
    if delta_mm == 0:
        raise ValueError("Reference points must be at different mm positions.")
    steps_per_mm = (target_steps - reference_steps) / delta_mm
    home_offset_mm = reference_steps / steps_per_mm - reference_mm
    return AxisCalibrationSchema(steps_per_mm=steps_per_mm, home_offset_mm=home_offset_mm)


class Calibration:
    def __init__(self, axis_calibrations: Dict[str, AxisCalibrationSchema]):
        self._axes = {axis.upper(): cal for axis, cal in axis_calibrations.items()}

    @classmethod
    def from_config(cls, calibration_data: dict) -> "Calibration":
        validated = CalibrationSchema.model_validate(calibration_data)
        logger.debug(f"Loaded calibration for axes: {sorted(validated.root.keys())}")
        return cls(validated.root)

    def known_axes(self) -> set:
        return set(self._axes.keys())

    def _get(self, axis: str) -> AxisCalibrationSchema:
        axis_upper = axis.upper()
        if axis_upper not in self._axes:
            raise KeyError(f"No calibration defined for axis '{axis_upper}'.")
        return self._axes[axis_upper]

    def mm_to_steps(self, positions_mm: Dict[str, float]) -> Dict[str, int]:
        steps = {}
        for axis, mm in positions_mm.items():
            cal = self._get(axis)
            steps[axis.upper()] = round((mm + cal.home_offset_mm) * cal.steps_per_mm)
        return steps

    def steps_to_mm(self, positions_steps: Dict[str, float]) -> Dict[str, float]:
        mm = {}
        for axis, steps in positions_steps.items():
            cal = self._get(axis)
            mm[axis.upper()] = (steps / cal.steps_per_mm) - cal.home_offset_mm
        return mm

    def delta_mm_to_steps(self, deltas_mm: Dict[str, float]) -> Dict[str, int]:
        deltas = {}
        for axis, mm in deltas_mm.items():
            cal = self._get(axis)
            deltas[axis.upper()] = round(mm * cal.steps_per_mm)
        return deltas
