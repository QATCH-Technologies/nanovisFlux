from __future__ import annotations
from dataclasses import dataclass, field
from ..core import AxisId


@dataclass
class Response:
    ok: bool
    info: list[str] = field(default_factory=list)  # lines before the status line
    status: str = "ok"
    reason: str | None = None


@dataclass
class ProbeResult:
    contacted: bool
    positions: dict[AxisId, int]  # microsteps at trigger (firmware reports X, Y, A)


@dataclass
class DistanceResult:
    """One reading per M412 slot -- see commands.MeasureDistance. Each is
    ``None`` when that slot echoed no signal, was out of range, or simply
    wasn't queried in the command that produced this result."""
    x_mm: float | None
    y_mm: float | None
    z_mm: float | None


def extract_reason(status_line: str) -> str | None:
    """'NOT ok (axis Z not homed)' -> 'axis Z not homed'."""
    if "(" in status_line and ")" in status_line:
        return status_line[status_line.index("(") + 1: status_line.rindex(")")]
    return None


def parse_position(info: list[str]) -> dict[AxisId, int]:
    """Parse an M114 line like ' X:100 Y:150 Z:5 A:0 B:0 C:0'."""
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
    """Parse '[PRB:x,y,a:flag]'. In this firmware the three values are the
    X, Y and A positions at the trigger, and flag=1 means contact."""
    for line in info:
        s = line.strip()
        if s.startswith("[PRB:") and s.endswith("]"):
            coords, _, flag = s[len("[PRB:"):-1].rpartition(":")
            xs = [int(v) for v in coords.split(",")]
            axes = [AxisId.X, AxisId.Y, AxisId.A]
            return ProbeResult(
                contacted=flag.strip() == "1",
                positions={axes[i]: xs[i] for i in range(min(len(xs), 3))},
            )
    return None


def parse_distance(info: list[str]) -> DistanceResult | None:
    """Parse '[RNG:<x_mm>,<y_mm>,<z_mm>]' (see MeasureDistance's docstring).
    A negative value (e.g. -1) in any slot means no echo / out of range /
    not queried."""
    for line in info:
        s = line.strip()
        if s.startswith("[RNG:") and s.endswith("]"):
            values = [float(v) for v in s[len("[RNG:"):-1].split(",")]
            x, y, z = (values + [-1.0, -1.0, -1.0])[:3]
            return DistanceResult(
                x_mm=x if x >= 0 else None,
                y_mm=y if y >= 0 else None,
                z_mm=z if z >= 0 else None,
            )
    return None
