"""
In-memory transport that simulates the instrument controller protocol.

This module provides :class:`SimulatedTransport`, a test-oriented
implementation of :class:`~.base.Transport` that emulates the subset of
controller behavior required by the motion-control stack.

The simulator supports controller startup and shutdown, absolute and
relative
positioning, homing, linear and rapid moves, position reporting, probing,
ultrasonic distance measurements, emergency stops, and selected firmware
configuration commands. It also models controller behaviors that affect
higher-level code, including deferred `G1` completion responses and
real-time linear motion.

Unlike rapid moves, simulated `G1` moves progress according to elapsed
wall-clock time and their configured feed rate. Position queries therefore
report interpolated in-flight positions, allowing tests of jogging, stopping,
polling, and motion verification to exercise behavior closer to real
hardware.

The simulator also models configurable axis travel limits, probe contact
positions, and ultrasonic measurements, making it suitable for deterministic
motion-control tests without requiring physical hardware.
"""

from __future__ import annotations

import time

from .base import Transport

_SILENT = ("M201", "M204", "M210", "M220", "M421", "M112", "M30")


class SimulatedTransport(Transport):
    """Simulate a line-oriented instrument controller entirely in memory.

    `SimulatedTransport` implements :class:`Transport` without requiring
    physical hardware. It accepts controller commands as text lines and
    produces protocol-compatible response lines through an internal queue.

    The simulator supports the protocol operations required by the motion
    stack, including:

    * Controller startup and shutdown responses.
    * Absolute (`G90`) and relative (`G91`) positioning.
    * Homing (`G28`).
    * Linear moves (`G1`) with real-time position interpolation.
    * Rapid moves (`G0`).
    * Position reporting (`M114`).
    * Probe moves (`G38`) and `[PRB:...]` responses.
    * Ultrasonic range queries (`M412`) and `[RNG:...]` responses.
    * Quick-stop behavior (`M410`).
    * Selected silent firmware configuration commands.

    Linear moves are modeled using wall-clock time and feed rate rather than
    completing immediately. This allows callers to observe intermediate
    positions and interrupt an in-flight move. Completion responses for
    asynchronous `G1` commands are deferred until the corresponding motion
    has actually finished.

    Axis positions are constrained to configured travel limits. Homing marks
    axes as homed and resets their positions to zero. Unhomed axes are
    reported using the simulator's negative-position convention.

    Args:
        probe_contact: Optional mapping of axis identifiers to simulated
            probe-contact positions in microsteps.
        ultrasonic_mm: Optional simulated ultrasonic distance in millimeters.
            `None` represents no valid ultrasonic echo.
        axis_limits: Optional mapping of axis identifiers to maximum travel
            positions in microsteps. Default limits are taken from the
            application's standard axis configuration.

    Attributes:
        probe_contact: Simulated probe-contact position for each configured
            axis.
        ultrasonic_mm: Simulated rear ultrasonic distance in millimeters, or
            `None` when no valid reading is available.
        axis_limits: Maximum permitted position for each axis in microsteps.
    """

    def __init__(
        self,
        probe_contact: dict | None = None,
        ultrasonic_mm: float | None = None,
        axis_limits: dict | None = None,
    ):
        """Initialize an in-memory controller simulator.

        The simulator starts with all axes at position zero but marked as
        unhomed. Default axis travel limits are loaded from the application's
        standard axis configuration and may be overridden for individual axes.

        Args:
            probe_contact: Optional mapping of axis identifiers to simulated
                probe-contact positions in microsteps.
            ultrasonic_mm: Optional simulated ultrasonic distance in millimeters.
                `None` indicates that no ultrasonic echo is available.
            axis_limits: Optional mapping of axis identifiers to maximum travel
                positions in microsteps.
        """
        self._pos = {a: 0 for a in "XYZABC"}
        self._homed = {a: False for a in "XYZABC"}
        self._absolute = True
        self._queue: list[str] = []
        self._motion: dict[str, tuple] = {}
        self._pending_g1: list = []
        self.probe_contact = {"Z": 120000, "A": 120000}
        if probe_contact:
            self.probe_contact.update(probe_contact)
        self.ultrasonic_mm = ultrasonic_mm
        from ..motion.axis import default_axis_configs

        self.axis_limits = {
            a.letter: cfg.endstop_limit for a, cfg in default_axis_configs().items()
        }
        if axis_limits:
            self.axis_limits.update(axis_limits)

    def open(self) -> None:
        """Simulate opening the controller connection.

        A simulated controller startup message followed by `"ok"` is placed
        into the response queue.
        """
        self._queue += ["OpenFlux OT-2 Stepper Controller (simulated)", "ok"]

    def close(self) -> None:
        """Simulate closing the controller connection.

        Any queued responses are discarded.
        """
        self._queue.clear()

    def write_line(self, line: str) -> None:
        """Process one controller command line.

        In-flight linear motion is first advanced to its current wall-clock
        position and any completed deferred `G1` acknowledgements are queued.
        The supplied command is then normalized and passed to the protocol
        handler.

        Args:
            line: Controller command to process.
        """
        self._settle()
        self._drain_pending_g1_oks()
        self._queue += self._handle(line.strip().upper())

    def read_line(self, timeout: float | None = None) -> str:
        """Read one simulated controller response.

        The method polls briefly while an in-flight move is progressing so that
        deferred `G1` completion acknowledgements can become available after
        sufficient simulated wall-clock time has elapsed.

        Args:
            timeout: Maximum time to wait for a response, in seconds. `None`
                waits until a response becomes available or there is no remaining
                in-flight motion.

        Returns:
            The next queued response line, or an empty string if the timeout
            expires or no response can be produced.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            self._settle()
            self._drain_pending_g1_oks()
            if self._queue:
                return self._queue.pop(0)
            if not self._motion:
                return ""
            if deadline is not None and time.monotonic() >= deadline:
                return ""
            time.sleep(0.01)

    def reset_input_buffer(self) -> None:
        """Discard all currently queued controller responses."""
        self._queue.clear()

    def _settle(self) -> None:
        """Advance in-flight linear moves to their current positions.

        Each active `G1` move is interpolated according to its feed rate and
        elapsed wall-clock time. Completed moves are placed exactly at their
        targets and removed from the in-flight motion registry.

        This method allows position reports and stop commands to observe the
        simulated position reached at the actual time the operation is queried.
        """
        if not self._motion:
            return
        now = time.monotonic()
        finished = []
        for axis, (target, feed, start, t0) in self._motion.items():
            direction = 1 if target >= start else -1
            traveled = feed * (now - t0)
            pos = start + direction * traveled
            if (direction > 0 and pos >= target) or (direction < 0 and pos <= target):
                self._pos[axis] = target
                finished.append(axis)
            else:
                self._pos[axis] = int(pos)
        for axis in finished:
            del self._motion[axis]

    def _drain_pending_g1_oks(self) -> None:
        """Queue completion acknowledgements for finished linear moves.

        Pending `G1` commands are processed in submission order. An `"ok"`
        response is queued only after all axes associated with the oldest pending
        move have finished moving.

        This preserves the response ordering expected from firmware when a
        non-blocking linear move is followed by commands whose responses may
        arrive while that move remains in progress.
        """
        while self._pending_g1 and not (self._pending_g1[0] & self._motion.keys()):
            self._pending_g1.pop(0)
            self._queue.append("ok")

    @staticmethod
    def _axis_values(line: str) -> dict:
        """Extract axis/value pairs from a controller command.

        Args:
            line: Uppercase controller command containing zero or more axis
                identifiers followed by integer values.

        Returns:
            A mapping from axis letters to parsed integer values.
        """
        out = {}
        for a in "XYZABC":
            i = line.find(a)
            if i < 0:
                continue
            j, num = i + 1, ""
            while j < len(line) and (line[j].isdigit() or line[j] in "+-"):
                num += line[j]
                j += 1
            if num not in ("", "+", "-"):
                out[a] = int(num)
        return out

    def _clamp(self, axis: str, value: float) -> int:
        """Clamp an axis position to its configured travel range.

        Positions below zero are clamped to zero. If a maximum travel limit is
        configured for the axis, values above that limit are clamped to the
        limit.

        Args:
            axis: Axis identifier.
            value: Requested position in microsteps.

        Returns:
            The position constrained to the axis's valid travel range.
        """
        limit = self.axis_limits.get(axis)
        value = max(0, value)
        if limit is not None:
            value = min(value, limit)
        return int(value)

    @staticmethod
    def _feed_value(line: str) -> float | None:
        """Extract the feed-rate value from a controller command.

        Args:
            line: Controller command containing an optional `F` parameter.

        Returns:
            The parsed feed rate, or `None` when no valid feed value is present.
        """
        i = line.find("F")
        if i < 0:
            return None
        j, num = i + 1, ""
        while j < len(line) and (line[j].isdigit() or line[j] in "+-."):
            num += line[j]
            j += 1
        return float(num) if num not in ("", "+", "-", ".") else None

    def _prb_line(self, contacted: bool) -> str:
        """Build a simulated probe-result response.

        Homed axes report their current absolute positions while unhomed axes
        report `-1`. The response includes whether the simulated probe move
        contacted its configured target.

        Args:
            contacted: Whether the probe operation detected simulated contact.

        Returns:
            A controller-compatible `[PRB:...]` response line.
        """

        def val(a):
            return abs(self._pos[a]) if self._homed[a] else -1

        return f"[PRB:{val('X')},{val('Y')},{val('A')}:{1 if contacted else 0}]"

    def _handle(self, line: str) -> list:
        """Handle a normalized controller command.

        The command is interpreted according to the subset of firmware behavior
        modeled by the simulator. Motion state, homing state, response ordering,
        and simulated sensor results are updated as appropriate.

        Args:
            line: Normalized uppercase controller command.

        Returns:
            A list of response lines generated immediately by the command.
            Deferred responses, such as completion acknowledgements for in-flight
            ``G1`` moves, are queued separately.
        """
        if line.startswith("G90"):
            self._absolute = True
            return ["Absolute mode set.", "ok"]
        if line.startswith("G91"):
            self._absolute = False
            return ["Relative mode set.", "ok"]
        if line.startswith("G28"):
            axes = [a for a in "XYZABC" if a in line] or list("XYZAB")
            for a in axes:
                self._motion.pop(a, None)
                self._pos[a], self._homed[a] = 0, True
            self._pending_g1.clear()  # homing takes over outright, same as G38 below
            return [f"Homed {a}." for a in axes] + ["ok"]
        if line.startswith("G38"):
            self._motion.clear()
            self._pending_g1.clear()
            vals = self._axis_values(line)
            toward = line.startswith(("G38.2", "G38.3"))
            for a, target in vals.items():
                contact = self.probe_contact.get(a)
                if toward and contact is not None and abs(contact) <= abs(target):
                    self._pos[a] = self._clamp(a, contact)
                    return [self._prb_line(True), "ok"]
                self._pos[a] = self._clamp(a, target)
            return [self._prb_line(False), "ok"]
        if line.startswith("G1"):
            feed = self._feed_value(line)
            axes_this_move = set()
            for a, v in self._axis_values(line).items():
                target = self._clamp(a, (self._pos[a] + v) if not self._absolute else v)
                if feed and feed > 0 and target != self._pos[a]:
                    self._motion[a] = (target, float(feed), self._pos[a], time.monotonic())
                    axes_this_move.add(a)
                else:
                    self._pos[a] = target
                    self._motion.pop(a, None)
            if axes_this_move:
                self._pending_g1.append(axes_this_move)
                return []
            return ["ok"]
        if line.startswith("G0"):
            for a, v in self._axis_values(line).items():
                self._pos[a] = self._clamp(a, (self._pos[a] + v) if not self._absolute else v)
                self._motion.pop(a, None)
            return ["ok"]
        if line.startswith("M114"):
            body = " ".join(f"{a}:{abs(self._pos[a]) if self._homed[a] else -1}" for a in "XYZABC")
            return [" " + body, "ok"]
        if line.startswith("M410"):
            self._motion.clear()
            self._pending_g1.clear()
            return []
        if line.startswith("M911"):
            return ["Movement safety guards OFF.", "ok"]
        if line.startswith("M412"):
            time.sleep(0.05)
            z = self.ultrasonic_mm if (self.ultrasonic_mm is not None and "Z" in line) else -1
            return [f"[RNG:-1,-1,{z}]", "ok"]
        if line.startswith(_SILENT):
            return []
        return ["ok"]
