"""
Derives per-axis travel-limit bounds from a set of raw-step corner readings
(e.g. jogging the gantry to each corner of the reachable volume) and stores
them directly on PhysicalAxis (see src.core.axes) -- the envelope is a
property of the physical axis itself, not a separate bag of bounds, so
anything holding a PhysicalAxis can ask it for its own limits.

This class is a thin, ergonomic facade over that axis-level state: a
convenient way to derive bounds from calibration readings and query/check
them as a group, without owning the state itself. An axis held constant
across every corner reading (span == 0) was not actually swept during
calibration -- e.g. a mount's vertical axis that happened to sit at its rest
position throughout an X/Y/Z sweep -- so it is left with no envelope rather
than treated as a real (zero-width) limit.
"""

from typing import Dict, List, Set, Tuple

from src.core.axes import PhysicalAxis
from src.core.config_schema import PhysicalEnvelopeSchema
from src.utils.logger import logger


class PhysicalEnvelope:
    def __init__(self, bounds: Dict[str, Tuple[float, float]]):
        # A physical envelope describes one real machine's actual travel
        # limits -- constructing a new one replaces whatever was known
        # before rather than merging with it.
        PhysicalAxis.clear_all_envelopes()
        for axis, (low, high) in bounds.items():
            if high > low:
                PhysicalAxis(axis.upper()).set_envelope(low, high)

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
        logger.debug(f"Derived physical envelope for axes: {sorted(envelope.known_axes())}")
        return envelope

    def known_axes(self) -> Set[str]:
        return {axis.value for axis in PhysicalAxis if axis.has_envelope()}

    def axis_range(self, axis: str) -> Tuple[float, float]:
        bounds = PhysicalAxis(axis.upper()).envelope()
        if bounds is None:
            raise KeyError(f"No calibrated envelope bounds for axis '{axis.upper()}'.")
        return bounds

    def span(self, axis: str) -> float:
        low, high = self.axis_range(axis)
        return high - low

    def violations(self, steps: Dict[str, float]) -> Dict[str, Tuple[float, Tuple[float, float]]]:
        """Axes in `steps` that fall outside their calibrated bounds, mapped
        to (requested_value, (low, high)). Axes with no calibrated bounds are
        skipped rather than flagged."""
        bad = {}
        for axis, value in steps.items():
            physical_axis = PhysicalAxis(axis.upper())
            if not physical_axis.in_envelope(value):
                bad[axis.upper()] = (value, physical_axis.envelope())
        return bad

    def contains(self, steps: Dict[str, float]) -> bool:
        return not self.violations(steps)
