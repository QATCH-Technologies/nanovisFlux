"""
works as machine coordinates in terms of motor steps, and as the virtual
coordinate space in terms of mm along the deck. See src.core.axes for the
origin and sign convention of each space.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from src.common.calibration import Calibration
from src.core.coordinate_system import DeckCalibration


@dataclass(frozen=True)
class PhysicalCoordinate:
    """A position in raw motor-step space. Origin is machine home -- the
    back right corner above the trash (see src.core.axes.PhysicalAxis)."""

    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None

    @classmethod
    def from_steps(cls, steps: Dict[str, float]) -> "PhysicalCoordinate":
        return cls(**{axis.lower(): value for axis, value in steps.items()})

    def as_steps(self) -> Dict[str, float]:
        axes = {"X": self.x, "Y": self.y, "Z": self.z, "A": self.a, "B": self.b, "C": self.c}
        return {axis: value for axis, value in axes.items() if value is not None}

    def to_mm(
        self, deck_calibration: DeckCalibration, z_calibration: Calibration
    ) -> "VirtualCoordinate":
        """Converts to a deck mm position. Requires the calibration data that
        fixes this machine's step<->mm mapping -- there is no single global
        answer, so it must be supplied rather than assumed."""
        if self.x is None or self.y is None or self.z is None:
            raise ValueError("X, Y, and Z steps are all required to resolve a deck mm position.")
        x_mm, y_mm = deck_calibration.steps_to_mm({"X": self.x, "Y": self.y})
        z_mm = z_calibration.steps_to_mm({"Z": self.z})["Z"]
        return VirtualCoordinate(x=x_mm, y=y_mm, z=z_mm)

    def __str__(self) -> str:
        parts = " ".join(f"{axis}{value:.3f}" for axis, value in self.as_steps().items())
        return f"PhysicalCoordinate({parts})"


@dataclass(frozen=True)
class VirtualCoordinate:
    """A position in deck mm space. Origin is the front-right corner of deck
    slot 1 (see src.core.axes.VirtualAxis)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_steps(
        self, deck_calibration: DeckCalibration, z_calibration: Calibration
    ) -> PhysicalCoordinate:
        """Converts to raw motor steps. Requires the calibration data that
        fixes this machine's mm<->step mapping."""
        steps = deck_calibration.mm_to_steps(self.x, self.y)
        steps.update(z_calibration.mm_to_steps({"Z": self.z}))
        return PhysicalCoordinate.from_steps(steps)

    def __str__(self) -> str:
        return f"VirtualCoordinate(X={self.x:.3f}mm, Y={self.y:.3f}mm, Z={self.z:.3f}mm)"
