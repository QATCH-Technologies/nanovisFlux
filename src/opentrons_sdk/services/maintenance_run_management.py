"""
src.opentrons_sdk.services.maintenance_run_management

Service interface for maintenance run management.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

from typing import Any, Dict, List, Optional, Union

import models as Models
import paths as Paths
from client import FlexHTTPClient
from pydantic import BaseModel


class MaintenanceRunManagementService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def create_maintenance_run(
        self,
        run_data: Optional[Union[Models.MaintenanceRunCreate, Dict[str, Any]]] = None,
    ) -> Models.SimpleBodyMaintenanceRun:
        """
        POST /maintenance_runs
        Create a new maintenance run for manual robot interaction.

        If a maintenance run already exists, it will be cleared.
        Note: This will fail if a standard protocol run is currently active.

        Args:
            run_data: Optional model or dict containing labwareOffsets or metadata.
        """
        path = Paths.Endpoints.MaintenanceRuns.CREATE
        payload = None
        if run_data is not None:
            if isinstance(run_data, BaseModel):
                payload_data = run_data.model_dump(exclude_none=True)
            else:
                payload_data = dict(run_data)
            payload = {"data": payload_data}
        data = await self.client.post(path, json=payload)
        return Models.SimpleBodyMaintenanceRun(**data)

    async def get_current_maintenance_run(
        self,
    ) -> Models.BodyMaintenanceRunAllRunsLinks:
        """
        GET /maintenance_runs/current_run
        Retrieve the currently active maintenance run, if one exists.
        """
        path = Paths.Endpoints.MaintenanceRuns.CURRENT
        data = await self.client.get(path)
        return Models.BodyMaintenanceRunAllRunsLinks(**data)

    async def get_maintenance_run(self, run_id: str) -> Models.SimpleBodyMaintenanceRun:
        """
        GET /maintenance_runs/{runId}
        Retrieve a specific maintenance run by its ID.
        """
        path = Paths.Endpoints.MaintenanceRuns.GET_ID.format(runId=run_id)
        data = await self.client.get(path)
        return Models.SimpleBodyMaintenanceRun(**data)

    async def delete_maintenance_run(self, run_id: str) -> Models.SimpleEmptyBody:
        """
        DELETE /maintenance_runs/{runId}
        Delete a specific maintenance run. This is required to clear the
        maintenance state before starting a protocol run.
        """
        path = Paths.Endpoints.MaintenanceRuns.DELETE.format(runId=run_id)
        data = await self.client.delete(path)
        return Models.SimpleEmptyBody(**data)

    async def get_maintenance_run_commands(
        self, run_id: str, cursor: Optional[int] = None, page_length: int = 20
    ) -> Models.MultiBodyRunCommandSummaryCommandCollectionLinks:
        """
        GET /maintenance_runs/{runId}/commands
        Get a list of all commands enqueued in the maintenance run.
        """
        path = Paths.Endpoints.MaintenanceRuns.COMMANDS.format(runId=run_id)
        params = {"cursor": cursor, "pageLength": page_length}
        data = await self.client.get(
            path, params={k: v for k, v in params.items() if v is not None}
        )
        return Models.MultiBodyRunCommandSummaryCommandCollectionLinks(**data)

    async def enqueue_maintenance_command(
        self,
        run_id: str,
        command: Dict[str, Any],
        wait_until_complete: bool = False,
        timeout: Optional[int] = None,
    ) -> (
        Models.SimpleBodyAnnotatedUnionAirGapInPlaceAspirateAspirateInPlaceAspirateWhileTrackingCommentCustomDispenseDispenseInPlaceDispenseWhileTrackingBlowOutBlowOutInPlaceConfigureForVolumeConfigureNozzleLayoutDropTipDropTipInPlaceHomeRetractAxisLoadLabwareReloadLabwareLoadLiquidLoadLiquidClassLoadModuleIdentifyModuleLoadPipetteLoadLidStackLoadLidMoveLabwareMoveRelativeMoveToCoordinatesMoveToWellMoveToAddressableAreaMoveToAddressableAreaForDropTipPrepareToAspirateWaitForResumeWaitForDurationPickUpTipSavePositionSetRailLightsTouchTipSetStatusBarVerifyTipPresenceGetTipPresenceGetNextTipLiquidProbeTryLiquidProbeSealPipetteToTipPressureDispenseUnsealPipetteFromTipWaitForTemperatureSetTargetTemperatureDeactivateHeaterSetAndWaitForShakeSpeedDeactivateShakerOpenLabwareLatchCloseLabwareLatchDisengageEngageSetTargetTemperatureWaitForTemperatureDeactivateTemperatureSetTargetBlockTemperatureWaitForBlockTemperatureSetTargetLidTemperatureWaitForLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidRunProfileRunExtendedProfileCloseLidOpenLidInitializeReadAbsorbanceRetrieveStoreSetStoredLabwareFillEmptyCalibrateGripperCalibratePipetteCalibrateModuleMoveToMaintenancePositionUnsafeBlowOutInPlaceUnsafeDropTipInPlaceUpdatePositionEstimatorsUnsafeEngageAxesUnsafeUngripLabwareUnsafePlaceLabwareUnsafeFlexStackerManualRetrieveUnsafeFlexStackerCloseLatchUnsafeFlexStackerOpenLatchUnsafeFlexStackerPrepareShuttleMoveToMoveAxesRelativeMoveAxesToOpenGripperJawCloseGripperJawFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType
    ):
        """
        POST /maintenance_runs/{runId}/commands
        Enqueue a single command to the maintenance run for immediate execution.

        Args:
            run_id: Unique identifier of the maintenance run.
            command: The command payload (e.g., {"commandType": "home", "params": {}}).
            wait_until_complete: If True, blocks until command finishes or timeouts.
            timeout: Max time in ms to wait if wait_until_complete is True.
        """
        path = Paths.Endpoints.MaintenanceRuns.COMMANDS.format(runId=run_id)
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
        return Models.SimpleBodyAnnotatedUnionAirGapInPlaceAspirateAspirateInPlaceAspirateWhileTrackingCommentCustomDispenseDispenseInPlaceDispenseWhileTrackingBlowOutBlowOutInPlaceConfigureForVolumeConfigureNozzleLayoutDropTipDropTipInPlaceHomeRetractAxisLoadLabwareReloadLabwareLoadLiquidLoadLiquidClassLoadModuleIdentifyModuleLoadPipetteLoadLidStackLoadLidMoveLabwareMoveRelativeMoveToCoordinatesMoveToWellMoveToAddressableAreaMoveToAddressableAreaForDropTipPrepareToAspirateWaitForResumeWaitForDurationPickUpTipSavePositionSetRailLightsTouchTipSetStatusBarVerifyTipPresenceGetTipPresenceGetNextTipLiquidProbeTryLiquidProbeSealPipetteToTipPressureDispenseUnsealPipetteFromTipWaitForTemperatureSetTargetTemperatureDeactivateHeaterSetAndWaitForShakeSpeedDeactivateShakerOpenLabwareLatchCloseLabwareLatchDisengageEngageSetTargetTemperatureWaitForTemperatureDeactivateTemperatureSetTargetBlockTemperatureWaitForBlockTemperatureSetTargetLidTemperatureWaitForLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidRunProfileRunExtendedProfileCloseLidOpenLidInitializeReadAbsorbanceRetrieveStoreSetStoredLabwareFillEmptyCalibrateGripperCalibratePipetteCalibrateModuleMoveToMaintenancePositionUnsafeBlowOutInPlaceUnsafeDropTipInPlaceUpdatePositionEstimatorsUnsafeEngageAxesUnsafeUngripLabwareUnsafePlaceLabwareUnsafeFlexStackerManualRetrieveUnsafeFlexStackerCloseLatchUnsafeFlexStackerOpenLatchUnsafeFlexStackerPrepareShuttleMoveToMoveAxesRelativeMoveAxesToOpenGripperJawCloseGripperJawFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType(
            **data
        )

    async def get_maintenance_run_command(
        self, run_id: str, command_id: str
    ) -> (
        Models.SimpleBodyAnnotatedUnionAirGapInPlaceAspirateAspirateInPlaceAspirateWhileTrackingCommentCustomDispenseDispenseInPlaceDispenseWhileTrackingBlowOutBlowOutInPlaceConfigureForVolumeConfigureNozzleLayoutDropTipDropTipInPlaceHomeRetractAxisLoadLabwareReloadLabwareLoadLiquidLoadLiquidClassLoadModuleIdentifyModuleLoadPipetteLoadLidStackLoadLidMoveLabwareMoveRelativeMoveToCoordinatesMoveToWellMoveToAddressableAreaMoveToAddressableAreaForDropTipPrepareToAspirateWaitForResumeWaitForDurationPickUpTipSavePositionSetRailLightsTouchTipSetStatusBarVerifyTipPresenceGetTipPresenceGetNextTipLiquidProbeTryLiquidProbeSealPipetteToTipPressureDispenseUnsealPipetteFromTipWaitForTemperatureSetTargetTemperatureDeactivateHeaterSetAndWaitForShakeSpeedDeactivateShakerOpenLabwareLatchCloseLabwareLatchDisengageEngageSetTargetTemperatureWaitForTemperatureDeactivateTemperatureSetTargetBlockTemperatureWaitForBlockTemperatureSetTargetLidTemperatureWaitForLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidRunProfileRunExtendedProfileCloseLidOpenLidInitializeReadAbsorbanceRetrieveStoreSetStoredLabwareFillEmptyCalibrateGripperCalibratePipetteCalibrateModuleMoveToMaintenancePositionUnsafeBlowOutInPlaceUnsafeDropTipInPlaceUpdatePositionEstimatorsUnsafeEngageAxesUnsafeUngripLabwareUnsafePlaceLabwareUnsafeFlexStackerManualRetrieveUnsafeFlexStackerCloseLatchUnsafeFlexStackerOpenLatchUnsafeFlexStackerPrepareShuttleMoveToMoveAxesRelativeMoveAxesToOpenGripperJawCloseGripperJawFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType
    ):
        """
        GET /maintenance_runs/{runId}/commands/{commandId}
        Retrieve full details for a specific command in a maintenance run,
        including associated payload, result, and execution timing.

        Args:
            run_id: Unique identifier of the maintenance run.
            command_id: Unique identifier of the specific command.
        """
        path = Paths.Endpoints.MaintenanceRuns.COMMAND_ID.format(
            runId=run_id, commandId=command_id
        )
        data = await self.client.get(path)
        return Models.SimpleBodyAnnotatedUnionAirGapInPlaceAspirateAspirateInPlaceAspirateWhileTrackingCommentCustomDispenseDispenseInPlaceDispenseWhileTrackingBlowOutBlowOutInPlaceConfigureForVolumeConfigureNozzleLayoutDropTipDropTipInPlaceHomeRetractAxisLoadLabwareReloadLabwareLoadLiquidLoadLiquidClassLoadModuleIdentifyModuleLoadPipetteLoadLidStackLoadLidMoveLabwareMoveRelativeMoveToCoordinatesMoveToWellMoveToAddressableAreaMoveToAddressableAreaForDropTipPrepareToAspirateWaitForResumeWaitForDurationPickUpTipSavePositionSetRailLightsTouchTipSetStatusBarVerifyTipPresenceGetTipPresenceGetNextTipLiquidProbeTryLiquidProbeSealPipetteToTipPressureDispenseUnsealPipetteFromTipWaitForTemperatureSetTargetTemperatureDeactivateHeaterSetAndWaitForShakeSpeedDeactivateShakerOpenLabwareLatchCloseLabwareLatchDisengageEngageSetTargetTemperatureWaitForTemperatureDeactivateTemperatureSetTargetBlockTemperatureWaitForBlockTemperatureSetTargetLidTemperatureWaitForLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidRunProfileRunExtendedProfileCloseLidOpenLidInitializeReadAbsorbanceRetrieveStoreSetStoredLabwareFillEmptyCalibrateGripperCalibratePipetteCalibrateModuleMoveToMaintenancePositionUnsafeBlowOutInPlaceUnsafeDropTipInPlaceUpdatePositionEstimatorsUnsafeEngageAxesUnsafeUngripLabwareUnsafePlaceLabwareUnsafeFlexStackerManualRetrieveUnsafeFlexStackerCloseLatchUnsafeFlexStackerOpenLatchUnsafeFlexStackerPrepareShuttleMoveToMoveAxesRelativeMoveAxesToOpenGripperJawCloseGripperJawFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType(
            **data
        )

    async def add_maintenance_run_labware_offsets(
        self,
        run_id: str,
        offsets: Union[
            Models.LabwareOffsetCreate, List[Models.LabwareOffsetCreate], Dict[str, Any]
        ],
    ) -> Models.SimpleBodyUnionLabwareOffsetListLabwareOffset:
        """
        POST /maintenance_runs/{runId}/labware_offsets
        Add labware offsets to an existing maintenance run.

        Args:
            run_id: Unique identifier of the maintenance run.
            offsets: A single offset, a list of offsets, or a raw dictionary.
        """
        path = Paths.Endpoints.MaintenanceRuns.LABWARE_OFFSETS.format(runId=run_id)

        if isinstance(offsets, list):
            payload_data = [
                o.model_dump(exclude_none=True) if isinstance(o, BaseModel) else o
                for o in offsets
            ]
        elif isinstance(offsets, BaseModel):
            payload_data = offsets.model_dump(exclude_none=True)
        else:
            payload_data = offsets

        payload = {"data": payload_data}
        data = await self.client.post(path, json=payload)
        return Models.SimpleBodyUnionLabwareOffsetListLabwareOffset(**data)

    async def add_maintenance_run_labware_definition(
        self,
        run_id: str,
        definition: Union[
            Dict[str, Any],
            Models.RequestModelAnnotatedUnionLabwareDefinition2LabwareDefinition3Discriminator,
        ],
    ) -> Models.SimpleBodyMaintenanceRun:
        """
        POST /maintenance_runs/{runId}/labware_definitions
        Add a labware definition (v2 or v3) to a specific maintenance run.

        Args:
            run_id: Unique identifier of the maintenance run.
            definition: The full JSON labware definition.
        """
        path = Paths.Endpoints.MaintenanceRuns.LABWARE_DEFS.format(runId=run_id)
        payload_data = (
            definition.model_dump(exclude_none=True)
            if isinstance(definition, BaseModel)
            else definition
        )
        payload = {"data": payload_data}
        data = await self.client.post(path, json=payload)
        return Models.SimpleBodyMaintenanceRun(**data)
