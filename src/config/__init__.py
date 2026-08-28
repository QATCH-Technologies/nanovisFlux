"""Configuration loading and runtime object construction.

This package provides the configuration boundary between serialized robot
configuration and the runtime objects used by the robot-control stack.

The public helpers exposed here load configuration data and construct the
corresponding axes, deck, labware, tips, calibration, transport, and robot
objects. Keeping this construction logic behind a small public API allows
the rest of the system to work with typed runtime objects without depending
directly on the configuration file format.

The package-level API re-exports the primary builders and loaders from
:mod:`.loader`.
"""

from .loader import (
    build_axes,
    build_calibration,
    build_deck,
    build_labware,
    build_tips,
    build_transport,
    load_calibration,
    load_config,
    load_robot,
    resolve_robot_config,
)

__all__ = [
    "build_axes",
    "build_calibration",
    "build_deck",
    "build_labware",
    "build_tips",
    "build_transport",
    "load_calibration",
    "load_config",
    "load_robot",
    "resolve_robot_config",
]
