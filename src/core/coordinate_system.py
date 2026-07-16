from typing import Dict, List, Tuple

from src.core.config_schema import MountOffsetsSchema, PhysicalEnvelopeSchema
from src.utils.logger import logger


class PhysicalEnvelope:
    """The reachable bounding box in raw motor steps, derived from a set of
    axis readings taken at the physical travel extremes (e.g. jogging the
    gantry to each corner of the deck volume).

    An axis held constant across every corner reading (span == 0) was not
    actually swept during calibration -- e.g. a mount's vertical axis that
    happened to sit at its rest position throughout an X/Y/Z sweep -- so it
    is excluded from bounds-checking rather than treated as a real limit.
    """

    def __init__(self, bounds: Dict[str, Tuple[float, float]]):
        self._bounds = {
            axis: bounds_ for axis, bounds_ in bounds.items() if bounds_[1] > bounds_[0]
        }

    @classmethod
    def from_corners(cls, corners: List[Dict[str, float]]) -> "PhysicalEnvelope":
        validated = PhysicalEnvelopeSchema.model_validate(corners).root
        bounds: Dict[str, Tuple[float, float]] = {}
        for corner in validated:
            for axis, value in corner.items():
                axis = axis.upper()
                low, high = bounds.get(axis, (value, value))
                bounds[axis] = (min(low, value), max(high, value))
        envelope = cls(bounds)
        logger.debug(f"Derived physical envelope: {envelope._bounds}")
        return envelope

    def known_axes(self) -> set:
        return set(self._bounds.keys())

    def axis_range(self, axis: str) -> Tuple[float, float]:
        axis = axis.upper()
        if axis not in self._bounds:
            raise KeyError(f"No calibrated envelope bounds for axis '{axis}'.")
        return self._bounds[axis]

    def span(self, axis: str) -> float:
        low, high = self.axis_range(axis)
        return high - low

    def violations(self, steps: Dict[str, float]) -> Dict[str, Tuple[float, Tuple[float, float]]]:
        """Axes in `steps` that fall outside their calibrated bounds, mapped
        to (requested_value, (low, high)). Axes with no calibrated bounds are
        skipped rather than flagged."""
        bad = {}
        for axis, value in steps.items():
            axis = axis.upper()
            if axis not in self._bounds:
                continue
            low, high = self._bounds[axis]
            if value < low or value > high:
                bad[axis] = (value, (low, high))
        return bad

    def contains(self, steps: Dict[str, float]) -> bool:
        return not self.violations(steps)


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
