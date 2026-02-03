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

"""
src.opentrons_sdk.services.maintenance_run_management

Service interface for maintenance run management.
"""

from typing import Any, Dict, List, Optional, Union

import paths as Paths
from client import FlexHTTPClient
from pydantic import BaseModel


class MaintenanceRunManagementService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def create_maintenance_run(
        self,
        run_data: Optional[Union[BaseModel, Dict[str, Any]]] = None,
    ):
        """
        POST /maintenance_runs
        Create a new maintenance run.
        """
        path = Paths.Endpoints.MaintenanceRuns.CREATE
        payload = None
        if run_data is not None:
            if isinstance(run_data, BaseModel):
                payload_data = run_data.model_dump(exclude_none=True)
            else:
                payload_data = dict(run_data)
            payload = {"data": payload_data}

        # Return raw dict to avoid Pydantic validation errors
        return await self.client.post(path, json=payload)

    async def get_current_maintenance_run(self):
        """
        GET /maintenance_runs/current_run
        """
        path = Paths.Endpoints.MaintenanceRuns.CURRENT
        return await self.client.get(path)

    async def get_maintenance_run(self, run_id: str):
        """
        GET /maintenance_runs/{runId}
        """
        path = Paths.Endpoints.MaintenanceRuns.GET_ID.format(runId=run_id)
        return await self.client.get(path)

    async def delete_maintenance_run(self, run_id: str):
        """
        DELETE /maintenance_runs/{runId}
        """
        path = Paths.Endpoints.MaintenanceRuns.DELETE.format(runId=run_id)
        return await self.client.delete(path)

    async def get_maintenance_run_commands(
        self, run_id: str, cursor: Optional[int] = None, page_length: int = 20
    ):
        """
        GET /maintenance_runs/{runId}/commands
        """
        path = Paths.Endpoints.MaintenanceRuns.COMMANDS.format(runId=run_id)
        params = {"cursor": cursor, "pageLength": page_length}
        return await self.client.get(
            path, params={k: v for k, v in params.items() if v is not None}
        )

    async def enqueue_maintenance_command(
        self,
        run_id: str,
        command: Dict[str, Any],
        wait_until_complete: bool = False,
        timeout: Optional[int] = None,
    ):
        """
        POST /maintenance_runs/{runId}/commands
        Enqueue a single command.
        Returns RAW DICTIONARY to avoid Pydantic validation errors on commandType.
        """
        path = Paths.Endpoints.MaintenanceRuns.COMMANDS.format(runId=run_id)
        params = {
            "waitUntilComplete": str(wait_until_complete).lower(),
            "timeout": timeout,
        }
        payload = {"data": command}

        #
        # We deliberately return the raw response here.
        # The generated model for Union[AirGap, Aspirate, ...] is broken.
        return await self.client.post(
            path,
            json=payload,
            params={k: v for k, v in params.items() if v is not None},
        )

    async def get_maintenance_run_command(self, run_id: str, command_id: str):
        """
        GET /maintenance_runs/{runId}/commands/{commandId}
        """
        path = Paths.Endpoints.MaintenanceRuns.COMMAND_ID.format(
            runId=run_id, commandId=command_id
        )
        return await self.client.get(path)

    async def add_maintenance_run_labware_offsets(
        self,
        run_id: str,
        offsets: Union[BaseModel, List[BaseModel], Dict[str, Any]],
    ):
        """
        POST /maintenance_runs/{runId}/labware_offsets
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
        return await self.client.post(path, json=payload)

    async def add_maintenance_run_labware_definition(
        self,
        run_id: str,
        definition: Union[Dict[str, Any], BaseModel],
    ):
        """
        POST /maintenance_runs/{runId}/labware_definitions
        """
        path = Paths.Endpoints.MaintenanceRuns.LABWARE_DEFS.format(runId=run_id)
        payload_data = (
            definition.model_dump(exclude_none=True)
            if isinstance(definition, BaseModel)
            else definition
        )
        payload = {"data": payload_data}
        return await self.client.post(path, json=payload)
