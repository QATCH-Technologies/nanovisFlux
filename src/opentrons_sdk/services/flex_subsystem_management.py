"""
src.opentrons_sdk.services.flex_subsystem_management

Service interface for managing Flex subsystems.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import models as Models
import paths as Paths


class FlexSubsystemManagementService:
    def __init__(self, client):
        self.client = client

    async def get_subsystems_status(self) -> Models.SimpleMultiBodyPresentSubsystem:
        """
        GET /subsystems/status
        Retrieve the state, firmware version, and connection status
        of all Flex hardware subsystems.

        Note: This is strictly for Flex robots and will return 403 on OT-2.
        """
        path = Paths.Endpoints.FlexSubsystemManagament.SUBSYSTEMS_STATUS
        data = await self.client.get(path)
        return Models.SimpleMultiBodyPresentSubsystem(**data)

    async def get_subsystem_status(
        self, subsystem: str
    ) -> Models.SimpleBodyPresentSubsystem:
        """
        GET /subsystems/status/{subsystem}
        Retrieve details for a single hardware subsystem (e.g., 'gantry', 'gripper').

        Args:
            subsystem: The ID of the subsystem to query.
        """
        path = Paths.Endpoints.FlexSubsystemManagament.SUBSYSTEM_ID.format(
            subsystem=subsystem
        )
        data = await self.client.get(path)
        return Models.SimpleBodyPresentSubsystem(**data)

    async def get_current_subsystem_updates(
        self,
    ) -> Models.SimpleMultiBodyUpdateProgressSummary:
        """
        GET /subsystems/updates/current
        Get a list of currently running subsystem firmware updates.

        This provides a snapshot of active updates that might block robot
        movements or protocol execution.
        """
        path = Paths.Endpoints.FlexSubsystemManagament.SUBSYSTEM_UPDATES_CURRENT
        data = await self.client.get(path)
        return Models.SimpleMultiBodyUpdateProgressSummary(**data)

    async def get_current_subsystem_update(
        self, subsystem: str
    ) -> Models.SimpleBodyUpdateProgressData:
        """
        GET /subsystems/updates/current/{subsystem}
        Retrieve the ongoing update status for a specific subsystem.

        Args:
            subsystem: The ID of the subsystem (e.g., 'gantry', 'pipette_left').
        """
        path = Paths.Endpoints.FlexSubsystemManagament.SUBSYSTEM_UPDATES_CURRENT_SUBSYSTEM.format(
            subsystem=subsystem
        )
        data = await self.client.get(path)
        return Models.SimpleBodyUpdateProgressData(**data)

    async def get_all_subsystem_updates(
        self,
    ) -> Models.SimpleMultiBodyUpdateProgressData:
        """
        GET /subsystems/updates/all
        Retrieve a list of all firmware updates attempted since the last boot.

        Includes ongoing, completed, and failed updates.
        """
        path = Paths.Endpoints.FlexSubsystemManagament.SUBSYSTEM_UPDATES_ALL
        data = await self.client.get(path)
        return Models.SimpleMultiBodyUpdateProgressData(**data)

    async def get_subsystem_update_by_id(
        self, update_id: str
    ) -> Models.SimpleBodyUpdateProgressData:
        """
        GET /subsystems/updates/all/{id}
        Retrieve the full status and result of a specific subsystem update process.

        Args:
            update_id: The unique identifier for the update process
                       (previously obtained from GET /subsystems/updates/all).
        """
        path = Paths.Endpoints.FlexSubsystemManagament.SUBSYSTEM_UPDATES_ALL_ID.format(
            id=update_id
        )
        data = await self.client.get(path)
        return Models.SimpleBodyUpdateProgressData(**data)

    async def update_subsystem(
        self, subsystem: str
    ) -> Models.SimpleBodyUpdateProgressData:
        """
        POST /subsystems/updates/{subsystem}
        Begin a firmware update for a specific subsystem.

        Args:
            subsystem: The ID of the subsystem (e.g., 'gantry', 'pipette_left').

        Returns:
            Update progress data containing the session ID to track with
            the 'get_subsystem_update_by_id' method.
        """
        path = (
            Paths.Endpoints.FlexSubsystemManagament.SUBSYSTEM_UPDATES_SUBSYSTEM.format(
                subsystem=subsystem
            )
        )
        data = await self.client.post(path)
        return Models.SimpleBodyUpdateProgressData(**data)
