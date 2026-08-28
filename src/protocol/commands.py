"""Structured controller commands and protocol-line rendering.

This module defines the command objects used to represent instructions sent
to the motion controller. Each concrete :class:`Command` encapsulates the
parameters of one firmware operation and renders itself to the corresponding
G-code or controller protocol line.

Command objects form the boundary between the higher-level robot API and the
controller wire format: code above this module works with typed command
objects rather than constructing protocol strings directly. Adding support
for a new firmware instruction should therefore generally consist of adding a
corresponding :class:`Command` subclass.

The module also defines :class:`ProbeMode` for the controller's probing
variants and provides shared helpers for formatting axis/value arguments.
Commands declare whether they are expected to produce a terminal
acknowledgement through :attr:`Command.acknowledges`, allowing the controller
driver to distinguish commands that require response synchronization from
silent configuration, stop, or reset operations.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from ..core import AxisId


def _num(v) -> str:
    """Format a numeric value for controller protocol output.

    Integer-valued floating-point inputs are rendered without a decimal
    portion; non-integral values retain their floating-point representation.

    Args:
        v: Numeric value to format.

    Returns:
        str: Compact string representation suitable for a controller command.
    """
    f = float(v)
    return str(int(f)) if f.is_integer() else repr(f)


def _axis_args(values: Mapping[AxisId, float]) -> str:
    """Render axis/value mappings as controller command arguments.

    Args:
        values: Mapping of axis identifiers to numeric target values.

    Returns:
        str: Space-separated axis/value arguments such as `"X10 Y20"`.
    """
    return " ".join(f"{a.letter}{_num(v)}" for a, v in values.items())


class Command:
    """Abstract representation of a single controller instruction.

    Concrete command subclasses encapsulate the parameters of a firmware
    instruction and render themselves to the corresponding controller
    protocol line. Higher-level code should operate on command objects rather
    than constructing wire-format strings directly.

    Attributes:
        acknowledges: Whether the controller is expected to return a
            terminal acknowledgement such as `ok` or `NOT ok` after the
            command. Commands that are silent or otherwise do not produce the
            expected acknowledgement set this to `False`.
    """

    acknowledges: ClassVar[bool] = True

    def render(self) -> str:
        """Render the command as a controller protocol line.

        Returns:
            str: Wire-format command suitable for transmission to the controller.

        Raises:
            NotImplementedError: Always raised by the base implementation.
                Concrete command classes must implement this method.
        """
        raise NotImplementedError


@dataclass
class RapidMove(Command):
    """Command for a rapid, non-linear-interpolated movement.

    Attributes:
        targets: Mapping of motion axes to their target positions.
    """

    targets: Mapping[AxisId, int]

    def render(self) -> str:
        """Render the rapid-movement command.

        Returns:
            str: `G0` command containing the configured axis targets.
        """
        return "G0 " + _axis_args(self.targets)


@dataclass
class LinearMove(Command):
    """Command for a linear movement to one or more axis targets.

    Attributes:
        targets: Mapping of motion axes to their target positions.
        feed: Optional feed rate for the movement.
    """

    targets: Mapping[AxisId, int]
    feed: int | None = None

    def render(self) -> str:
        """Render the linear-movement command.

        Returns:
            str: `G1` command containing the configured axis targets and,
            when specified, the feed rate.
        """
        s = "G1 " + _axis_args(self.targets)
        return s + (f" F{int(self.feed)}" if self.feed is not None else "")


@dataclass
class Home(Command):
    """Command for homing one or more controller axes.

    An empty axis sequence requests homing of all axes supported by the
    controller.

    Attributes:
        axes: Axes to home. Defaults to an empty sequence, indicating all
            axes.
    """

    axes: Sequence[AxisId] = ()

    def render(self) -> str:
        """Render the homing command.

        Returns:
            str: `G28` when all axes should be homed, or `G28` followed by the
            selected axis letters when specific axes are configured.
        """
        return "G28" if not self.axes else "G28 " + " ".join(a.letter for a in self.axes)


class ProbeMode(Enum):
    """Controller probing modes supported by the G38 command family.

    Each mode determines the direction of probing and whether failure to
    establish or release contact is treated as an error.

    Attributes:
        TOWARD_OR_FAIL: Probe toward the target and report an error if the
            target is reached without contact.
        TOWARD: Probe toward the target without treating no-contact as an
            error.
        AWAY_OR_FAIL: Probe away from the contact point and report an error if
            contact is not released.
        AWAY: Probe away without treating failure to release contact as an
            error.
    """

    TOWARD_OR_FAIL = "G38.2"  # error if target reached without contact
    TOWARD = "G38.3"  # no error on no-contact
    AWAY_OR_FAIL = "G38.4"  # error if contact never released
    AWAY = "G38.5"  # no error


@dataclass
class Probe(Command):
    """Command for performing a controller-supported probing movement.

    Attributes:
        axis: Axis along which the probe movement is performed.
        target: Target coordinate for the probing operation.
        feed: Optional probing feed rate.
        mode: Probing mode controlling direction and failure behavior.
            Defaults to :attr:`ProbeMode.TOWARD_OR_FAIL`.
    """

    axis: AxisId
    target: int
    feed: int | None = None
    mode: ProbeMode = ProbeMode.TOWARD_OR_FAIL

    def render(self) -> str:
        """Render the configured probing command.

        Returns:
            str: G38-family command containing the selected probing mode, axis,
            target, and optional feed rate.
        """
        s = f"{self.mode.value} {self.axis.letter}{int(self.target)}"
        return s + (f" F{int(self.feed)}" if self.feed is not None else "")


@dataclass
class SetAbsolute(Command):
    """Command that selects absolute positioning mode.

    Subsequent motion coordinates are interpreted as absolute positions
    relative to the controller's coordinate system.
    """

    def render(self) -> str:
        """Render the absolute-positioning command.

        Returns:
            str: `G90`.
        """
        return "G90"


@dataclass
class SetRelative(Command):
    """Command that selects relative positioning mode.

    Subsequent motion coordinates are interpreted as offsets relative to the
    current position.
    """

    def render(self) -> str:
        """Render the relative-positioning command.

        Returns:
            str: `G91`.
        """
        return "G91"


@dataclass
class ReportPosition(Command):
    """Command that requests the controller's current position."""

    def render(self) -> str:
        """Render the position-report command.

        Returns:
            str: `M114`.
        """
        return "M114"


@dataclass
class _PerAxisConfig(Command):
    """Base command for silent per-axis controller configuration.

    Concrete subclasses provide the firmware command code through the
    :attr:`code` class variable. These commands do not produce the terminal
    acknowledgement expected by normal controller commands.

    Attributes:
        values: Mapping of axes to their configured numeric values.
        code: Firmware command code emitted by the concrete subclass.
        acknowledges: Always `False` because these configuration commands
            are silent.
    """

    values: Mapping[AxisId, float]
    code: ClassVar[str] = ""
    acknowledges: ClassVar[bool] = False

    def render(self) -> str:
        """Render the per-axis configuration command.

        Returns:
            str: Firmware command code followed by the configured axis/value
            arguments.
        """
        return f"{self.code} " + _axis_args(self.values)


class SetHardLimits(_PerAxisConfig):
    """Configure per-axis hard-limit parameters.

    The command uses the firmware `M201` instruction and is silent at the
    protocol level.
    """

    code = "M201"


class SetAccelerations(_PerAxisConfig):
    """Configure per-axis acceleration parameters.

    The command uses the firmware `M204` instruction and is silent at the
    protocol level.
    """

    code = "M204"


class SetHomingSpeeds(_PerAxisConfig):
    """Configure per-axis homing speeds.

    The command uses the firmware `M210` instruction and is silent at the
    protocol level.
    """

    code = "M210"


class SetTravelSpeeds(_PerAxisConfig):
    """Configure per-axis travel speeds.

    The command uses the firmware `M220` instruction and is silent at the
    protocol level.
    """

    code = "M220"


class SetHomingRetract(_PerAxisConfig):
    """Configure per-axis homing retract distances.

    The command uses the firmware `M421` instruction and is silent at the
    protocol level.
    """

    code = "M421"


@dataclass
class QuickStop(Command):
    """Command for immediately stopping controller motion.

    This command is silent and therefore does not wait for a terminal
    acknowledgement from the controller.
    """

    acknowledges: ClassVar[bool] = False

    def render(self) -> str:
        """Render the quick-stop command.

        Returns:
            str: `M410`.
        """
        return "M410"


@dataclass
class EmergencyStop(Command):
    """Command for triggering the controller's emergency stop.

    This command is silent and does not wait for a terminal acknowledgement.
    """

    acknowledges: ClassVar[bool] = False

    def render(self) -> str:
        """Render the emergency-stop command.

        Returns:
            str: `M112`.
        """
        return "M112"


@dataclass
class Reset(Command):
    """Command for resetting or rebooting the controller.

    The reset command is silent and does not produce the normal terminal
    acknowledgement. A controller boot banner is expected after the reset.
    """

    acknowledges: ClassVar[bool] = False

    def render(self) -> str:
        """Render the controller reset command.

        Returns:
            str: `M30`.
        """
        return "M30"


@dataclass
class DisableLimits(Command):
    """Command for disabling controller motion limits."""

    def render(self) -> str:
        """Render the limit-disabling command.

        Returns:
            str: `M911`.
        """
        return "M911"


@dataclass
class MeasureDistance(Command):
    """Query one or more ultrasonic distance-sensor slots.

    The firmware `M412` command queries the selected ultrasonic sensor
    slots and returns a range response before the terminal `ok`. A reported
    value of `-1` indicates either that no echo was received or that the
    corresponding slot was not queried.

    The slot letters used by this command belong to the ultrasonic sensor
    protocol namespace and should not be interpreted as motion-axis
    coordinates, even though the same `AxisId` representation is used to
    encode them. For example, the Z slot currently corresponds to the
    physically connected rear sensor.

    Attributes:
        axes: Sensor slots to query. An empty tuple emits `M412` without
            slot arguments and therefore does not explicitly request any
            slot.
    """

    axes: tuple = ()  # which slot letters to query, e.g. (AxisId.Z,); () queries none

    def render(self) -> str:
        """Render the ultrasonic distance measurement command.

        Returns:
            str: ``M412`` followed by the selected sensor-slot letters when
            ``axes`` is non-empty.
        """
        s = "M412"
        if self.axes:
            s += " " + " ".join(a.letter for a in self.axes)
        return s
