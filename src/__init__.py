"""OpenFlux: an object-oriented abstraction for automated liquid handling.

OpenFlux provides a typed, layered interface for controlling an OT-2
Stepper Controller without requiring application code to construct or parse
raw G-code. Low-level protocol formatting and response parsing are isolated
in :mod:`openflux.protocol.commands` and :mod:`openflux.protocol.responses`;
higher layers operate on typed domain objects such as axes, mount sides,
deck coordinates, tools, and robot motions.

The package-level API exposes the primary objects required by user code:

* :class:`AxisId` -- Identifies the controller's motion axes.
* :class:`MountSide` -- Identifies the robot's tool-mount positions.
* :class:`DeckPoint` -- Represents a position in deck-space coordinates.
* :class:`Robot` -- Top-level facade coordinating motion, calibration,
  mounts, tools, and labware.
* :class:`TipGeometry` -- Describes the physical geometry of a disposable
  pipette tip.
* :class:`TipPickup` -- Defines the mechanical parameters used to seat a tip.

The package version is available through :data:`__version__`.
"""

from .core import AxisId, MountSide
from .geometry.coordinates import DeckPoint
from .robot import Robot
from .tools.tips import TipGeometry, TipPickup

__all__ = [
    "AxisId",
    "DeckPoint",
    "MountSide",
    "Robot",
    "TipGeometry",
    "TipPickup",
]
__version__ = "0.2.0"
