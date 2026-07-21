"""OpenFlux: an object-oriented liquid-handler abstraction over the
OT-2 Stepper Controller G-code serial protocol.

Raw G-code strings exist in exactly one place (openflux.protocol.commands /
responses). Everything above manipulates typed objects instead.
"""
from .core import AxisId, MountSide
from .geometry.coordinates import DeckPoint
from .tools.tips import TipGeometry, TipPickup
from .robot import Robot

__all__ = ["Robot", "AxisId", "MountSide", "DeckPoint",
           "TipGeometry", "TipPickup"]
__version__ = "0.2.0"
