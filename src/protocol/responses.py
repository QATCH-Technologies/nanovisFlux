"""Typed controller responses and protocol-response parsers.

This module defines the structured result types returned by the motion
controller and the parsing helpers that translate controller response lines
into those types.

The response models distinguish general command acknowledgements
(:class:`Response`) from operation-specific results such as probing
(:class:`ProbeResult`) and ultrasonic distance measurements
(:class:`DistanceResult`). Parsing remains isolated from the controller
transport and command layers so that protocol-specific response formats are
handled in one place.

The parsers are intentionally tolerant of informational lines surrounding the
protocol response of interest. Missing or unrecognized result lines are
represented by `None` where appropriate, allowing callers to distinguish a
valid response with no matching result from a parsed result containing empty
or unavailable measurements.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core import AxisId


@dataclass
class Response:
    """Represent a general controller command response.

    A response contains the terminal status together with any informational
    lines received before that status. The optional reason preserves a
    controller-provided explanation for a failed command.

    Attributes:
        ok: Whether the controller considered the command successful.
        info: Informational response lines received before the terminal
            status line.
        status: Raw terminal status returned by the controller. Defaults to
            `"ok"`.
        reason: Optional parsed explanation associated with a failed response.
    """

    ok: bool
    info: list[str] = field(default_factory=list)  # lines before the status line
    status: str = "ok"
    reason: str | None = None


@dataclass
class ProbeResult:
    """Represent the result of a controller probing operation.

    Attributes:
        contacted: Whether the probe detected the expected contact condition.
        positions: Axis positions, in microsteps, reported by the firmware at
            the probe trigger point.
    """

    contacted: bool
    positions: dict[AxisId, int]  # microsteps at trigger (firmware reports X, Y, A)


@dataclass
class DistanceResult:
    """Represent ultrasonic distance measurements for the M412 sensor slots.

    Each field corresponds to one sensor slot in the `M412` response. A
    value of `None` indicates that no usable measurement is available for
    that slot, whether because no echo was received, the measurement was out
    of range, or the slot was not queried.

    Attributes:
        x_mm: Distance reported for the X sensor slot, in millimeters, or
            `None` when unavailable.
        y_mm: Distance reported for the Y sensor slot, in millimeters, or
            `None` when unavailable.
        z_mm: Distance reported for the Z sensor slot, in millimeters, or
            `None` when unavailable.
    """

    x_mm: float | None
    y_mm: float | None
    z_mm: float | None


def extract_reason(status_line: str) -> str | None:
    """Extract the parenthesized reason from a controller status line.

    For example, a status line of `"NOT ok (axis Z not homed)"` produces
    `"axis Z not homed"`.

    Args:
        status_line: Raw controller status line.

    Returns:
        str | None: Text contained between the first opening parenthesis and
        the final closing parenthesis, or `None` when the status line does
        not contain a parenthesized reason.
    """
    if "(" in status_line and ")" in status_line:
        return status_line[status_line.index("(") + 1 : status_line.rindex(")")]
    return None


def parse_position(info: list[str]) -> dict[AxisId, int]:
    """Parse axis positions from an M114 response.

    Informational lines are searched for whitespace-separated `AXIS:VALUE`
    tokens. Tokens that cannot be converted to a known :class:`AxisId` with an
    integer value are ignored.

    Args:
        info: Informational response lines returned by the controller.

    Returns:
        dict[AxisId, int]: Mapping of recognized axes to their reported
        positions.
    """
    out: dict[AxisId, int] = {}
    for line in info:
        if ":" not in line:
            continue
        for token in line.split():
            key, sep, val = token.partition(":")
            if not sep:
                continue
            try:
                out[AxisId(key)] = int(val)
            except (ValueError, KeyError):
                pass
    return out


def parse_probe(info: list[str]) -> ProbeResult | None:
    """Parse a firmware `[PRB:...]` probe response.

    The expected response contains three position values followed by a
    contact flag. In the current firmware, the three positions correspond to
    the X, Y, and A axes, and a flag value of `1` indicates that contact was
    detected.

    Args:
        info: Informational response lines returned by the controller.

    Returns:
        ProbeResult | None: Parsed probe result when a valid `[PRB:...]`
        response is present; otherwise `None`.
    """
    for line in info:
        s = line.strip()
        if s.startswith("[PRB:") and s.endswith("]"):
            coords, _, flag = s[len("[PRB:") : -1].rpartition(":")
            xs = [int(v) for v in coords.split(",")]
            axes = [AxisId.X, AxisId.Y, AxisId.A]
            return ProbeResult(
                contacted=flag.strip() == "1",
                positions={axes[i]: xs[i] for i in range(min(len(xs), 3))},
            )
    return None


def parse_distance(info: list[str]) -> DistanceResult | None:
    """Parse a firmware `[RNG:...]` ultrasonic distance response.

    The response is expected to contain comma-separated X, Y, and Z distance
    values in millimeters. Negative values, such as the firmware's `-1`
    sentinel, are converted to `None` to represent an unavailable
    measurement.

    If fewer than three values are present, missing slots are treated as
    unavailable.

    Args:
        info: Informational response lines returned by the controller.

    Returns:
        DistanceResult | None: Parsed distance measurements when a valid
        `[RNG:...]` response is present; otherwise `None`.
    """
    for line in info:
        s = line.strip()
        if s.startswith("[RNG:") and s.endswith("]"):
            values = [float(v) for v in s[len("[RNG:") : -1].split(",")]
            x, y, z = (values + [-1.0, -1.0, -1.0])[:3]
            return DistanceResult(
                x_mm=x if x >= 0 else None,
                y_mm=y if y >= 0 else None,
                z_mm=z if z >= 0 else None,
            )
    return None
