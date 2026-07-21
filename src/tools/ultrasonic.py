from __future__ import annotations
from .base import Tool
from ..protocol.responses import DistanceResult


class UltrasonicSensor(Tool):
    """A fixed-position ultrasonic distance sensor on the rear mount, behind
    the Z and A mounts. Unlike the pipette/probe tools it has no vertical
    axis of its own -- it's rigidly fixed to the gantry frame and only ever
    travels along with X/Y -- so it reports a range rather than driving any
    motion. Wraps the firmware's M412 range query (see
    protocol.commands.MeasureDistance); the exact firmware side is still
    provisional, so treat the wire format as easy to revisit.
    """
    name = "ultrasonic"

    def __init__(self, offset_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
                max_range_mm: float = 4000.0):
        super().__init__()
        # fixed offset from the gantry's X/Y reference point to the sensor's
        # sensing face (rear mount, so typically -Y and some +Z)
        self.offset_mm = offset_mm
        self.max_range_mm = max_range_mm

    def read(self) -> DistanceResult:
        """Trigger a ping and return the raw DistanceResult."""
        return self._robot.controller.measure_distance()

    def read_distance_mm(self) -> float | None:
        """Trigger a ping and return the measured distance in mm, or None if
        out of range / no echo."""
        return self.read().distance_mm
