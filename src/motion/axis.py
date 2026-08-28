"""Axis configuration and runtime state for robot motion control.

This module defines the static configuration and runtime state abstractions
used by the motion layer to represent individual controller axes.

:class:`AxisConfig` contains the hardware- and firmware-dependent parameters
for an axis, including travel limits, homing behavior, motion speeds,
acceleration, endstop characteristics, optional unit scaling, and measured
resonance bands. Keeping these values in configuration objects allows the
motion implementation to remain independent of machine-specific constants.

:class:`Axis` wraps an :class:`AxisConfig` with mutable runtime state,
including whether the axis has been homed and its most recently known
controller position.

The module also provides :data:`HOMING_ORDER`, the application-level axis
ordering used when sequencing homing-related UI or control operations, and
:func:`default_axis_configs`, which constructs the reference firmware
configuration for all supported axes.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import AxisId
from ..geometry.units import default_axis_scale


@dataclass
class AxisConfig:
    """Static hardware and motion configuration for one controller axis.

    Axis configuration contains the parameters required to safely operate and
    home an axis. These values are intended to be loaded from external
    configuration such as YAML or JSON rather than hard-coded throughout the
    motion implementation.

    Attributes:
        axis: Identifier of the configured axis.
        endstop_limit: Maximum permitted position in microsteps according to
            the controller's hard endstop limit.
        homing_dir_forward: Whether the axis homes in the controller's
            forward direction.
        invert: Whether the axis direction is inverted relative to the
            controller's nominal positive direction.
        travel_speed: Default travel speed in microsteps per second.
        homing_speed: Homing speed in microsteps per second.
        travel_accel: Travel acceleration in microsteps per second squared.
        endstop_bounce: Endstop debounce or bounce distance parameter in
            controller units.
        steps_per_mm: Optional conversion factor from millimeters to
            microsteps. This is `None` for axes without a defined linear
            scale.
        resonance_bands_hz: Resonance frequency bands, represented as
            `(low_hz, high_hz)` pairs in full motor-step frequency. Feed
            rates falling within these bands should be avoided by the motion
            profile logic.
    """

    axis: AxisId
    endstop_limit: int
    homing_dir_forward: bool
    invert: bool
    travel_speed: float
    homing_speed: float
    travel_accel: float
    endstop_bounce: int
    steps_per_mm: float | None = None
    resonance_bands_hz: tuple = ()


@dataclass
class Axis:
    """Axis configuration and runtime state for robot motion control.

    This module defines the static configuration and runtime state abstractions
    used by the motion layer to represent individual controller axes.

    :class:`AxisConfig` contains the hardware- and firmware-dependent parameters
    for an axis, including travel limits, homing behavior, motion speeds,
    acceleration, endstop characteristics, optional unit scaling, and measured
    resonance bands. Keeping these values in configuration objects allows the
    motion implementation to remain independent of machine-specific constants.

    :class:`Axis` wraps an :class:`AxisConfig` with mutable runtime state,
    including whether the axis has been homed and its most recently known
    controller position.

    The module also provides :data:`HOMING_ORDER`, the application-level axis
    ordering used when sequencing homing-related UI or control operations, and
    :func:`default_axis_configs`, which constructs the reference firmware
    configuration for all supported axes.
    """

    config: AxisConfig
    homed: bool = False
    position: int = 0

    @property
    def id(self) -> AxisId:
        """Return the identifier of the configured axis.

        Returns:
            AxisId: Axis identifier associated with :attr:`config`.
        """
        return self.config.axis


HOMING_ORDER = (AxisId.A, AxisId.Z, AxisId.Y, AxisId.X, AxisId.B, AxisId.C)
"""Application-level axis order used for homing sequences.

This ordering follows the documented and intended homing sequence rather than
the exact internal call order currently implemented by the reference
firmware. It is used for application-level sequencing, such as live-view
homing animations, and does not alter the firmware's own axis homing order
when a bare `G28` command is issued.
"""


def default_axis_configs() -> dict:
    """Construct the default configuration for all supported axes.

    The returned configurations represent the reference motion-controller
    firmware settings for the six supported axes. Linear axes X, Y, Z, and A
    receive their corresponding `steps_per_mm` scale; B and C do not have a
    defined linear scale and therefore use `None`.

    Returns:
        dict[AxisId, AxisConfig]: Mapping from each supported axis identifier
        to its default :class:`AxisConfig`.
    """
    limit = {
        AxisId.X: 62500,
        AxisId.Y: 54000,
        AxisId.Z: 175000,
        AxisId.A: 175000,
        AxisId.B: 20000,
        AxisId.C: 20000,
    }
    travel = {
        AxisId.X: 16000,
        AxisId.Y: 16000,
        AxisId.Z: 32000,
        AxisId.A: 32000,
        AxisId.B: 6900,
        AxisId.C: 6900,
    }
    # Matches firmware HOMING_SPEEDS[6] = {8000, 8000, 16000, 16000, 5000, 5000}
    # (order X, Y, Z, A, B, C).
    homing = {
        AxisId.X: 8000,
        AxisId.Y: 8000,
        AxisId.Z: 16000,
        AxisId.A: 16000,
        AxisId.B: 5000,
        AxisId.C: 5000,
    }
    accel = {
        AxisId.X: 69000,
        AxisId.Y: 69000,
        AxisId.Z: 69000,
        AxisId.A: 69000,
        AxisId.B: 3200,
        AxisId.C: 3200,
    }
    bounce = {
        AxisId.X: 1000,
        AxisId.Y: 1000,
        AxisId.Z: 1500,
        AxisId.A: 1500,
        AxisId.B: 1250,
        AxisId.C: 1250,
    }
    homing_fwd = {
        AxisId.X: True,
        AxisId.Y: True,
        AxisId.Z: True,
        AxisId.A: True,
        AxisId.B: False,
        AxisId.C: False,
    }
    invert = {
        AxisId.X: True,
        AxisId.Y: True,
        AxisId.Z: True,
        AxisId.A: True,
        AxisId.B: False,
        AxisId.C: False,
    }
    return {
        a: AxisConfig(
            axis=a,
            endstop_limit=limit[a],
            homing_dir_forward=homing_fwd[a],
            invert=invert[a],
            travel_speed=travel[a],
            homing_speed=homing[a],
            travel_accel=accel[a],
            endstop_bounce=bounce[a],
            steps_per_mm=(
                default_axis_scale(a).steps_per_mm
                if a in (AxisId.X, AxisId.Y, AxisId.Z, AxisId.A)
                else None
            ),
        )
        for a in AxisId
    }
