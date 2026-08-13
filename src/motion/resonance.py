"""Stepper resonance-band avoidance.

Every stepper motor has one or more mechanical resonant frequencies (tied
to the motor/leadscrew/carriage system, not the driver electronics) where
commanding it to step at that rate makes it ring audibly and vibrate badly
instead of turning smoothly. This module doesn't measure or predict where
those bands are for any particular machine -- it only nudges a computed
feed rate away from bands that have been *configured* (see
``motion.axis.AxisConfig.resonance_bands_hz``), leaving them empty (no
avoidance at all) until someone actually characterizes the hardware.

Bands are expressed in FULL motor-step Hz -- the physically meaningful unit
for stepper resonance. Microstepping (see geometry.units.MICROSTEPS_PER_STEP)
only interpolates position *within* one full step; the rotor still detents
at the full-step rate regardless of how finely that step is subdivided, so
a resonance band doesn't move around depending on the microstepping setting
the way it would if expressed directly in microsteps/s. Everything here
converts to/from microsteps/s (the wire protocol's own feed unit -- see
protocol.commands.LinearMove) only at the boundary.

To characterize a real band: jog the axis slowly across its range at a
series of speeds (or run a slow constant-speed sweep) and listen/feel for
where it rings -- note the approximate microsteps/s, divide by
MICROSTEPS_PER_STEP to get full-step Hz, and add the (low, high) pair to
that axis's ``resonance_bands_hz`` in configs/axes.yaml.
"""

from __future__ import annotations

from ..geometry.units import MICROSTEPS_PER_STEP


def feed_in_resonance_band(
    feed: float, bands_hz, microsteps_per_step: int = MICROSTEPS_PER_STEP
):
    """The (low_hz, high_hz) band (full-step Hz) that ``feed`` (microsteps/s)
    falls in, or None if it's clear of all of them."""
    for low, high in bands_hz:
        if low * microsteps_per_step <= feed <= high * microsteps_per_step:
            return (low, high)
    return None


def _walk_clear(
    feed: float, bands_hz, microsteps_per_step: int, direction: int, limit: float | None
) -> float | None:
    """Push ``feed`` in ``direction`` (+1 up, -1 down), one violated band's
    far edge at a time, until it lands clear of every band in ``bands_hz``
    -- chaining straight through adjacent/overlapping bands (landing just
    past one band that turns out to be the start of the next moves on
    again, rather than reporting clear prematurely). None if ``limit``
    (ceiling going up / floor going down) is crossed before that happens,
    or if it doesn't converge within a bounded number of steps -- either
    way, this direction isn't a viable escape."""
    current = feed
    for _ in range(len(bands_hz) + 1):
        band = feed_in_resonance_band(current, bands_hz, microsteps_per_step)
        if band is None:
            return current
        edge_hz = band[1] if direction > 0 else band[0]
        current = edge_hz * microsteps_per_step + direction
        if limit is not None and (current > limit if direction > 0 else current < limit):
            return None
    return None


def avoid_resonant_feed(
    feed: float,
    bands_hz,
    *,
    ceiling: float | None = None,
    floor: float = 0.0,
    microsteps_per_step: int = MICROSTEPS_PER_STEP,
) -> float:
    """``feed`` (microsteps/s), nudged clear of every band in ``bands_hz``
    (full-step Hz) that it currently falls inside.

    Tries moving clear in both directions (see ``_walk_clear``) and picks
    whichever landing point is closer to the original ``feed`` --
    minimizing how much the requested speed actually changes.

    ``ceiling``/``floor`` (also microsteps/s) are hard limits from the
    caller -- e.g. an axis's own configured travel_speed -- that a nudge
    must never cross even if that means landing back inside a band: a
    safety/mechanical ceiling always wins over dodging a bad sound. If
    neither direction can escape within [floor, ceiling], the original
    ``feed`` is simply clamped into that range and returned -- that's a
    genuinely unavoidable band given the caller's limits, a configuration
    problem this function can't solve, not something to loop forever over.
    """
    if not bands_hz or feed_in_resonance_band(feed, bands_hz, microsteps_per_step) is None:
        return feed
    up = _walk_clear(feed, bands_hz, microsteps_per_step, +1, ceiling)
    down = _walk_clear(feed, bands_hz, microsteps_per_step, -1, floor)
    candidates = [c for c in (up, down) if c is not None]
    if not candidates:
        clamped = feed if ceiling is None else min(feed, ceiling)
        return max(floor, clamped)
    return min(candidates, key=lambda c: abs(c - feed))
