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


class _TraceBus(QObject):
    event = pyqtSignal(object)


class CommandTracer:

    def __init__(self, robot):
        self.robot = robot
        self.bus = _TraceBus()
        self.lock = threading.Lock()
        self._orig_execute = robot.controller.execute
        robot.controller.execute = self._traced_execute

    def _traced_execute(self, command, **kwargs):
        line = command.render()
        with self.lock:
            try:
                resp = self._orig_execute(command, **kwargs)
            except Exception as exc:
                self.bus.event.emit(TraceEvent(line=line, ok=False, error=str(exc)))
                raise
        self.bus.event.emit(TraceEvent(line=line, ok=resp.ok, info=list(resp.info)))
        return resp

    def detach(self) -> None:
        self.robot.controller.execute = self._orig_execute
