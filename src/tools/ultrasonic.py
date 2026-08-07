from __future__ import annotations
from ..core import AxisId, MountSide
from .base import Tool
from ..protocol.responses import DistanceResult

#: Which M412 slot letter answers for a sensor mounted on each side. REAR is
#: the one confirmed/wired mapping today (see firmware/docs/protocol.md's
#: M412 worked example -- the sole physical sensor answers on the Z slot).
#: LEFT/X and RIGHT/Y are a forward-looking, provisional extension for if/
#: when a sensor is ever mounted there -- update alongside the firmware once
#: real hardware exists on those slots.
_MOUNT_RANGE_SLOT = {MountSide.LEFT: AxisId.X, MountSide.RIGHT: AxisId.Y, MountSide.REAR: AxisId.Z}


class UltrasonicSensor(Tool):
    """A fixed-position ultrasonic distance sensor, typically on the rear
    mount, behind the Z and A mounts. Unlike the pipette/probe tools it has
    no vertical axis of its own -- it's rigidly fixed to the gantry frame
    and only ever travels along with X/Y -- so it reports a range rather
    than driving any motion. Wraps the firmware's M412 range query (see
    protocol.commands.MeasureDistance), querying whichever slot letter
    corresponds to the mount it's attached to (see _MOUNT_RANGE_SLOT).
    """
    name = "ultrasonic"

    def __init__(self, offset_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
                max_range_mm: float = 4000.0):
        super().__init__()
        # fixed offset from the gantry's X/Y reference point to the sensor's
        # sensing face (rear mount, so typically -Y and some +Z)
        self.offset_mm = offset_mm
        self.max_range_mm = max_range_mm

    def _slot(self) -> AxisId:
        side = self._mount.side if self._mount is not None else None
        return _MOUNT_RANGE_SLOT.get(side, AxisId.Z)

    def read(self) -> DistanceResult:
        """Trigger a ping (on this mount's M412 slot) and return the raw
        DistanceResult (all three slots, per the wire format)."""
        return self._robot.controller.measure_distance(self._slot())

    def read_distance_mm(self) -> float | None:
        """Trigger a ping and return this mount's measured distance in mm,
        or None if out of range / no echo."""
        result = self.read()
        return {AxisId.X: result.x_mm, AxisId.Y: result.y_mm, AxisId.Z: result.z_mm}[self._slot()]
