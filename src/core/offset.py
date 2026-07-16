"""
Handles mount offsets, pipette tip offsets, labware offsets, calibration offsets
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class Offset:
    """A named, fixed shift in raw motor steps to apply on top of a computed
    target -- e.g. a mount's physical mounting position, a pipette tip's
    length, a labware's calibrated resting position, or a one-off
    calibration nudge."""

    name: str
    steps: Dict[str, float] = field(default_factory=dict)

    def apply(self, steps: Dict[str, float]) -> Dict[str, float]:
        return {
            axis: steps.get(axis, 0.0) + self.steps.get(axis, 0.0)
            for axis in set(steps) | set(self.steps)
        }

    def remove(self, steps: Dict[str, float]) -> Dict[str, float]:
        """Inverse of apply(): removes this offset's contribution from an
        already-shifted step target."""
        return {
            axis: steps.get(axis, 0.0) - self.steps.get(axis, 0.0)
            for axis in set(steps) | set(self.steps)
        }


class OffsetStack:
    """Layers multiple named offsets (mount, pipette tip, labware,
    calibration, ...) and applies them together, in the order they were
    added."""

    def __init__(self) -> None:
        self._offsets: List[Offset] = []

    def add(self, offset: Offset) -> "OffsetStack":
        self._offsets.append(offset)
        return self

    def named(self, name: str) -> Offset:
        for offset in self._offsets:
            if offset.name == name:
                return offset
        raise KeyError(f"No offset named '{name}' in this stack.")

    def apply(self, steps: Dict[str, float]) -> Dict[str, float]:
        result = dict(steps)
        for offset in self._offsets:
            result = offset.apply(result)
        return result

    def remove(self, steps: Dict[str, float]) -> Dict[str, float]:
        result = dict(steps)
        for offset in reversed(self._offsets):
            result = offset.remove(result)
        return result
