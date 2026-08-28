from __future__ import annotations

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QPlainTextEdit

from . import style as S
from .trace import TraceEvent

_LEVEL_MARK = {"WARNING": "!", "ERROR": "✗", "CRITICAL": "✗", "SUCCESS": "✓"}


class ConsoleLog(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("console")
        self.setReadOnly(True)
        self.setMaximumBlockCount(4000)
        self.setFont(QFont(S.MONO_FONT, 9))

    def append_trace(self, ev: TraceEvent) -> None:
        self.appendPlainText(f"› {ev.line}")
        for line in ev.info:
            self.appendPlainText(f"  {line}")
        if ev.error:
            self.appendPlainText(f"  ✗ {ev.error}")
        else:
            self.appendPlainText(f"  → {'ok' if ev.ok else 'NOT ok'}")

    def append_log(self, level: str, message: str) -> None:
        mark = _LEVEL_MARK.get(level, "#")
        self.appendPlainText(f"{mark} {message}")
