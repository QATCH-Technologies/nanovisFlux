"""Wires loguru into the GUI's ConsoleLog widget.

A loguru sink is just a callable invoked with each formatted record --
this bridges that into ConsoleLog.append_log via a signal, so it's safe to
call from any thread (routine runs, gamepad polling, calibration work all
log from their own threads, not just the GUI thread) -- same idea as
CommandTracer's _TraceBus in trace.py, applied to general log messages
instead of wire-level command traces.
"""
from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal
from loguru import logger


class _LogBus(QObject):
    record = pyqtSignal(str, str)  # level name, formatted message


def install_console_sink(console, level: str = "INFO") -> int:
    """Make ``console`` (a ConsoleLog) show every log record from here on,
    in addition to whatever other sinks loguru already has (e.g. the
    default stderr sink, still useful when the GUI is launched from a
    terminal). Returns the sink id, for logger.remove() if ever needed."""
    bus = _LogBus(console)
    bus.record.connect(console.append_log)
    return logger.add(
        lambda message: bus.record.emit(message.record["level"].name, message.record["message"]),
        level=level,
        format="{message}",
    )
