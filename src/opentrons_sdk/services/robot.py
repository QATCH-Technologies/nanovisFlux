"""
src.opentrons_sdk.services.robot

Service interface for remote robot actions.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import models as Models
import paths as Paths


class RobotService:
    def __init__(self, client):
        self.client = client

    async def get_estop_status(self) -> Models.SimpleBodyEstopStatusModel:
        """
        GET /robot/control/estopStatus
        Retrieve the current status of the E-Stop system and a list of
        physically connected E-Stop devices.

        Note: This is strictly for Flex robots and will return 403 on OT-2.
        """
        path = Paths.Endpoints.Robot.ESTOP_STATUS
        data = await self.client.get(path)
        return Models.SimpleBodyEstopStatusModel(**data)

    async def acknowledge_estop_disengage(self) -> Models.SimpleBodyEstopStatusModel:
        """
        PUT /robot/control/acknowledgeEstopDisengage
        Clear the logical E-Stop state. Call this after the physical E-Stop
        button has been released to restore motor power and robot control.
        """
        path = Paths.Endpoints.Robot.ESTOP_ACKNOWLEDGE
        data = await self.client.put(path)
        return Models.SimpleBodyEstopStatusModel(**data)

    async def get_door_status(self) -> Models.SimpleBodyDoorStatusModel:
        """
        GET /robot/door/status
        Retrieve the current state of the robot door (open or closed).

        Useful for verifying the robot is sealed before starting sensitive
        protein viscosity experiments.
        """
        path = Paths.Endpoints.Robot.DOOR_STATUS
        data = await self.client.get(path)
        return Models.SimpleBodyDoorStatusModel(**data)
