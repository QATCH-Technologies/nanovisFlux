"""Core motion primitives and motion-profile utilities.

This package exposes the fundamental abstractions used to describe and
configure robot motion independently of higher-level routines and protocol
commands.

The public API includes:

* :class:`Axis` -- Representation of a controllable motion axis.
* :class:`AxisConfig` -- Configuration describing an axis's motion and
  homing behavior.
* :data:`HOMING_ORDER` -- Canonical ordering for axis homing operations.
* :func:`default_axis_configs` -- Construction of the default axis
  configuration set.
* :class:`Mount` -- Representation of a robot tool or pipette mount.
* :func:`avoid_resonant_feed` -- Selects or adjusts a feed rate to avoid a
  resonance region.
* :func:`feed_in_resonance_band` -- Determines whether a feed rate falls
  within a configured resonance band.

These objects form the core motion layer used by higher-level robot control
and routine abstractions.
"""

from .axis import HOMING_ORDER, Axis, AxisConfig, default_axis_configs
from .mounts import Mount
from .resonance import avoid_resonant_feed, feed_in_resonance_band

__all__ = [
    "Axis",
    "AxisConfig",
    "HOMING_ORDER",
    "Mount",
    "avoid_resonant_feed",
    "default_axis_configs",
    "feed_in_resonance_band",
]
