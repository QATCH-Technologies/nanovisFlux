import datetime

import models as Models
import paths as Paths

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class SystemControlService:
    def __init__(self, client):
        self.client = client

    async def get_system_time(
        self,
    ) -> Models.DeprecatedResponseModelSystemTimeResponseAttributes:
        """
        GET /system/time
        Retrieve the robot's current UTC date and time, local timezone,
        and NTP synchronization status.
        """
        path = Paths.Endpoints.SystemControl.SYSTEM_TIME
        data = await self.client.get(path)
        return Models.DeprecatedResponseModelSystemTimeResponseAttributes(**data)

    async def set_system_time(
        self, system_time: datetime.datetime
    ) -> Models.DeprecatedResponseModelSystemTimeResponseAttributes:
        """
        PUT /system/time
        Manually update the robot's system time. Useful if the robot is
        on a local network without NTP access.

        Args:
            system_time: A Python datetime object to set on the robot.
        """
        path = Paths.Endpoints.SystemControl.SYSTEM_TIME
        payload = {"data": {"attributes": {"systemTime": system_time.isoformat()}}}

        data = await self.client.put(path, json=payload)
        return Models.DeprecatedResponseModelSystemTimeResponseAttributes(**data)
