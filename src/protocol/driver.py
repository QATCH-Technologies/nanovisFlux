from __future__ import annotations

from collections.abc import Callable, Mapping

from ..core import AxisId
from ..transport.base import Transport
from . import commands as cmd
from .commands import Command
from .errors import TransportError, map_error
from .responses import (
    DistanceResult,
    ProbeResult,
    Response,
    extract_reason,
    parse_distance,
    parse_position,
    parse_probe,
)


class Controller:
    """Translate structured commands into controller communication and results.

    The controller forms the boundary between the typed command layer and the
    underlying :class:`Transport`. Callers provide :class:`Command` objects
    rather than protocol strings, while responses are converted into typed
    result objects or controller-specific exceptions.

    The controller owns the transport lifecycle, manages command
    acknowledgement behavior, applies response timeouts, and optionally
    invokes a send hook for logging or execution tracing.

    Attributes:
        on_send: Optional callback invoked immediately before a rendered
            command is written to the transport. The callback receives the
            rendered protocol line and its originating :class:`Command`.
        banner: Lines received from the controller during :meth:`open`,
            typically containing the firmware boot banner.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        timeout: float = 30.0,
        on_send: Callable[[str, Command], None] | None = None,
    ):
        """Initialize a controller around a transport.

        Args:
            transport: Transport implementation used to communicate with the
                motion controller.
            timeout: Maximum time, in seconds, to wait for an individual
                controller response.
            on_send: Optional callback invoked immediately before each command is
                written. It receives the rendered protocol line and the original
                command object.
        """
        self._t = transport
        self._timeout = timeout
        self.on_send = on_send
        self.banner: list[str] = []

    def open(self) -> None:
        """Open the transport and consume the controller's startup response.

        The transport is opened first, after which incoming lines are drained
        through the controller's terminal `ok` response. Lines received before
        `ok` are stored in :attr:`banner`.

        Raises:
            TransportError: If the underlying transport fails while opening or
                reading the startup response.
        """
        self._t.open()
        self.banner = self._drain_to_ok()

    def close(self) -> None:
        """Close the underlying controller transport.

        This method delegates transport shutdown to the configured
        :class:`Transport`.
        """
        self._t.close()

    def __enter__(self) -> Controller:  # noqa
        """Open the controller for use as a context manager.

        Returns:
            Controller: This controller instance after its transport has been
            opened and its startup response consumed.
        """
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        """Close the controller when leaving a context manager.

        Args:
            *exc: Context-manager exception information. The values are accepted
                for protocol compatibility but are not otherwise used.
        """
        self.close()

    def execute(
        self,
        command: Command,
        *,
        wait_for_ok: bool | None = None,
    ) -> Response:
        """Render, send, and optionally await acknowledgement for a command.

        The command is rendered into its controller protocol representation and
        passed to the optional :attr:`on_send` callback before being written to
        the transport. By default, the controller waits for a terminal
        acknowledgement according to :attr:`Command.acknowledges`.

        `wait_for_ok` can override the command's default acknowledgement
        behavior for individual calls. When acknowledgement waiting is disabled,
        a synthetic successful response is returned immediately; any eventual
        controller response remains in the transport input stream and must be
        handled before a subsequent command that expects a clean response.

        Args:
            command: Structured controller command to execute.
            wait_for_ok: Optional override controlling whether to wait for the
                terminal `ok` or `NOT ok` response. When `None`, uses the
                command's :attr:`Command.acknowledges` value.

        Returns:
            Response: Controller response when acknowledgement is awaited, or a
            synthetic successful response with status `"(no ack)"` when waiting
            is disabled.

        Raises:
            TransportError: If the controller does not provide a response before
                the configured timeout.
            ControllerError: If the controller returns a `NOT ok` response.
        """
        line = command.render()
        if self.on_send:
            self.on_send(line, command)
        self._t.write_line(line)
        should_wait = command.acknowledges if wait_for_ok is None else wait_for_ok
        if not should_wait:
            return Response(ok=True, info=[], status="(no ack)")
        return self._read_response()

    def reset_input_buffer(self) -> None:
        """Discard unread data currently buffered by the transport.

        This is useful after commands executed without waiting for acknowledgement
        when a later command requires a clean response stream.
        """
        self._t.reset_input_buffer()

    def _read_response(self) -> Response:
        """Read and parse a terminal controller response.

        Informational lines are accumulated until a terminal `ok` or
        `NOT ok` response is received.

        Returns:
            Response: Successful controller response containing any informational
            lines received before the terminal acknowledgement.

        Raises:
            TransportError: If no response is received before the configured
                timeout.
            ControllerError: If the controller returns a `NOT ok` response. The
                raw response is preserved on the raised typed exception.
        """
        info: list[str] = []
        while True:
            line = self._t.read_line(self._timeout)
            if line == "":
                raise TransportError("timed out waiting for controller response")
            if line == "ok":
                return Response(ok=True, info=info, status=line)
            if line.startswith("NOT ok"):
                reason = extract_reason(line)
                raise map_error(reason, Response(False, info, line, reason))
            info.append(line)

    def _drain_to_ok(self) -> list[str]:
        """Consume controller startup output through its terminal acknowledgement.

        At most 64 lines are read. Informational lines received before `ok` are
        returned for storage as the controller's startup banner.

        Returns:
            list[str]: Informational lines received before the terminal `ok`
            response, or before the read limit is reached.
        """
        info: list[str] = []
        for _ in range(64):
            line = self._t.read_line(self._timeout)
            if line in ("", "ok"):
                break
            info.append(line)
        return info

    def home(self, *axes: AxisId) -> Response:
        """Home one or more controller axes.

        Args:
            *axes: Axes to home. When no axes are provided, the controller's home
                command requests homing of all axes.

        Returns:
            Response: Controller acknowledgement for the homing command.
        """
        return self.execute(cmd.Home(tuple(axes)))

    def rapid_move(self, targets: Mapping[AxisId, int]) -> Response:
        """Execute a rapid movement to the specified axis targets.

        Args:
            targets: Mapping of axes to their target positions.

        Returns:
            Response: Controller acknowledgement for the movement.
        """
        return self.execute(cmd.RapidMove(dict(targets)))

    def linear_move(
        self,
        targets: Mapping[AxisId, int],
        feed: int | None = None,
        *,
        wait_for_ok: bool | None = None,
    ) -> Response:
        """Execute a linear movement to the specified axis targets.

        Args:
            targets: Mapping of axes to their target positions.
            feed: Optional feed rate for the movement.
            wait_for_ok: Optional override controlling whether execution waits for
                the controller's terminal acknowledgement.

        Returns:
            Response: Controller response, or a synthetic response when
            acknowledgement waiting is disabled.
        """
        return self.execute(cmd.LinearMove(dict(targets), feed), wait_for_ok=wait_for_ok)

    def set_absolute(self) -> Response:
        """Select absolute positioning mode.

        Returns:
            Response: Controller acknowledgement for the mode change.
        """
        return self.execute(cmd.SetAbsolute())

    def set_relative(self) -> Response:
        """Select relative positioning mode.

        Returns:
            Response: Controller acknowledgement for the mode change.
        """
        return self.execute(cmd.SetRelative())

    def report_position(self) -> dict[AxisId, int]:
        """Query and parse the controller's current axis positions.

        Returns:
            dict[AxisId, int]: Mapping of axis identifiers to their reported
            positions.
        """
        return parse_position(self.execute(cmd.ReportPosition()).info)

    def probe(
        self,
        axis: AxisId,
        target: int,
        feed: int | None = None,
        mode: cmd.ProbeMode = cmd.ProbeMode.TOWARD_OR_FAIL,
    ) -> ProbeResult:
        """Perform a probing movement and parse its probe result.

        Args:
            axis: Axis along which the probing movement is performed.
            target: Target position for the probe movement.
            feed: Optional probing feed rate.
            mode: Probing mode controlling direction and failure behavior.

        Returns:
            ProbeResult: Parsed probe result. If the controller response does not
            contain a probe result, an unsuccessful empty result is returned.

        Raises:
            ControllerError: If the controller reports a probing failure.
        """
        resp = self.execute(cmd.Probe(axis, target, feed, mode))
        return parse_probe(resp.info) or ProbeResult(False, {})

    def measure_distance(self, *axes: AxisId) -> DistanceResult:
        """Query and parse ultrasonic distance measurements.

        Args:
            *axes: Sensor slots to query. The interpretation of these identifiers
                follows the ultrasonic distance command protocol rather than the
                motion-axis semantics.

        Returns:
            DistanceResult: Parsed distance measurements. If the controller
            response does not contain a distance result, an empty result with
            `None` values is returned.

        Raises:
            ControllerError: If the controller rejects the measurement command.
        """
        resp = self.execute(cmd.MeasureDistance(tuple(axes)))
        return parse_distance(resp.info) or DistanceResult(None, None, None)

    def set_hard_limits(self, limits: Mapping[AxisId, int]) -> None:
        """Configure hard-limit parameters for controller axes.

        Args:
            limits: Mapping of axes to their hard-limit configuration values.
        """
        self.execute(cmd.SetHardLimits(dict(limits)))

    def emergency_stop(self) -> None:
        """Trigger the controller's emergency stop.

        The underlying command does not wait for a terminal acknowledgement.
        """
        self.execute(cmd.EmergencyStop())

    def quick_stop(self) -> None:
        """Immediately stop controller motion.

        The underlying quick-stop command does not wait for a terminal
        acknowledgement.
        """
        self.execute(cmd.QuickStop())
