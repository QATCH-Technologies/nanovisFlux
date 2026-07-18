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
