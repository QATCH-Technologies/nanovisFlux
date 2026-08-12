from __future__ import annotations

import time

from .base import Transport

_SILENT = ("M201", "M204", "M210", "M220", "M421", "M112", "M30")


class FakeTransport(Transport):
    """In-memory controller simulator for tests and examples.

    Understands enough of the protocol to exercise the stack: the boot
    handshake, homing, absolute/relative moves, M114 reports, G38 probes
    (it "touches" at ``probe_contact[axis]`` and emits a [PRB:...] line), and
    M412 ultrasonic range reads (reports ``ultrasonic_mm``, emitting a
    [RNG:...] line -- see MeasureDistance for why this wire format is
    provisional). Mirrors the firmware quirk that the config setters reply
    with nothing.

    G1 (``LinearMove``) moves are simulated in real time rather than applied
    instantly: a move's target is reached only after ``distance / feed``
    seconds actually elapse (feed is microsteps/sec -- see
    firmware/docs/protocol.md), with the in-between position interpolated
    honestly on demand (see ``_settle``). This is what lets a quick stop
    (M410) genuinely cut a move short wherever it's gotten to, matching real
    hardware -- the reason JogController's begin_jog/end_jog continuous-move
    model (see control/jog.py) now works against this transport too, not
    just a real one. G0 (``RapidMove``) is deliberately left instant: nothing
    in this codebase feeds it a rate to simulate against (see
    ``commands.RapidMove.render`` -- no F term), and routines/safe_move_to
    use it for point-to-point repositioning where instant completion is the
    existing, relied-upon behavior.

    A real G1's "ok" isn't printed until the move itself finishes, not
    merely once it's queued (see JogController's docstring) -- this
    matters to anything that fires a G1 with ``wait_for_ok=False`` and
    polls *other* commands (M114/M412) while it's still in flight, e.g. a
    continuous topography sweep (scripts/scan_deck_topography.py): those
    polls' own responses must come back before the G1's belated "ok",
    not after. ``_pending_g1``/``_drain_pending_g1_oks`` reproduce that
    ordering here instead of queuing the "ok" the instant the G1 is sent.
    """

    def __init__(
        self,
        probe_contact: dict | None = None,
        ultrasonic_mm: float | None = None,
        axis_limits: dict | None = None,
    ):
        self._pos = {a: 0 for a in "XYZABC"}
        self._homed = {a: False for a in "XYZABC"}
        self._absolute = True
        self._queue: list[str] = []
        # in-flight G1 moves: axis -> (target, feed_steps_per_sec, start_pos, start_time)
        self._motion: dict[str, tuple] = {}
        # un-acked G1s awaiting completion, oldest first -- each is the set
        # of axes that move commanded. Real firmware doesn't print a G1's
        # "ok" until the move itself finishes (not merely once it's queued
        # -- see JogController's docstring), so a client that sent this
        # with wait_for_ok=False and is polling other commands (M114/M412)
        # in the meantime must see THEIR responses first, not this one
        # jumping the queue. See _drain_pending_g1_oks.
        self._pending_g1: list = []
        # microsteps at which each axis "contacts" during a G38 toward-probe
        self.probe_contact = {"Z": 120000, "A": 120000}
        if probe_contact:
            self.probe_contact.update(probe_contact)
        # simulated rear ultrasonic reading in mm; None = no echo / out of range
        self.ultrasonic_mm = ultrasonic_mm
        # Hard travel bounds per axis, [0, limit] microsteps -- mirrors a
        # real hard endstop: a commanded move just can't get any farther,
        # it doesn't wrap or go negative. 0 (home) is always the low bound
        # regardless of axis, matching the firmware convention (M114/report
        # only ever reports a non-negative microstep count -- see
        # report_position). Defaults from the same axis config the rest of
        # the app uses, so a jog aimed at "as far as it goes"
        # (JogController._restart_continuous targets endstop_limit) actually
        # stops there instead of sailing past into negative territory.
        from ..motion.axis import default_axis_configs

        self.axis_limits = {
            a.letter: cfg.endstop_limit for a, cfg in default_axis_configs().items()
        }
        if axis_limits:
            self.axis_limits.update(axis_limits)

    def open(self) -> None:
        self._queue += ["OpenFlux OT-2 Stepper Controller (simulated)", "ok"]

    def close(self) -> None:
        self._queue.clear()

    def write_line(self, line: str) -> None:
        self._settle()
        self._drain_pending_g1_oks()
        self._queue += self._handle(line.strip().upper())

    def read_line(self, timeout: float | None = None) -> str:
        return self._queue.pop(0) if self._queue else ""

    def reset_input_buffer(self) -> None:
        self._queue.clear()

    # -- crude firmware emulation -------------------------------------
    def _settle(self) -> None:
        """Advance every in-flight G1 move to where it actually is right
        now, given real elapsed wall-clock time -- called before handling
        any new line (see write_line) so position reads/reports and a
        quick stop always see an honest, current position rather than one
        that jumped straight to the commanded target."""
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
        """Queue "ok" for every pending G1 whose axes have all finished
        moving (per the _settle() that just ran), oldest first -- called
        right before handling whatever new line is being written, so an
        un-awaited G1's belated "ok" lands on the wire ahead of that new
        command's own response, exactly like real firmware interleaving
        motion completion with the next serial line it happens to read."""
        while self._pending_g1 and not (self._pending_g1[0] & self._motion.keys()):
            self._pending_g1.pop(0)
            self._queue.append("ok")

    @staticmethod
    def _axis_values(line: str) -> dict:
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
        limit = self.axis_limits.get(axis)
        value = max(0, value)
        if limit is not None:
            value = min(value, limit)
        return int(value)

    @staticmethod
    def _feed_value(line: str) -> float | None:
        i = line.find("F")
        if i < 0:
            return None
        j, num = i + 1, ""
        while j < len(line) and (line[j].isdigit() or line[j] in "+-."):
            num += line[j]
            j += 1
        return float(num) if num not in ("", "+", "-", ".") else None

    def _prb_line(self, contacted: bool) -> str:
        def val(a):
            return abs(self._pos[a]) if self._homed[a] else -1

        return f"[PRB:{val('X')},{val('Y')},{val('A')}:{1 if contacted else 0}]"

    def _handle(self, line: str) -> list:
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
            # A probe move takes over the axis outright; any jog it was
            # mid-flight on must stop first (mirrors real firmware
            # serializing motion commands).
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
                # "ok" deferred until every one of these axes finishes --
                # see _drain_pending_g1_oks, called at the top of the next
                # write_line -- rather than queued right away.
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
            # _settle() (called from write_line before we got here) already
            # froze _pos at wherever each move had actually gotten to; just
            # drop the in-flight targets so nothing keeps progressing. Also
            # drop any now-truncated G1's pending "ok" -- it's cut short,
            # not completed, so real firmware never sends it either.
            self._motion.clear()
            self._pending_g1.clear()
            return []
        if line.startswith("M911"):
            return ["Movement safety guards OFF.", "ok"]
        if line.startswith("M412"):
            # Only Z (the one physically wired sensor, see tools/ultrasonic.py)
            # ever reports a real reading; X/Y always read -1, matching real
            # firmware today -- see firmware/docs/protocol.md. Real M412
            # isn't free -- the firmware averages 10 ultrasonic samples,
            # each rate-limited to >=30ms (AlashUltrasonic::getDistance) --
            # so a real query costs at least ~300ms. A small sleep here
            # approximates that, so a continuous-sweep polling loop (see
            # scripts/scan_deck_topography.py) paces similarly to real
            # hardware against this transport instead of spinning as fast
            # as Python can loop and needing thousands of iterations to
            # cover one simulated G1's real-time travel.
            time.sleep(0.05)
            z = self.ultrasonic_mm if (self.ultrasonic_mm is not None and "Z" in line) else -1
            return [f"[RNG:-1,-1,{z}]", "ok"]
        if line.startswith(_SILENT):
            return []
        return ["ok"]
