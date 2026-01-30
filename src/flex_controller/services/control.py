from typing import Any, Dict, Union

import models as Models
import paths as Paths
from client import FlexHTTPClient

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class ControlService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def identify(self, seconds: int) -> Models.V1BasicResponse:
        """
        POST /identify
        Blink the gantry lights so you can pick the robot out of a crowd.

        Args:
            seconds: Time in seconds to blink the lights.
        """
        path = Paths.Endpoints.RobotControl.IDENTIFY
        params = {"seconds": seconds}
        data = await self.client.post(path, params=params)
        return Models.V1BasicResponse(**data)

    async def get_robot_positions(self) -> Models.RobotPositionsResponse:
        """
        GET /robot/positions
        Get a list of useful positions.

        WARNING: Deprecated. This data primarily applies to OT-2 robots.
        There is currently no public way to get these specific positions for Flex robots via this endpoint.
        """
        path = Paths.Endpoints.RobotControl.POSITIONS
        data = await self.client.get(path)
        return Models.RobotPositionsResponse(**data)

    async def move_robot(self, target: Union[Models.RobotMoveTarget, Dict[str, Any]]) -> Models.V1BasicResponse:
        """
        POST /robot/move
        Move the robot's gantry to a specific position.

        WARNING: Deprecated. Prefer using 'moveToCoordinates' commands 
        within a Maintenance Run for safer, collision-aware movement on Flex.

        Args:
            target: The target destination (e.g., specific mount or coordinates).
        """
        path = Paths.Endpoints.RobotControl.MOVE
        if isinstance(target, Models.RobotMoveTarget):
            payload = target.model_dump(exclude_none=True)
        else:
            payload = dict(target)
        data = await self.client.post(path, json=payload)
        return Models.V1BasicResponse(**data)

    async def home(
        self, target: Union[Models.RobotHomeTarget, Dict[str, Any]]
    ) -> Models.V1BasicResponse:
        """
        POST /robot/home
        Home the robot gantry or specific axes.

        Args:
            target: The target axes or mount to home.
        """
        path = Paths.Endpoints.RobotControl.HOME
        if isinstance(target, Models.RobotHomeTarget):
            payload = target.model_dump(exclude_none=True)
        else:
            payload = dict(target)
        data = await self.client.post(path, json=payload)
        return Models.V1BasicResponse(**data)

    async def get_lights_status(self) -> Models.RobotLightState:
        """
        GET /robot/lights
        Get the current status (on/off) of the robot's rail lights.
        """
        path = Paths.Endpoints.RobotControl.LIGHTS
        data = await self.client.get(path)
        return Models.RobotLightState(**data)

    async def set_lights(
        self, state: Union[Models.RobotLightState, Dict[str, Any]]
    ) -> Models.RobotLightState:
        """
        POST /robot/lights
        Turn the rail lights on or off.

        Args:
            state: A RobotLightState model or dict containing the 'on' boolean.
        """
        path = Paths.Endpoints.RobotControl.LIGHTS
        if isinstance(state, Models.RobotLightState):
            payload = state.model_dump(exclude_none=True)
        else:
            payload = dict(state)
        data = await self.client.post(path, json=payload)
        return Models.RobotLightState(**data)