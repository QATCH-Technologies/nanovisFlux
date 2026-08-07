from __future__ import annotations
from typing import Callable, Mapping
from ..core import AxisId
from ..transport.base import Transport
from . import commands as cmd
from .commands import Command
from .responses import (Response, ProbeResult, DistanceResult, extract_reason,
                        parse_position, parse_probe, parse_distance)
from .errors import map_error, TransportError


class Controller:
    """Owns a Transport and turns Command objects into typed results.

    This is the seam between objects and the wire. Nothing above this class
    sees a G-code string; nothing below it understands one.
    """

    def __init__(self, transport: Transport, *, timeout: float = 30.0,
                 on_send: Callable[[str, Command], None] | None = None):
        self._t = transport
        self._timeout = timeout
        #: hook fired with (rendered line, source Command) just before it's
        #: written -- e.g. logging, or capturing a move's intended target
        #: (see RoutineRunner) rather than the rendered string.
        self.on_send = on_send
        self.banner: list[str] = []

    # -- lifecycle ----------------------------------------------------
    def open(self) -> None:
        self._t.open()
        self.banner = self._drain_to_ok()  # firmware prints a boot banner + ok

    def close(self) -> None:
        self._t.close()

    def __enter__(self) -> "Controller":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- core execution ----------------------------------------------
    def execute(self, command: Command, *, wait_for_ok: bool | None = None) -> Response:
        """Send ``command``. By default waits for a terminal 'ok'/'NOT ok'
        exactly when ``command.acknowledges`` says to; pass ``wait_for_ok``
        to override that per call -- e.g. a continuous jog's move is fired
        without waiting (see JogController), so a stick release isn't stuck
        behind a G1 whose 'ok' the firmware may not send until the move
        itself finishes. When skipping the wait, call reset_input_buffer()
        before the next command that DOES need a clean response to read,
        so that eventual late reply doesn't get parsed as its answer."""
        line = command.render()
        if self.on_send:
            self.on_send(line, command)
        self._t.write_line(line)
        should_wait = command.acknowledges if wait_for_ok is None else wait_for_ok
        if not should_wait:
            return Response(ok=True, info=[], status="(no ack)")
        return self._read_response()

    def reset_input_buffer(self) -> None:
        self._t.reset_input_buffer()

    def _read_response(self) -> Response:
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
        info: list[str] = []
        for _ in range(64):
            line = self._t.read_line(self._timeout)
            if line in ("", "ok"):
                break
            info.append(line)
        return info

    # -- typed convenience API (still objects underneath) ------------
    def home(self, *axes: AxisId) -> Response:
        return self.execute(cmd.Home(tuple(axes)))

    def rapid_move(self, targets: Mapping[AxisId, int]) -> Response:
        return self.execute(cmd.RapidMove(dict(targets)))

    def linear_move(self, targets: Mapping[AxisId, int], feed: int | None = None,
                    *, wait_for_ok: bool | None = None) -> Response:
        return self.execute(cmd.LinearMove(dict(targets), feed), wait_for_ok=wait_for_ok)

    def set_absolute(self) -> Response:
        return self.execute(cmd.SetAbsolute())

    def set_relative(self) -> Response:
        return self.execute(cmd.SetRelative())

    def report_position(self) -> dict[AxisId, int]:
        return parse_position(self.execute(cmd.ReportPosition()).info)

    def probe(self, axis: AxisId, target: int, feed: int | None = None,
              mode: cmd.ProbeMode = cmd.ProbeMode.TOWARD_OR_FAIL) -> ProbeResult:
        resp = self.execute(cmd.Probe(axis, target, feed, mode))
        return parse_probe(resp.info) or ProbeResult(False, {})

    def measure_distance(self) -> DistanceResult:
        resp = self.execute(cmd.MeasureDistance())
        return parse_distance(resp.info) or DistanceResult(False, None)

    def set_hard_limits(self, limits: Mapping[AxisId, int]) -> None:
        self.execute(cmd.SetHardLimits(dict(limits)))

    def emergency_stop(self) -> None:
        self.execute(cmd.EmergencyStop())

    def quick_stop(self) -> None:
        self.execute(cmd.QuickStop())
