from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TipGeometry:
    """Physical description of a disposable tip (or a calibration probe).

    ``length_mm`` is the distance from the pipette nozzle reference plane to
    the tip's contact end -- the single number that shifts every Z target
    once a tip is installed. Calibration stores a nozzle-reference z_zero, so
    swapping tips only changes this value, never the calibration.
    """

    name: str
    length_mm: float
    max_volume_ul: float = 0.0
    inner_diameter_mm: float = 0.0


@dataclass
class TipPickup:
    """Mechanical parameters for the press-to-seat pickup motion.

    The nozzle descends onto the tip top (``press_z`` in deck mm), then makes
    ``presses`` downward strokes of ``engage_mm`` with a small ``retract_mm``
    lift between them, seating the tip firmly before lifting away with it.
    """

    press_z_mm: float  # deck z of the tip top (first contact)
    engage_mm: float = 3.0  # how far below press_z each stroke drives
    retract_mm: float = 2.0  # lift between strokes
    presses: int = 2  # "press against it twice"
    feed: int = 4000  # plunger-slow feed for a controlled press
