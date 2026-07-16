from typing import Dict, Tuple

from src.core.config_schema import DeckCalibrationSchema, MountOffsetsSchema
from src.core.physical_envelope import PhysicalEnvelope
from src.utils.logger import logger

# PhysicalEnvelope now lives in src.core.physical_envelope (bounds are stored
# directly on PhysicalAxis, see src.core.axes) -- re-exported here since this
# is where callers already look for it, alongside the other coordinate-space
# machinery.
__all__ = ["PhysicalEnvelope", "MountOffsets", "DeckCalibration"]


class MountOffsets:
    """Per-mount fixed step offsets correcting for the physical mounting
    position of each tool on the gantry carriage. A target computed in the
    shared gantry frame is shifted by a mount's offset to get the actual
    step command for that mount's tool tip."""

    def __init__(self, offsets: Dict[str, Dict[str, float]]):
        self._offsets = {
            mount: {axis.upper(): value for axis, value in axes.items()}
            for mount, axes in offsets.items()
        }

    @classmethod
    def from_config(cls, data: dict) -> "MountOffsets":
        validated = MountOffsetsSchema.model_validate(data)
        offsets = {mount: schema.root for mount, schema in validated.root.items()}
        logger.debug(f"Loaded mount offsets for mounts: {sorted(offsets.keys())}")
        return cls(offsets)

    def known_mounts(self) -> set:
        return set(self._offsets.keys())

    def _get(self, mount: str) -> Dict[str, float]:
        if mount not in self._offsets:
            raise KeyError(f"No mount offset defined for mount '{mount}'.")
        return self._offsets[mount]

    def apply(self, mount: str, steps: Dict[str, float]) -> Dict[str, float]:
        offset = self._get(mount)
        return {axis: value + offset.get(axis.upper(), 0.0) for axis, value in steps.items()}

    def remove(self, mount: str, steps: Dict[str, float]) -> Dict[str, float]:
        """Inverse of apply(): reframes an absolute mount-space step target
        back into the shared gantry frame."""
        offset = self._get(mount)
        return {axis: value - offset.get(axis.upper(), 0.0) for axis, value in steps.items()}


class DeckCalibration:
    """Fixes the deck plane's origin, orientation, and scale in raw steps
    from three calibration readings: an origin (the step position at deck
    mm (0, 0)) and one reading offset purely along each deck axis -- e.g.
    the centers of two slot separators, one column and one row apart. Every
    other deck mm position is then a straight linear interpolation between
    these three points.

    Unlike a pair of independent per-axis steps_per_mm values, this is a
    full 2D affine map: each deck axis can project onto both raw machine
    axes, so any skew between the deck's X/Y and the gantry's own X/Y is
    captured rather than assumed away. No home_offset_mm is needed -- the
    origin reading already is the absolute step position of the deck's
    (0, 0), with nothing further to add.
    """

    def __init__(
        self,
        origin_steps: Dict[str, float],
        x_vector: Dict[str, float],
        y_vector: Dict[str, float],
    ):
        self._origin = {axis.upper(): value for axis, value in origin_steps.items()}
        self._x_vector = {axis.upper(): value for axis, value in x_vector.items()}
        self._y_vector = {axis.upper(): value for axis, value in y_vector.items()}

    @classmethod
    def from_three_points(
        cls,
        origin_steps: Dict[str, float],
        x_reference_steps: Dict[str, float],
        x_reference_mm: float,
        y_reference_steps: Dict[str, float],
        y_reference_mm: float,
    ) -> "DeckCalibration":
        if x_reference_mm == 0 or y_reference_mm == 0:
            raise ValueError("Reference points must be offset from the origin.")
        axes = set(origin_steps) | set(x_reference_steps) | set(y_reference_steps)
        x_vector = {
            axis: (x_reference_steps.get(axis, 0.0) - origin_steps.get(axis, 0.0)) / x_reference_mm
            for axis in axes
        }
        y_vector = {
            axis: (y_reference_steps.get(axis, 0.0) - origin_steps.get(axis, 0.0)) / y_reference_mm
            for axis in axes
        }
        calibration = cls(origin_steps, x_vector, y_vector)
        logger.debug(
            f"Derived deck calibration: origin={calibration._origin}, "
            f"x_vector={calibration._x_vector}, y_vector={calibration._y_vector}"
        )
        return calibration

    @classmethod
    def from_config(cls, data: dict) -> "DeckCalibration":
        validated = DeckCalibrationSchema.model_validate(data)
        return cls.from_three_points(
            origin_steps=validated.origin_steps.as_steps(),
            x_reference_steps=validated.x_reference_steps.as_steps(),
            x_reference_mm=validated.x_reference_mm,
            y_reference_steps=validated.y_reference_steps.as_steps(),
            y_reference_mm=validated.y_reference_mm,
        )

    def mm_to_steps(self, x_mm: float, y_mm: float) -> Dict[str, float]:
        axes = set(self._origin) | set(self._x_vector) | set(self._y_vector)
        return {
            axis: self._origin.get(axis, 0.0)
            + x_mm * self._x_vector.get(axis, 0.0)
            + y_mm * self._y_vector.get(axis, 0.0)
            for axis in axes
        }

    def steps_to_mm(self, steps: Dict[str, float]) -> Tuple[float, float]:
        """Inverts mm_to_steps for the deck plane: given raw X/Y axis step
        readings, solves the 2x2 linear system for the (x_mm, y_mm) that
        would have produced them, using only the X and Y axis components of
        the calibration vectors -- the two equations needed for the two
        unknowns."""
        if "X" not in steps or "Y" not in steps:
            raise KeyError("steps_to_mm requires both 'X' and 'Y' step readings.")

        dx = steps["X"] - self._origin.get("X", 0.0)
        dy = steps["Y"] - self._origin.get("Y", 0.0)
        a, b = self._x_vector.get("X", 0.0), self._y_vector.get("X", 0.0)
        c, d = self._x_vector.get("Y", 0.0), self._y_vector.get("Y", 0.0)

        determinant = a * d - b * c
        if determinant == 0:
            raise ValueError("Deck calibration matrix is singular; cannot invert steps to mm.")

        x_mm = (dx * d - b * dy) / determinant
        y_mm = (a * dy - dx * c) / determinant
        return x_mm, y_mm
