from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Mapping, Sequence
from ..core import AxisId


def _num(v) -> str:
    f = float(v)
    return str(int(f)) if f.is_integer() else repr(f)


def _axis_args(values: Mapping[AxisId, float]) -> str:
    return " ".join(f"{a.letter}{_num(v)}" for a, v in values.items())


class Command:
    """A single controller instruction.

    Subclasses render themselves to a G-code line. This is the ONLY place in
    the library where the wire format is written; everything above deals in
    these objects, never strings. New firmware command -> new Command class.
    """
    #: Does the firmware reply with a terminal 'ok'/'NOT ok'? The config
    #: setters (M201/M204/M210/M220/M421) and the stop/reset codes are silent,
    #: so the driver must NOT block waiting on them.
    acknowledges: ClassVar[bool] = True

    def render(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass
class RapidMove(Command):
    targets: Mapping[AxisId, int]

    def render(self) -> str:
        return "G0 " + _axis_args(self.targets)


@dataclass
class LinearMove(Command):
    targets: Mapping[AxisId, int]
    feed: int | None = None

    def render(self) -> str:
        s = "G1 " + _axis_args(self.targets)
        return s + (f" F{int(self.feed)}" if self.feed is not None else "")


@dataclass
class Home(Command):
    axes: Sequence[AxisId] = ()

    def render(self) -> str:
        return "G28" if not self.axes else "G28 " + " ".join(a.letter for a in self.axes)


class ProbeMode(Enum):
    TOWARD_OR_FAIL = "G38.2"  # error if target reached without contact
    TOWARD = "G38.3"          # no error on no-contact
    AWAY_OR_FAIL = "G38.4"    # error if contact never released
    AWAY = "G38.5"            # no error


@dataclass
class Probe(Command):
    axis: AxisId
    target: int
    feed: int | None = None
    mode: ProbeMode = ProbeMode.TOWARD_OR_FAIL

    def render(self) -> str:
        s = f"{self.mode.value} {self.axis.letter}{int(self.target)}"
        return s + (f" F{int(self.feed)}" if self.feed is not None else "")


@dataclass
class SetAbsolute(Command):
    def render(self) -> str:
        return "G90"


@dataclass
class SetRelative(Command):
    def render(self) -> str:
        return "G91"


@dataclass
class ReportPosition(Command):
    def render(self) -> str:
        return "M114"


# --- silent per-axis configuration setters ---------------------------------
@dataclass
class _PerAxisConfig(Command):
    values: Mapping[AxisId, float]
    code: ClassVar[str] = ""
    acknowledges: ClassVar[bool] = False

    def render(self) -> str:
        return f"{self.code} " + _axis_args(self.values)


class SetHardLimits(_PerAxisConfig):
    code = "M201"


class SetAccelerations(_PerAxisConfig):
    code = "M204"


class SetHomingSpeeds(_PerAxisConfig):
    code = "M210"


class SetTravelSpeeds(_PerAxisConfig):
    code = "M220"


class SetHomingRetract(_PerAxisConfig):
    code = "M421"


@dataclass
class QuickStop(Command):
    acknowledges: ClassVar[bool] = False

    def render(self) -> str:
        return "M410"


@dataclass
class EmergencyStop(Command):
    acknowledges: ClassVar[bool] = False

    def render(self) -> str:
        return "M112"


@dataclass
class Reset(Command):
    acknowledges: ClassVar[bool] = False  # reboots; a boot banner follows

    def render(self) -> str:
        return "M30"


@dataclass
class DisableLimits(Command):
    def render(self) -> str:
        return "M911"
