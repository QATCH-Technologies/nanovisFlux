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
    brand: str = ""  # vendor/manufacturer, e.g. "Opentrons" -- "" when unknown/custom


@dataclass
class TipPickup:
    """Mechanical parameters for the press-to-seat pickup motion.

    The nozzle descends onto the tip top (``press_z`` in deck mm), then makes
    ``presses`` downward strokes of ``engage_mm`` with a small ``retract_mm``
    lift between them, seating the tip firmly.

    If ``touch_offset_mm`` is nonzero, the nozzle then backs off by
    ``touch_retract_mm`` (about half the press depth, by default) and taps
    the tip against the tip rack well's walls in a '+' pattern -- left then
    right, then front then back -- to square it up before lifting away with
    it. 0 disables the touch pattern entirely.
    """

    press_z_mm: float  # deck z of the tip top (first contact)
    engage_mm: float = 3.0  # how far below press_z each stroke drives
    retract_mm: float = 2.0  # lift between strokes
    presses: int = 2  # "press against it twice"
    feed: int = 9000  # Z feed (microsteps/s) for every press/retract/touch stroke -- quick taps
    touch_offset_mm: float = 1.5  # lateral nudge for the '+' well-wall touch; 0 disables
    touch_retract_mm: float | None = None  # lift before touching; None = engage_mm / 2
    touch_feed: int | None = None  # feed for the touch pattern; None = use `feed`
