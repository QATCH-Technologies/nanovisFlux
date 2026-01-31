from typing import Any, Dict, List, Optional, Union

import models as Models
import paths as Paths
from client import FlexHTTPClient

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class RunManagementService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_all_runs(
        self, page_length: Optional[int] = None
    ) -> Models.MultiBodyUnionRunBadRunAllRunsLinks:
        """
        GET /runs
        Get a list of all active and inactive runs, in order from oldest to newest.

        Args:
            page_length: The maximum number of runs to return. If omitted, all runs are returned.
        """
        path = Paths.Endpoints.Runs.GET_ALL
        params = {"pageLength": page_length} if page_length is not None else {}
        data = await self.client.get(path, params=params)
        return Models.MultiBodyUnionRunBadRunAllRunsLinks(**data)

    async def create_run(
        self, run_data: Optional[Union[Models.RunCreate, Dict[str, Any]]] = None
    ) -> Models.SimpleBodyRun:
        """
        POST /runs
        Create a new run to track robot interaction.

        When too many runs already exist, old ones are automatically deleted
        to make room for the new one.

        Args:
            run_data: Optional RunCreate model or dict containing protocolId,
                      labwareOffsets, or metadata.
        """
        path = Paths.Endpoints.Runs.CREATE

        payload = None
        if run_data is not None:
            # Ensure the data is converted to a dictionary for the JSON body
            if hasattr(run_data, "model_dump"):
                payload_data = run_data.model_dump(exclude_none=True)
            else:
                payload_data = dict(run_data)
            payload = {"data": payload_data}
        data = await self.client.post(path, json=payload)
        return Models.SimpleBodyRun(**data)

    async def get_run(self, run_id: str) -> Models.SimpleBodyUnionRunBadRun:
        """
        GET /runs/{runId}
        Get a specific run by its unique identifier.
        """
        path = Paths.Endpoints.Runs.GET_ID.format(runId=run_id)
        data = await self.client.get(path)
        return Models.SimpleBodyUnionRunBadRun(**data)

    async def update_run(
        self, run_id: str, update_data: Union[Models.RunUpdate, Dict[str, Any]]
    ) -> Models.SimpleBodyRun:
        """
        PATCH /runs/{runId}
        Update a specific run (e.g., setting it as the 'current' run).
        """
        path = Paths.Endpoints.Runs.UPDATE.format(runId=run_id)
        if hasattr(update_data, "model_dump"):
            payload_data = update_data.model_dump(exclude_none=True)
        else:
            payload_data = dict(update_data)
        payload = {"data": payload_data}
        data = await self.client.patch(path, json=payload)
        return Models.SimpleBodyRun(**data)

    async def delete_run(self, run_id: str) -> Models.SimpleEmptyBody:
        """
        DELETE /runs/{runId}
        Delete a specific run. If the run is currently active, it must be
        stopped before it can be deleted.
        """
        path = Paths.Endpoints.Runs.DELETE.format(runId=run_id)
        data = await self.client.delete(path)
        return Models.SimpleEmptyBody(**data)

    async def get_run_command_errors(
        self, run_id: str, page_length: int = 20, cursor: Optional[int] = None
    ) -> Models.SimpleMultiBodyErrorOccurrence:
        """
        GET /runs/{runId}/commandErrors
        Get a list of all command errors that occurred during the run.
        Errors are returned in order from oldest to newest.

        Args:
            run_id: Unique identifier of the run.
            page_length: Max number of errors to return (default: 20).
            cursor: Starting index for the list. If None, defaults to the last error added.
        """
        path = Paths.Endpoints.Runs.COMMAND_ERRORS.format(runId=run_id)
        params = {"pageLength": page_length, "cursor": cursor}
        data = await self.client.get(
            path, params={k: v for k, v in params.items() if v is not None}
        )
        return Models.SimpleMultiBodyErrorOccurrence(**data)

    async def get_run_current_state(
        self, run_id: str
    ) -> Models.BodyRunCurrentStateCurrentStateLinks:
        """
        GET /runs/{runId}/currentState
        Get the current state snapshot associated with a run.

        Note: This endpoint is experimental and only returns data if the
        run is the 'current' run on the robot.

        Args:
            run_id: Unique identifier of the run.
        """
        path = Paths.Endpoints.Runs.CURRENT_STATE.format(runId=run_id)
        data = await self.client.get(path)
        return Models.BodyRunCurrentStateCurrentStateLinks(**data)

    async def get_run_commands(
        self,
        run_id: str,
        cursor: Optional[int] = None,
        page_length: int = 20,
        include_fixit: bool = True,
    ) -> Models.MultiBodyRunCommandSummaryCommandCollectionLinks:
        """
        GET /runs/{runId}/commands
        Get a list of all commands in the run and their statuses.
        """
        path = Paths.Endpoints.Runs.COMMANDS_GET.format(runId=run_id)
        params = {
            "cursor": cursor,
            "pageLength": page_length,
            "includeFixitCommands": str(include_fixit).lower(),
        }
        data = await self.client.get(
            path, params={k: v for k, v in params.items() if v is not None}
        )
        return Models.MultiBodyRunCommandSummaryCommandCollectionLinks(**data)

    async def enqueue_command(
        self,
        run_id: str,
        command: Dict[str, Any],
        wait_until_complete: bool = False,
        timeout: Optional[int] = None,
        failed_command_id: Optional[str] = None,
    ) -> Models.MultiBodyRunCommandSummaryCommandCollectionLinks:
        """
        POST /runs/{runId}/commands
        Add a single command to the run. Useful for setup, stateless control,
        or error recovery (fixit commands).

        Args:
            run_id: Unique identifier of the run.
            command: The command payload (type, params, and source).
            wait_until_complete: If True, blocks until command finishes or timeouts.
            timeout: Max time in ms to wait if wait_until_complete is True.
            failed_command_id: Reference for FIXIT commands.
        """
        path = Paths.Endpoints.Runs.COMMANDS_GET.format(runId=run_id)

        params = {
            "waitUntilComplete": str(wait_until_complete).lower(),
            "timeout": timeout,
            "failedCommandId": failed_command_id,
        }

        payload = {"data": command}
        data = await self.client.post(
            path,
            json=payload,
            params={k: v for k, v in params.items() if v is not None},
        )
        return Models.MultiBodyRunCommandSummaryCommandCollectionLinks(**data)

    async def get_run_commands_preserialized(
        self, run_id: str, include_fixit: bool = True
    ) -> Models.SimpleMultiBodyStr:
        """
        GET /runs/{runId}/commandsAsPreSerializedList
        Get all commands of a completed run as a list of pre-serialized commands.

        WARNING: Experimental. This is only available after a run has completed
        and data is committed to the database.

        Args:
            run_id: Unique identifier of the run.
            include_fixit: If True, returns all commands including error-recovery ones.
        """
        path = Paths.Endpoints.Runs.COMMANDS_PRESERIALIZED.format(runId=run_id)
        params = {"includeFixitCommands": str(include_fixit).lower()}
        data = await self.client.get(path, params=params)
        return Models.SimpleMultiBodyStr(**data)

    async def get_run_command(
        self, run_id: str, command_id: str
    ) -> (
        Models.SimpleBodyAnnotatedUnionHomeSetRailLightsSetStatusBarEngageDisengageSetTargetTemperatureDeactivateTemperatureSetTargetBlockTemperatureSetTargetLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidSetTargetTemperatureSetAndWaitForShakeSpeedDeactivateHeaterDeactivateShakerOpenLabwareLatchCloseLabwareLatchUnsafeFlexStackerPrepareShuttleCreateUnsafeFlexStackerCloseLatchCreateUnsafeFlexStackerOpenLatchCreateIdentifyModuleFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType
    ):
        """
        GET /runs/{runId}/commands/{commandId}
        Get full details about a specific command in a run, including its
        payload, result, and execution timing information.

        Args:
            run_id: Unique identifier of the run.
            command_id: Unique identifier of the command to retrieve.
        """
        path = Paths.Endpoints.Runs.COMMANDS_GET_ID.format(
            runId=run_id, commandId=command_id
        )
        data = await self.client.get(path)
        return Models.SimpleBodyAnnotatedUnionHomeSetRailLightsSetStatusBarEngageDisengageSetTargetTemperatureDeactivateTemperatureSetTargetBlockTemperatureSetTargetLidTemperatureDeactivateBlockDeactivateLidOpenLidCloseLidSetTargetTemperatureSetAndWaitForShakeSpeedDeactivateHeaterDeactivateShakerOpenLabwareLatchCloseLabwareLatchUnsafeFlexStackerPrepareShuttleCreateUnsafeFlexStackerCloseLatchCreateUnsafeFlexStackerOpenLatchCreateIdentifyModuleFieldInfoAnnotationNoneTypeRequiredTrueDiscriminatorCommandType(
            **data
        )

    async def create_run_action(
        self, run_id: str, action: Union[Models.RunActionCreate, Dict[str, Any]]
    ) -> Models.SimpleBodyRunAction:
        """
        POST /runs/{runId}/actions
        Issue a control action (play, pause, stop, resume) to the run.

        Args:
            run_id: Unique identifier of the run.
            action: A RunActionCreate model or dict specifying the action type.
                    Example: {"actionType": "play"}
        """
        path = Paths.Endpoints.Runs.ACTIONS.format(runId=run_id)
        if hasattr(action, "model_dump"):
            payload_data = action.model_dump(exclude_none=True)
        else:
            payload_data = dict(action)
        payload = {"data": payload_data}
        data = await self.client.post(path, json=payload)
        return Models.SimpleBodyRunAction(**data)

    async def add_run_labware_offsets(
        self,
        run_id: str,
        offsets: Union[
            Models.LabwareOffsetCreate, List[Models.LabwareOffsetCreate], Dict[str, Any]
        ],
    ) -> Models.SimpleBodyUnionLabwareOffsetListLabwareOffset:
        """
        POST /runs/{runId}/labware_offsets
        Add labware offsets to an existing run.

        Args:
            run_id: Unique identifier of the run.
            offsets: A single offset create model, a list of models, or a raw dictionary.
        """
        path = Paths.Endpoints.Runs.LABWARE_OFFSETS.format(runId=run_id)
        if isinstance(offsets, list):
            payload_data = [
                o.model_dump(exclude_none=True) if hasattr(o, "model_dump") else o
                for o in offsets
            ]
        elif hasattr(offsets, "model_dump"):
            payload_data = offsets.model_dump(exclude_none=True)
        else:
            payload_data = offsets
        payload = {"data": payload_data}
        data = await self.client.post(path, json=payload)
        return Models.SimpleBodyUnionLabwareOffsetListLabwareOffset(**data)

    async def add_run_labware_definition(
        self,
        run_id: str,
        definition: Union[
            Dict[str, Any],
            Models.RequestModelAnnotatedUnionLabwareDefinition2LabwareDefinition3Discriminator,
        ],
    ) -> Models.SimpleBodyLabwareDefinitionSummary:
        """
        POST /runs/{runId}/labware_definitions
        Add a labware definition (v2 or v3) to a specific run.

        Args:
            run_id: Unique identifier of the run.
            definition: The full JSON labware definition.
        """
        path = Paths.Endpoints.Runs.LABWARE_DEFS.format(runId=run_id)
        payload_data = (
            definition.model_dump(exclude_none=True)
            if hasattr(definition, "model_dump")
            else definition
        )
        payload = {"data": payload_data}
        data = await self.client.post(path, json=payload)
        return Models.SimpleBodyLabwareDefinitionSummary(**data)

    async def get_run_loaded_labware_definitions(
        self, run_id: str
    ) -> (
        Models.SimpleBodyListAnnotatedUnionLabwareDefinition2LabwareDefinition3Discriminator
    ):
        """
        GET /runs/{runId}/loaded_labware_definitions
        Get the definitions of all labware that the run has loaded so far.
        Definitions are deduplicated.
        """
        path = Paths.Endpoints.Runs.LOADED_LABWARE.format(runId=run_id)
        data = await self.client.get(path)
        return Models.SimpleBodyListAnnotatedUnionLabwareDefinition2LabwareDefinition3Discriminator(
            **data
        )

    async def get_run_error_recovery_policy(
        self, run_id: str
    ) -> Models.SimpleBodyErrorRecoveryPolicy:
        """
        GET /runs/{runId}/errorRecoveryPolicy
        Retrieve the current error recovery rules set for the specific run.
        """
        path = Paths.Endpoints.Runs.ERROR_RECOVERY_POLICY.format(runId=run_id)
        data = await self.client.get(path)
        return Models.SimpleBodyErrorRecoveryPolicy(**data)

    async def set_run_error_recovery_policy(
        self, run_id: str, policy: Union[Dict[str, Any], Models.ErrorRecoveryPolicy]
    ) -> Models.SimpleEmptyBody:
        """
        PUT /runs/{runId}/errorRecoveryPolicy
        Update the rules for handling command failures (e.g., automated retries).

        Note: For this to take effect, Error Recovery must be enabled globally
        via PATCH /errorRecovery/settings.
        """
        path = Paths.Endpoints.Runs.ERROR_RECOVERY_POLICY.format(runId=run_id)
        payload_data = (
            policy.model_dump(exclude_none=True)
            if hasattr(policy, "model_dump")
            else policy
        )
        payload = {"data": payload_data}
        data = await self.client.put(path, json=payload)
        return Models.SimpleEmptyBody(**data)
