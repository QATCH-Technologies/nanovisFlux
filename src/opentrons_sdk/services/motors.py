"""
src.opentrons_sdk.services.motors

Service interface for motor controls.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

from typing import Any, Dict, Union

import models as Models
import paths as Paths
from client import FlexHTTPClient


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
