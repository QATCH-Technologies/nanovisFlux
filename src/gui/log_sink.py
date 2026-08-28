from __future__ import annotations

from loguru import logger
from PyQt5.QtCore import QObject, pyqtSignal


class _LogBus(QObject):
    record = pyqtSignal(str, str)


def install_console_sink(console, level: str = "INFO") -> int:
    bus = _LogBus(console)
    bus.record.connect(console.append_log)
    return logger.add(
        lambda message: bus.record.emit(message.record["level"].name, message.record["message"]),
        level=level,
        format="{message}",
    )
