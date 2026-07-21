"""Instrumentation seam between the GUI and Controller.execute.

Controller.execute (see protocol/driver.py) is the one place in the whole
stack where a rendered G-code line and its parsed Response meet -- "nothing
above this class sees a G-code string; nothing below it understands one."
Wrapping it here gives one trace point that sees every command a manual jog,
a routine step, or a calibration touch-off ever sends, instead of
instrumenting each call site separately.
"""
from __future__ import annotations
import threading
from dataclasses import dataclass, field

from PyQt5.QtCore import QObject, pyqtSignal


@dataclass
class TraceEvent:
    line: str
    ok: bool = True
    info: list = field(default_factory=list)
    error: str | None = None
    source: str = "cmd"  # "cmd" | "note" (a plain human-readable log line, no wire traffic)


class _TraceBus(QObject):
    event = pyqtSignal(object)  # TraceEvent -- emitted possibly from a worker thread;
    # PyQt auto-queues delivery to slots living on a different thread than the
    # emitter, so ConsoleLog never has to worry about cross-thread paint calls.


class CommandTracer:
    """Wraps ``robot.controller.execute`` to broadcast every command/response
    pair, and serializes concurrent callers (manual jog vs. a routine thread)
    onto the single transport underneath.

    Serialization here only protects individual G-code lines from
    interleaving -- it does NOT make a multi-command robot method (e.g.
    ``safe_move_to``'s lift/travel/descend) atomic as a whole. Callers that
    need that guarantee (the routine runner) must additionally suspend
    manual jog input for the run's duration; see MainWindow._set_routine_active.
    """

    def __init__(self, robot):
        self.robot = robot
        self.bus = _TraceBus()
        self.lock = threading.Lock()
        self._orig_execute = robot.controller.execute
        robot.controller.execute = self._traced_execute

    def note(self, message: str) -> None:
        """Post a plain human-readable line (not a wire command) to the console."""
        self.bus.event.emit(TraceEvent(line=message, source="note"))

    def _traced_execute(self, command):
        line = command.render()
        with self.lock:
            try:
                resp = self._orig_execute(command)
            except Exception as exc:
                self.bus.event.emit(TraceEvent(line=line, ok=False, error=str(exc)))
                raise
        self.bus.event.emit(TraceEvent(line=line, ok=resp.ok, info=list(resp.info)))
        return resp

    def detach(self) -> None:
        self.robot.controller.execute = self._orig_execute
