import asyncio
from typing import Any, Dict, List, Optional

import aiohttp

from ..client import FlexHTTPClient
from ..constants import Endpoints
from ..schemas import (
    DataFile,
    LabwareOffset,
    ProtocolAnalysis,
    ProtocolData,
    RunActionType,
    RunCommandSummary,
    RunData,
    RunStatus,
)

# Logging import
try:
    from flex_serial_controls.log import get_tagged_logger

    log = get_tagged_logger("FlexRuns")
except ImportError:
    import logging

    log = logging.getLogger("FlexRuns")


class RunService:
    """
    Manages the Protocol Engine Lifecycle:
    - Standard Runs (Protocol execution)
    - Maintenance Runs (Manual control/Fixit)
    - Protocol Files (Upload/Analyze)
    - Data Files (CSV/Input)
    - Stateless Commands (Simple actions)
    """

    def __init__(self, client: FlexHTTPClient):
        self.client = client
        self.current_run_id: Optional[str] = None
        self.current_maintenance_run_id: Optional[str] = None

    # ============================================================================
    #                               STANDARD RUNS
    # ============================================================================

    async def create_run(
        self,
        protocol_id: Optional[str] = None,
        labware_offsets: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        POST /runs
        Create a new run context.
        """
        payload_data = {}
        if protocol_id:
            payload_data["protocolId"] = protocol_id
        if labware_offsets:
            payload_data["labwareOffsets"] = labware_offsets

        # Post wrapping data in "data" key
        response = await self.client.post(Endpoints.RUNS, json={"data": payload_data})

        data = response["data"]
        self.current_run_id = data["id"]
        log.info(f"Created new run: {self.current_run_id}")
        return self.current_run_id

    async def get_run(self, run_id: str) -> RunData:
        """
        GET /runs/{runId}
        """
        path = f"{Endpoints.RUNS}/{run_id}"
        data = await self.client.get(path)
        return RunData(**data["data"])

    async def get_all_runs(self, limit: int = 20) -> List[RunData]:
        """
        GET /runs
        """
        params = {"pageLength": limit}
        data = await self.client.get(Endpoints.RUNS, params=params)
        return [RunData(**item) for item in data.get("data", [])]

    async def delete_run(self, run_id: str):
        """
        DELETE /runs/{runId}
        """
        path = f"{Endpoints.RUNS}/{run_id}"
        await self.client.delete(path)

        if self.current_run_id == run_id:
            self.current_run_id = None
        log.debug(f"Deleted run: {run_id}")

    # ============================================================================
    #                               RUN CONTROLS
    # ============================================================================

    async def send_run_action(self, action: RunActionType):
        """
        POST /runs/{runId}/actions
        Issue a control action (Play, Pause, Stop, Resume).
        """
        if not self.current_run_id:
            raise RuntimeError("No active run to control.")

        path = Endpoints.RUN_ACTIONS.format(run_id=self.current_run_id)
        payload = {"data": {"actionType": action.value}}

        try:
            await self.client.post(path, json=payload)
            log.info(f"Run Action Sent: {action.value}")
        except Exception as e:
            # 409 Conflict is common if already running/paused
            if "409" in str(e):
                log.warning(f"Action {action.value} ignored (State Conflict)")
            else:
                raise e

    async def play(self):
        await self.send_run_action(RunActionType.PLAY)

    async def pause(self):
        await self.send_run_action(RunActionType.PAUSE)

    async def stop(self):
        await self.send_run_action(RunActionType.STOP)

    async def resume_from_recovery(self):
        await self.send_run_action(RunActionType.RESUME_FROM_RECOVERY)

    # ============================================================================
    #                               RUN COMMANDS
    # ============================================================================

    async def execute_command(
        self,
        command_type: str,
        params: Dict[str, Any],
        wait: bool = True,
        intent: str = "setup",
    ) -> Dict[str, Any]:
        """
        POST /runs/{runId}/commands
        Enqueue a command to the current run.
        """
        if not self.current_run_id:
            await self.create_run()

        path = Endpoints.RUN_COMMANDS.format(run_id=self.current_run_id)
        payload = {
            "data": {"commandType": command_type, "params": params, "intent": intent}
        }

        # Infinite timeout for blocking commands
        qs_params = {"waitUntilComplete": "true", "timeout": "infinite"} if wait else {}

        response = await self.client.post(path, json=payload, params=qs_params)
        result_data = response.get("data", {})

        # Check for Protocol Engine logic errors returned in 201 response
        if result_data.get("status") == "failed":
            error_detail = result_data.get("error", {}).get(
                "detail", "Unknown Protocol Error"
            )
            log.error(f"Command {command_type} FAILED: {error_detail}")
            # Raise generic exception or specific one if available
            raise RuntimeError(f"Protocol Error: {error_detail}")

        return result_data

    async def get_run_commands(self, run_id: str = None) -> List[RunCommandSummary]:
        """
        GET /runs/{runId}/commands
        """
        target_id = run_id or self.current_run_id
        if not target_id:
            raise ValueError("No run specified.")

        path = Endpoints.RUN_COMMANDS.format(run_id=target_id)
        data = await self.client.get(path)
        return [RunCommandSummary(**item) for item in data.get("data", [])]

    async def add_run_labware_offset(self, offset: LabwareOffset):
        """
        POST /runs/{runId}/labware_offsets
        Apply an offset to the ACTIVE run.
        """
        if not self.current_run_id:
            raise RuntimeError("No active run.")

        path = f"{Endpoints.RUNS}/{self.current_run_id}/labware_offsets"
        payload = {
            "data": {
                "definitionUri": offset.definitionUri,
                "locationSequence": offset.locationSequence,
                "vector": offset.vector.model_dump(),
            }
        }

        await self.client.post(path, json=payload)
        log.debug(f"Offset added to run {self.current_run_id}")

    # ============================================================================
    #                           MAINTENANCE RUNS
    # ============================================================================

    async def create_maintenance_run(
        self, labware_offsets: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        POST /maintenance_runs
        Create a maintenance run for immediate manual control.
        """
        payload_data = {}
        if labware_offsets:
            payload_data["labwareOffsets"] = labware_offsets

        try:
            response = await self.client.post(
                Endpoints.MAINTENANCE_RUNS, json={"data": payload_data}
            )
            data = response["data"]
            self.current_maintenance_run_id = data["id"]
            log.info(f"Created Maintenance Run: {self.current_maintenance_run_id}")
            return self.current_maintenance_run_id
        except Exception as e:
            if "409" in str(e):
                raise RuntimeError(
                    "Cannot create Maintenance Run: A Protocol Run is currently active."
                )
            raise e

    async def get_current_maintenance_run(self) -> Optional[RunData]:
        """
        GET /maintenance_runs/current_run
        """
        try:
            data = await self.client.get(Endpoints.MAINTENANCE_RUNS_CURRENT)
            run_data = RunData(**data["data"])
            self.current_maintenance_run_id = run_data.id
            return run_data
        except Exception as e:
            if "404" in str(e):
                return None
            raise e

    async def delete_maintenance_run(self, run_id: str = None):
        """
        DELETE /maintenance_runs/{runId}
        """
        target_id = run_id or self.current_maintenance_run_id
        if not target_id:
            return

        path = f"{Endpoints.MAINTENANCE_RUNS}/{target_id}"
        await self.client.delete(path)

        if self.current_maintenance_run_id == target_id:
            self.current_maintenance_run_id = None
        log.debug(f"Deleted maintenance run: {target_id}")

    async def execute_maintenance_command(
        self, command_type: str, params: Dict[str, Any], wait: bool = True
    ) -> Dict[str, Any]:
        """
        POST /maintenance_runs/{runId}/commands
        Execute immediate command.
        """
        if not self.current_maintenance_run_id:
            await self.create_maintenance_run()

        path = (
            f"{Endpoints.MAINTENANCE_RUNS}/{self.current_maintenance_run_id}/commands"
        )
        payload = {
            "data": {"commandType": command_type, "params": params, "intent": "setup"}
        }

        qs_params = {"waitUntilComplete": "true", "timeout": "infinite"} if wait else {}

        response = await self.client.post(path, json=payload, params=qs_params)
        result_data = response.get("data", {})

        if result_data.get("status") == "failed":
            error_detail = result_data.get("error", {}).get("detail", "Unknown Error")
            log.error(f"Maintenance Command {command_type} FAILED: {error_detail}")
            raise RuntimeError(error_detail)

        return result_data

    # ============================================================================
    #                               PROTOCOLS
    # ============================================================================

    async def upload_protocol(
        self,
        file_path: str,
        labware_paths: Optional[List[str]] = None,
        protocol_kind: str = "standard",
        key: Optional[str] = None,
    ) -> ProtocolData:
        """
        POST /protocols
        Upload protocol file(s).
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Protocol file not found: {file_path}")

        data = aiohttp.FormData()
        data.add_field(
            "files", open(file_path, "rb"), filename=os.path.basename(file_path)
        )

        if labware_paths:
            for lw_path in labware_paths:
                if os.path.exists(lw_path):
                    data.add_field(
                        "files", open(lw_path, "rb"), filename=os.path.basename(lw_path)
                    )

        if key:
            data.add_field("key", key)
        data.add_field("protocol_kind", protocol_kind)

        response = await self.client.post(Endpoints.PROTOCOLS, data=data)
        return ProtocolData(**response["data"])

    async def get_protocols(self, limit: int = 20) -> List[ProtocolData]:
        """
        GET /protocols
        """
        # Note: 'pageLength' param support varies by API version for this endpoint
        data = await self.client.get(Endpoints.PROTOCOLS)
        return [ProtocolData(**item) for item in data.get("data", [])]

    async def get_protocol(self, protocol_id: str) -> ProtocolData:
        """
        GET /protocols/{protocolId}
        """
        path = f"{Endpoints.PROTOCOLS}/{protocol_id}"
        data = await self.client.get(path)
        return ProtocolData(**data["data"])

    async def delete_protocol(self, protocol_id: str):
        """
        DELETE /protocols/{protocolId}
        """
        path = f"{Endpoints.PROTOCOLS}/{protocol_id}"
        await self.client.delete(path)
        log.info(f"Deleted protocol: {protocol_id}")

    async def analyze_protocol(self, protocol_id: str, force_reanalyze: bool = False):
        """
        POST /protocols/{protocolId}/analyses
        """
        path = Endpoints.PROTOCOL_ANALYSES.format(protocol_id=protocol_id)
        payload = {"data": {"forceReAnalyze": force_reanalyze}}
        return await self.client.post(path, json=payload)

    async def get_analysis_status(
        self, protocol_id: str, analysis_id: str
    ) -> Dict[str, Any]:
        """
        GET /protocols/{protocolId}/analyses/{analysisId}
        """
        path = (
            Endpoints.PROTOCOL_ANALYSES.format(protocol_id=protocol_id)
            + f"/{analysis_id}"
        )
        data = await self.client.get(path)
        return data.get("data", {})

    async def upload_data_file(self, file_path: str) -> DataFile:
        """
        POST /dataFiles
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Data file not found: {file_path}")

        data = aiohttp.FormData()
        data.add_field(
            "file", open(file_path, "rb"), filename=os.path.basename(file_path)
        )

        response = await self.client.post(Endpoints.DATA_FILES, data=data)
        return DataFile(**response["data"])

    # ============================================================================
    #                            STATELESS COMMANDS
    # ============================================================================

    async def execute_stateless_command(
        self,
        command_type: str,
        params: Dict[str, Any],
        wait: bool = True,
        timeout: int = None,
    ) -> Dict[str, Any]:
        """
        POST /commands
        Execute simple command (e.g. 'home') without a run context.
        """
        payload = {"data": {"commandType": command_type, "params": params}}

        qs_params = {}
        if wait:
            qs_params["waitUntilComplete"] = "true"
            if timeout:
                qs_params["timeout"] = str(timeout)

        try:
            response = await self.client.post(
                Endpoints.COMMANDS, json=payload, params=qs_params
            )
            result_data = response.get("data", {})

            if result_data.get("status") == "failed":
                error_detail = result_data.get("error", {}).get(
                    "detail", "Unknown Error"
                )
                log.error(f"Stateless Command {command_type} FAILED: {error_detail}")
                raise RuntimeError(error_detail)

            return result_data
        except Exception as e:
            if "409" in str(e):
                raise RuntimeError(
                    "Cannot execute stateless command: A Run is currently active."
                )
            raise e

    async def get_stateless_commands(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        GET /commands
        """
        params = {"pageLength": limit}
        data = await self.client.get(Endpoints.COMMANDS, params=params)
        return data.get("data", [])
