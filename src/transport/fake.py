from __future__ import annotations
from .base import Transport

_SILENT = ("M201", "M204", "M210", "M220", "M421", "M410", "M112", "M30")


class FakeTransport(Transport):
    """In-memory controller simulator for tests and examples.

    Understands enough of the protocol to exercise the stack: the boot
    handshake, homing, absolute/relative moves, M114 reports, G38 probes
    (it "touches" at ``probe_contact[axis]`` and emits a [PRB:...] line), and
    M412 ultrasonic range reads (reports ``ultrasonic_mm``, emitting a
    [RNG:...] line -- see MeasureDistance for why this wire format is
    provisional). Mirrors the firmware quirk that the config setters reply
    with nothing.
    """

    def __init__(self, probe_contact: dict | None = None, ultrasonic_mm: float | None = None):
        self._pos = {a: 0 for a in "XYZABC"}
        self._homed = {a: False for a in "XYZABC"}
        self._absolute = True
        self._queue: list[str] = []
        # microsteps at which each axis "contacts" during a G38 toward-probe
        self.probe_contact = {"Z": 120000, "A": 120000}
        if probe_contact:
            self.probe_contact.update(probe_contact)
        # simulated rear ultrasonic reading in mm; None = no echo / out of range
        self.ultrasonic_mm = ultrasonic_mm

    def open(self) -> None:
        self._queue += ["OpenFlux OT-2 Stepper Controller (simulated)", "ok"]

    def close(self) -> None:
        self._queue.clear()

    def write_line(self, line: str) -> None:
        self._queue += self._handle(line.strip().upper())

    def read_line(self, timeout: float | None = None) -> str:
        return self._queue.pop(0) if self._queue else ""

    # -- crude firmware emulation -------------------------------------
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
                self._pos[a], self._homed[a] = 0, True
            return [f"Homed {a}." for a in axes] + ["ok"]
        if line.startswith("G38"):
            vals = self._axis_values(line)
            toward = line.startswith(("G38.2", "G38.3"))
            for a, target in vals.items():
                contact = self.probe_contact.get(a)
                if toward and contact is not None and abs(contact) <= abs(target):
                    self._pos[a] = contact
                    return [self._prb_line(True), "ok"]
                self._pos[a] = target
            return [self._prb_line(False), "ok"]
        if line.startswith(("G0", "G1")):
            for a, v in self._axis_values(line).items():
                self._pos[a] = (self._pos[a] + v) if not self._absolute else v
            return ["ok"]
        if line.startswith("M114"):
            body = " ".join(
                f"{a}:{abs(self._pos[a]) if self._homed[a] else -1}" for a in "XYZABC")
            return [" " + body, "ok"]
        if line.startswith("M911"):
            return ["Movement safety guards OFF.", "ok"]
        if line.startswith("M412"):
            val = self.ultrasonic_mm if self.ultrasonic_mm is not None else -1
            return [f"[RNG:{val}]", "ok"]
        if line.startswith(_SILENT):
            return []
        return ["ok"]
