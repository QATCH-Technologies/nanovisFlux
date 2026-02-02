"""
src.opentrons_sdk.services.simple_commands

Service interface for simple command actions.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

from typing import Any, Dict, Optional

import models as Models
import paths as Paths
from client import FlexHTTPClient


class SimpleCommandsService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def enqueue_simple_command(
        self,
        command: Dict[str, Any],
        wait_until_complete: bool = False,
        timeout: Optional[int] = None,
    ) -> (
        Models.SimpleMultiBodyAnnotatedUnionHomeSetRailLightsSetStatusBarEngageDisengageSetTargetTemperatureDeactivateTemperatureSetTargetBlockTemperatureSetTargetLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidSetTargetTemperatureSetAndWaitForShakeSpeedDeactivateHeaterDeactivateShakerOpenLabwareLatchCloseLabwareLatchUnsafeFlexStackerPrepareShuttleCreateUnsafeFlexStackerCloseLatchCreateUnsafeFlexStackerOpenLatchCreateIdentifyModuleFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType
    ):
        """
        POST /commands
        Execute a single stateless command on the robot.

        Args:
            command: The command payload (e.g., {"commandType": "home", "params": {}}).
            wait_until_complete: If True, blocks until finished or timed out.
            timeout: Max time in ms to wait if wait_until_complete is True.
        """
        path = Paths.Endpoints.SimpleCommands.COMMAND_QUEUE
        params = {
            "waitUntilComplete": str(wait_until_complete).lower(),
            "timeout": timeout,
        }
        payload = {"data": command}
        data = await self.client.post(
            path,
            json=payload,
            params={k: v for k, v in params.items() if v is not None},
        )
        return Models.SimpleMultiBodyAnnotatedUnionHomeSetRailLightsSetStatusBarEngageDisengageSetTargetTemperatureDeactivateTemperatureSetTargetBlockTemperatureSetTargetLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidSetTargetTemperatureSetAndWaitForShakeSpeedDeactivateHeaterDeactivateShakerOpenLabwareLatchCloseLabwareLatchUnsafeFlexStackerPrepareShuttleCreateUnsafeFlexStackerCloseLatchCreateUnsafeFlexStackerOpenLatchCreateIdentifyModuleFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType(
            **data
        )

    async def get_simple_commands(
        self, cursor: Optional[int] = None, page_length: int = 20
    ) -> (
        Models.SimpleMultiBodyAnnotatedUnionHomeSetRailLightsSetStatusBarEngageDisengageSetTargetTemperatureDeactivateTemperatureSetTargetBlockTemperatureSetTargetLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidSetTargetTemperatureSetAndWaitForShakeSpeedDeactivateHeaterDeactivateShakerOpenLabwareLatchCloseLabwareLatchUnsafeFlexStackerPrepareShuttleCreateUnsafeFlexStackerCloseLatchCreateUnsafeFlexStackerOpenLatchCreateIdentifyModuleFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType
    ):
        """
        GET /commands
        Retrieve a list of commands executed via the /commands endpoint since boot.
        """
        path = Paths.Endpoints.SimpleCommands.COMMAND_QUEUE
        params = {"cursor": cursor, "pageLength": page_length}

        data = await self.client.get(
            path, params={k: v for k, v in params.items() if v is not None}
        )
        return Models.SimpleMultiBodyAnnotatedUnionHomeSetRailLightsSetStatusBarEngageDisengageSetTargetTemperatureDeactivateTemperatureSetTargetBlockTemperatureSetTargetLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidSetTargetTemperatureSetAndWaitForShakeSpeedDeactivateHeaterDeactivateShakerOpenLabwareLatchCloseLabwareLatchUnsafeFlexStackerPrepareShuttleCreateUnsafeFlexStackerCloseLatchCreateUnsafeFlexStackerOpenLatchCreateIdentifyModuleFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType(
            **data
        )

    async def get_simple_command(
        self, command_id: str
    ) -> (
        Models.SimpleMultiBodyAnnotatedUnionHomeSetRailLightsSetStatusBarEngageDisengageSetTargetTemperatureDeactivateTemperatureSetTargetBlockTemperatureSetTargetLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidSetTargetTemperatureSetAndWaitForShakeSpeedDeactivateHeaterDeactivateShakerOpenLabwareLatchCloseLabwareLatchUnsafeFlexStackerPrepareShuttleCreateUnsafeFlexStackerCloseLatchCreateUnsafeFlexStackerOpenLatchCreateIdentifyModuleFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType
    ):
        """
        GET /commands/{commandId}
        Retrieve full details of a specific stateless command by ID.
        Only applicable for commands previously issued via POST /commands.

        Args:
            command_id: The unique identifier returned when the command was enqueued.
        """
        path = Paths.Endpoints.SimpleCommands.COMMAND_ID.format(commandId=command_id)
        data = await self.client.get(path)
        return Models.SimpleMultiBodyAnnotatedUnionHomeSetRailLightsSetStatusBarEngageDisengageSetTargetTemperatureDeactivateTemperatureSetTargetBlockTemperatureSetTargetLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidSetTargetTemperatureSetAndWaitForShakeSpeedDeactivateHeaterDeactivateShakerOpenLabwareLatchCloseLabwareLatchUnsafeFlexStackerPrepareShuttleCreateUnsafeFlexStackerCloseLatchCreateUnsafeFlexStackerOpenLatchCreateIdentifyModuleFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType(
            **data
        )
