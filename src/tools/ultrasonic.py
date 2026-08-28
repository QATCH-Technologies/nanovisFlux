"""
Ultrasonic distance-sensor tool for controller range measurements.

This module defines :class:`UltrasonicSensor`, a fixed-position
:class:`~.base.Tool` that queries the controller's ultrasonic range-measurement
interface.

Unlike motion tools such as pipettes and touch probes, an ultrasonic sensor
does not have an independently controlled vertical axis. Its physical
position relative to the robot's X/Y coordinate system is determined by the
mount on which it is installed. The sensor therefore performs measurements
only and does not directly command motion.

The controller's `M412` response contains readings for multiple sensor
slots. The slot queried by this tool is selected from the sensor's attached
:class:`~..core.MountSide`, allowing the same sensor implementation to support
different mount positions.
"""

from __future__ import annotations

from ..core import AxisId, MountSide
from ..protocol.responses import DistanceResult
from .base import Tool

#: Map each robot mount side to the controller sensor slot used for range
#: measurements. The rear mount currently corresponds to the physically
#: installed sensor on the controller's Z slot. The left and right mappings
#: reserve the X and Y slots for potential future sensors.
_MOUNT_RANGE_SLOT = {
    MountSide.LEFT: AxisId.X,
    MountSide.RIGHT: AxisId.Y,
    MountSide.REAR: AxisId.Z,
}


class UltrasonicSensor(Tool):
    """Provide fixed-position ultrasonic distance measurements.

    `UltrasonicSensor` is a non-actuating tool that triggers the controller's
    `M412` range-measurement command and exposes the resulting distance for
    the mount to which the sensor is attached.

    The sensor has no independently controlled vertical axis. Its physical
    position relative to the robot's gantry is determined by the mount
    geometry, rather than by sensor-specific positioning parameters. Mount
    offsets therefore remain part of the robot's mount configuration rather
    than this device's definition.

    The controller returns measurements for multiple sensor slots. This class
    selects the slot associated with its attached :class:`MountSide` using
    `_MOUNT_RANGE_SLOT`. The default mapping reflects the currently wired
    hardware, while the left and right mappings reserve the corresponding
    controller slots for possible future sensor installations.

    Args:
        max_range_mm: Maximum supported measurement range in millimeters.
        name: Name used to identify this sensor instance.
        brand: Sensor manufacturer or vendor name. May be empty when unknown
            or when using a custom sensor.

    Attributes:
        name: Instance-specific sensor name.
        brand: Sensor manufacturer or vendor.
        max_range_mm: Maximum supported measurement range in millimeters.
    """

    def __init__(
        self,
        max_range_mm: float = 4000.0,
        name: str = "ultrasonic",
        brand: str = "",
    ):
        """Initialize an ultrasonic distance sensor.

        The sensor starts detached from any robot mount. The measurement slot is
        determined dynamically from the mount when a reading is requested.

        Args:
            max_range_mm: Maximum supported measurement range in millimeters.
            name: Name used to identify this sensor instance.
            brand: Sensor manufacturer or vendor name.
        """
        super().__init__()
        self.name = name
        self.brand = brand
        self.max_range_mm = max_range_mm

    def _slot(self) -> AxisId:
        """Return the controller sensor slot associated with the sensor mount.

        The slot is selected from the sensor's currently attached mount. If the
        sensor is detached, the rear/Z slot is used as the default mapping.

        Returns:
            The :class:`AxisId` identifying the controller range-measurement slot
            associated with the sensor's mount.
        """
        side = self._mount.side if self._mount is not None else MountSide.REAR
        return _MOUNT_RANGE_SLOT.get(side, AxisId.Z)

    def read(self) -> DistanceResult:
        """Trigger an ultrasonic measurement and return the raw result.

        Sends a range-measurement request for the controller slot corresponding
        to this sensor's attached mount. The returned :class:`DistanceResult`
        contains the measurements reported for all supported sensor slots.

        Returns:
            The raw :class:`DistanceResult` returned by the controller.

        Raises:
            AttributeError: If the sensor is not attached to a robot with a
                configured controller.
        """
        robot = self._robot
        if robot is None:
            raise AttributeError("UltrasonicSensor is not attached to a robot")
        return robot.controller.measure_distance(self._slot())

    def read_distance_mm(self) -> float | None:
        """Measure and return the distance for this sensor's mount.

        Triggers a new ultrasonic measurement and selects the distance associated
        with the controller slot corresponding to the sensor's attached mount.

        Returns:
            The measured distance in millimeters, or `None` when the selected
            sensor reports no valid measurement, such as when the target is out
            of range or no echo is detected.

        Raises:
            AttributeError: If the sensor is not attached to a robot with a
                configured controller.
        """
        result = self.read()
        return {AxisId.X: result.x_mm, AxisId.Y: result.y_mm, AxisId.Z: result.z_mm}[self._slot()]
