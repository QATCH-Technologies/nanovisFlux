"""
Motion axis and mount-position enumerations.

This module defines the canonical identifiers used to represent the motion
axes exposed by the instrument firmware and the physical mount positions
associated with those axes.

The :class:`AxisId` enumeration maps firmware axis letters to their physical
motion axes and provides convenience properties for retrieving the firmware
letter and zero-based axis index. The :class:`MountSide` enumeration identifies
the left, right, and rear instrument mount positions and documents the motion
axes associated with each position.

These enumerations provide a shared, type-safe vocabulary for referring to
instrument axes and mount positions throughout motion-control, hardware
abstraction, and higher-level instrument-control code.
"""

from __future__ import annotations

from enum import Enum


class AxisId(Enum):
    """Identifies a motion axis exposed by the firmware.

    Each member corresponds to a firmware axis identifier and its associated
    physical motion in the instrument.

    Attributes:
        X: Gantry left/right motion axis.
        Y: Gantry front/back motion axis.
        Z: Left mount vertical motion axis.
        A: Right mount vertical motion axis.
        B: Left plunger motion axis.
        C: Right plunger motion axis.
    """

    X = "X"
    Y = "Y"
    Z = "Z"
    A = "A"
    B = "B"
    C = "C"

    @property
    def letter(self) -> str:
        """Return the firmware letter identifying this axis.

        Returns:
            The single-character firmware identifier for the axis.
        """
        return self.value

    @property
    def index(self) -> int:
        """Return the zero-based positional index of the axis.

        The index follows the firmware axis ordering `XYZABC`.

        Returns:
            The zero-based index of the axis in the canonical firmware ordering.
        """
        return "XYZABC".index(self.value)


class MountSide(Enum):
    """Identifies a physical instrument mount position.

    Each mount side describes the physical location of a mount and, where
    applicable, the vertical and plunger motion axes associated with it.

    Attributes:
        LEFT: Left mount, associated with vertical axis `Z` and plunger
            axis `B`.
        RIGHT: Right mount, associated with vertical axis `A` and plunger
            axis `C`.
        REAR: Fixed rear sensor mount positioned behind the left and right
            mounts. This position has no associated vertical or plunger axis.
    """

    LEFT = "left"
    RIGHT = "right"
    REAR = "rear"
