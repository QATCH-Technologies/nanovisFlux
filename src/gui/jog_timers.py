"""Hold-to-repeat helpers for jog input.

FakeTransport executes every move synchronously and instantly -- there is no
"in flight" period a quick-stop (M410) can interrupt, and M410 is in the
firmware's own silent/no-op list besides (see transport/fake.py). So
JogController's begin_jog/end_jog model -- built for real, asynchronous
hardware, where a continuous move is cut short by a quick-stop -- does not
simulate meaningfully here: pressing a jog button would jump the axis the
*entire* relative distance (up to the endstop limit) in one instant.

Instead, keyboard holds, on-screen button holds, and gamepad deflection all
drive JogController.nudge() repeatedly while held -- one small bounded step
per tick -- which behaves correctly and identically against both
FakeTransport and real hardware.
"""
from __future__ import annotations

from PyQt5.QtCore import QObject, QTimer


class HoldRepeater(QObject):
    """Fires ``action()`` once immediately on start(), then again every
    ``interval_ms`` until stop() -- brackets one press/hold gesture.
    Any exception from ``action`` (e.g. "axis not homed") stops the repeat;
    the error itself already reaches the console via CommandTracer."""

    def __init__(self, action, interval_ms: int = 130, parent=None):
        super().__init__(parent)
        self.action = action
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._fire)

    def _fire(self) -> None:
        try:
            self.action()
        except Exception:
            self._timer.stop()

    def start(self) -> None:
        self._fire()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()


class RateAccumulator:
    """Turns a continuous rate (ticks/sec) into a whole number of discrete
    steps per call -- used to translate proportional gamepad stick
    deflection into a variable-rate stream of nudge() calls, without ever
    needing a "continuous move" the fake transport can't simulate."""

    def __init__(self):
        self._acc = 0.0

    def step(self, dt_s: float, rate_hz: float) -> int:
        if rate_hz <= 0:
            self._acc = 0.0
            return 0
        self._acc += dt_s * rate_hz
        n = int(self._acc)
        self._acc -= n
        return n

    def reset(self) -> None:
        self._acc = 0.0
