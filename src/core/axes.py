"""
handles the physical motor axis
origin is in the top right rear corner of the machine, positive x extends left
positive y extends forward, positive z extends down.

origin is in the front left bottom corner of the machine. Positive x extends right
positive z extends up, and positive y extends back
"""

from enum import Enum
from typing import Dict, Optional, Tuple

# Module-level (not per-instance) state: PhysicalAxis members are singletons,
# so "which axis is active" and "what is this axis's travel envelope" are
# necessarily shared, machine-wide facts for the life of the process -- there
# is exactly one physical machine, so exactly one true answer for each axis.
_active_physical_axis: Optional["PhysicalAxis"] = None
_physical_axis_envelopes: Dict[str, Tuple[float, float]] = {}


class PhysicalAxis(Enum):
    """Raw motor-step axis. Origin sits at the top-right-rear corner of the
    machine: +X extends left, +Y extends forward, +Z extends down."""

    A = "A"
    B = "B"
    C = "C"
    X = "X"
    Y = "Y"
    Z = "Z"

    @classmethod
    def origin(cls) -> Dict[str, float]:
        """The step position of every physical axis at machine home."""
        return {axis.value: 0.0 for axis in cls}

    def active(self) -> None:
        """Marks this axis as the one currently engaged -- e.g. the vertical
        axis (Z or A) of whichever mount is presently selected."""
        global _active_physical_axis
        _active_physical_axis = self

    @classmethod
    def get_active(cls) -> Optional["PhysicalAxis"]:
        return _active_physical_axis

    def set_envelope(self, low: float, high: float) -> None:
        """Records this axis's calibrated travel limits, in raw steps. See
        src.core.physical_envelope, which derives these from corner
        readings."""
        if high <= low:
            raise ValueError(
                f"Envelope for axis {self.value} must have high > low (got {low}, {high})."
            )
        _physical_axis_envelopes[self.value] = (low, high)

    def envelope(self) -> Optional[Tuple[float, float]]:
        """This axis's (low, high) travel limits in raw steps, or None if it
        has no calibrated envelope (e.g. it was never swept during
        calibration)."""
        return _physical_axis_envelopes.get(self.value)

    def has_envelope(self) -> bool:
        return self.value in _physical_axis_envelopes

    def in_envelope(self, value: float) -> bool:
        """Whether `value` (in raw steps) falls within this axis's envelope.
        An axis with no calibrated envelope is never considered out of
        bounds."""
        bounds = self.envelope()
        if bounds is None:
            return True
        low, high = bounds
        return low <= value <= high

    def clear_envelope(self) -> None:
        _physical_axis_envelopes.pop(self.value, None)

    @classmethod
    def clear_all_envelopes(cls) -> None:
        _physical_axis_envelopes.clear()


class VirtualAxis(Enum):
    """Deck-space mm axis. Origin sits at the front-left-bottom corner of the
    machine (the front-right corner of deck slot 1): +X extends right, +Y
    extends back, +Z extends up."""

    X = "X"
    Y = "Y"
    Z = "Z"

    @classmethod
    def origin(cls) -> Dict[str, float]:
        """The mm position of every virtual axis at the deck origin."""
        return {axis.value: 0.0 for axis in cls}
