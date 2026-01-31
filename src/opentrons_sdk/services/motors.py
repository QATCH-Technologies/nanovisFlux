import os
from typing import Any, Dict, Union

import aiohttp
import models as Models
import paths as Paths
from client import FlexHTTPClient

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class MotorService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_engaged_motors(self) -> Models.EngagedMotors:
        """
        GET /motors/engaged
        Query which motors are currently engaged and holding position.
        """
        path = Paths.Endpoints.RobotControl.MOTORS_ENGAGED
        data = await self.client.get(path)
        return Models.EngagedMotors(**data)

    async def disengage_motors(
        self, axes: Union[Models.Axes, Dict[str, Any]]
    ) -> Models.V1BasicResponse:
        """
        POST /motors/disengage
        Disengage a motor or set of motors.

        Args:
            axes: An Axes model or dict specifying which axes to disengage
                  (e.g., {"axes": ["x", "y"]}).
        """
        path = Paths.Endpoints.RobotControl.MOTORS_DISENGAGE
        if isinstance(axes, Models.Axes):
            payload = axes.model_dump(exclude_none=True)
        else:
            payload = dict(axes)
        data = await self.client.post(path, json=payload)
        return Models.V1BasicResponse(**data)