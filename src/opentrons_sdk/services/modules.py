"""
src.opentrons_sdk.services.modules

Service interface for Opentrons module managment.

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


class ModuleService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def execute_module_command(
        self, serial: str, command: Union[Models.SerialCommand, Dict[str, Any]]
    ) -> Models.SerialCommandResponse:
        """
        POST /modules/{serial}
        Execute a command on a specific module.

        WARNING: Deprecated. Removed with Opentrons-Version: 3.
        Use execute_stateless_command() via RunService instead.

        Args:
            serial: Serial number of the target module.
            command: A SerialCommand model or dict containing the command name and params.
        """
        path = Paths.Endpoints.Components.MODULE_COMMAND.format(serial=serial)
        if isinstance(command, Models.SerialCommand):
            payload = command.model_dump(exclude_none=True)
        else:
            payload = dict(command)
        data = await self.client.post(path, json=payload)
        return Models.SerialCommandResponse(**data)

    async def update_module_firmware(self, serial: str) -> Models.V1BasicResponse:
        """
        POST /modules/{serial}/update
        Command the robot to flash its bundled firmware file for this module type
        to the specific module identified by serial number.

        Args:
            serial: Serial number of the module to update.
        """
        path = Paths.Endpoints.Components.MODULE_UPDATE.format(serial=serial)
        data = await self.client.post(path)
        return Models.V1BasicResponse(**data)
