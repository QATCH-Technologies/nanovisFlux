from __future__ import annotations
from enum import Enum


class AxisId(Enum):
    """The six motion axes exposed by the firmware."""
    X = "X"  # gantry left/right
    Y = "Y"  # gantry front/back
    Z = "Z"  # left mount vertical
    A = "A"  # right mount vertical
    B = "B"  # left plunger
    C = "C"  # right plunger

    @property
    def letter(self) -> str:
        return self.value

    @property
    def index(self) -> int:
        return "XYZABC".index(self.value)


class MountSide(Enum):
    LEFT = "left"    # vertical Z, plunger B
    RIGHT = "right"  # vertical A, plunger C
