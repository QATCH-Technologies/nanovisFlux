from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

AXES = {
    "X",
    "Y",
    "Z",
    "A",
    "B",
    "C",  # Added C as protocol.md lists it in the coordinate system
}

_VALID_PROBE_TYPES = {"38.2", "38.3", "38.4", "38.5"}


class Command(ABC):
    @abstractmethod
    def to_gcode(self) -> str:
        raise NotImplementedError

    def __str__(self) -> str:
        return self.to_gcode()


def _format_axis_values(values: Dict[str, int]) -> str:
    """Pure formatter: no validation, no re-sorting -- relies on the dict
    already being normalized (uppercase keys, correct order) by the caller."""
    return " ".join(f"{axis}{values[axis]}" for axis in values)


@dataclass(frozen=True)
class SimpleCommand(Command):
    code: str

    def to_gcode(self) -> str:
        return self.code


@dataclass(frozen=True)
class AxisCommand(Command):
    code: str
    axis_values: Dict[str, int]
    feed_rate: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.axis_values:
            raise ValueError(f"{self.code} command requires at least one axis value.")
        for axis in self.axis_values:
            if axis not in AXES:
                raise ValueError(f"Invalid axis '{axis}'. Must be one of {AXES}.")
        if self.feed_rate is not None and self.feed_rate <= 0:
            raise ValueError("Feedrate (speed) must be greater than zero.")
        # Defensive copy: a caller constructing this directly could mutate
        # their own dict after handing it to us.
        object.__setattr__(self, "axis_values", dict(self.axis_values))

    def to_gcode(self) -> str:
        parts = [self.code, _format_axis_values(self.axis_values)]
        if self.feed_rate is not None:
            parts.append(f"F{self.feed_rate}")
        return " ".join(parts)


@dataclass(frozen=True)
class HomeCommand(Command):
    axes: Optional[Tuple[str, ...]] = None

    def __post_init__(self) -> None:
        if self.axes:
            for axis in self.axes:
                if axis not in AXES:
                    raise ValueError(f"Invalid axis '{axis}' for homing.")

    def to_gcode(self) -> str:
        if not self.axes:
            return "G28"
        return f"G28 {' '.join(self.axes)}"


@dataclass(frozen=True)
class ProbeCommand(Command):
    axis: str
    target: int
    speed: int
    probe_type: str = "38.2"

    def __post_init__(self) -> None:
        if self.probe_type not in _VALID_PROBE_TYPES:
            raise ValueError(
                f"Invalid probe type '{self.probe_type}'. Must be one of {_VALID_PROBE_TYPES}."
            )
        if self.axis not in AXES:
            raise ValueError(f"Invalid probe axis '{self.axis}'.")

    def to_gcode(self) -> str:
        return f"G{self.probe_type} {self.axis}{self.target} F{self.speed}"


@dataclass(frozen=True)
class DebugInfoCommand(Command):
    pin: str

    def to_gcode(self) -> str:
        return f"M411 READ {self.pin}"
