"""Utilities for avoiding configured mechanical stepper resonance bands.

Stepper resonance occurs at machine-specific mechanical frequencies where a
motor and its attached mechanics may vibrate or produce excessive noise. This
module does not characterize or predict those frequencies. Instead, it
provides utilities for avoiding resonance bands that have already been
measured and configured on an axis.

Resonance bands are expressed in full motor-step frequency (Hz), while motion
commands use microsteps per second. The conversion between these units is
performed at the module boundary using
:data:`geometry.units.MICROSTEPS_PER_STEP`.

The primary public functions are :func:`feed_in_resonance_band`, which tests
whether a requested feed falls within a configured resonance band, and
:func:`avoid_resonant_feed`, which selects the nearest feed rate outside all
applicable bands while respecting caller-provided speed limits.
"""

from __future__ import annotations

from ..geometry.units import MICROSTEPS_PER_STEP


def feed_in_resonance_band(feed: float, bands_hz, microsteps_per_step: int = MICROSTEPS_PER_STEP):
    """Return the resonance band containing a feed rate, if any.

    `feed` is expressed in microsteps per second, while each configured
    resonance band is expressed as a `(low_hz, high_hz)` interval in full
    motor-step frequency. The feed is converted implicitly by comparing it
    against the corresponding microstep-rate bounds.

    Band boundaries are inclusive.

    Args:
        feed: Requested feed rate in microsteps per second.
        bands_hz: Iterable of `(low_hz, high_hz)` resonance bands expressed
            in full motor-step Hz.
        microsteps_per_step: Number of microsteps corresponding to one full
            motor step.

    Returns:
        tuple[float, float] | None: The first configured resonance band
        containing `feed`, or `None` if the feed is outside all bands.
    """
    for low, high in bands_hz:
        if low * microsteps_per_step <= feed <= high * microsteps_per_step:
            return (low, high)
    return None


def _walk_clear(
    feed: float,
    bands_hz,
    microsteps_per_step: int,
    direction: int,
    limit: float | None,
) -> float | None:
    """Search in one direction for a feed rate outside all resonance bands.

    Starting at `feed`, the search moves just beyond the far edge of each
    encountered resonance band. This allows adjacent or overlapping bands to
    be traversed as a single blocked region rather than incorrectly treating
    the first cleared band as a valid landing point.

    The search terminates successfully when a feed outside every configured
    band is found. It fails when the requested direction crosses `limit` or
    when the bounded search cannot reach a clear feed.

    Args:
        feed: Starting feed rate in microsteps per second.
        bands_hz: Iterable of `(low_hz, high_hz)` resonance bands expressed
            in full motor-step Hz.
        microsteps_per_step: Number of microsteps corresponding to one full
            motor step.
        direction: Search direction. `+1` searches toward higher feed
            rates; `-1` searches toward lower feed rates.
        limit: Optional hard limit in the search direction. When searching
            upward this is the maximum permitted feed; when searching
            downward it is the minimum permitted feed.

    Returns:
        float | None: The first feed rate found outside all resonance bands,
        or `None` if the direction cannot provide a valid escape.
    """
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
    """Adjust a feed rate to avoid configured resonance bands.

    If `feed` is already outside every configured resonance band, it is
    returned unchanged. Otherwise, the function searches both higher and
    lower feed rates for the nearest value that lies outside all bands.

    The selected candidate minimizes the absolute change from the requested
    feed. `ceiling` and `floor` constrain the adjustment and are treated
    as hard caller-provided motion limits. If neither direction provides a
    valid escape within those limits, the original feed is clamped to the
    permitted range and returned.

    Resonance bands are specified in full motor-step Hz, whereas `feed`,
    `ceiling`, and `floor` are expressed in microsteps per second.

    Args:
        feed: Requested feed rate in microsteps per second.
        bands_hz: Iterable of `(low_hz, high_hz)` resonance bands expressed
            in full motor-step Hz.
        ceiling: Optional maximum permitted feed rate in microsteps per
            second. A resonance-avoidance adjustment never exceeds this
            value.
        floor: Minimum permitted feed rate in microsteps per second.
            Defaults to zero.
        microsteps_per_step: Number of microsteps corresponding to one full
            motor step.

    Returns:
        float: The nearest feed rate outside all applicable resonance bands
        while respecting the specified limits. If no clear feed is reachable,
        returns the requested feed clamped to `[floor, ceiling]`.
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
