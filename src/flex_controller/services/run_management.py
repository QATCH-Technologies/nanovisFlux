import os
from typing import Any, Dict

import aiohttp
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
    ) -> Models.MultiBody_Union_Run__BadRun__AllRunsLinks_:
        """
        GET /runs
        Get a list of all active and inactive runs, in order from oldest to newest.

        Args:
            page_length: The maximum number of runs to return. If omitted, all runs are returned.
        """
        # References 'RUNS = "/runs"' in Endpoints.Runs
        path = Paths.Endpoints.Runs.RUNS

        params = {"pageLength": page_length} if page_length is not None else {}

        data = await self.client.get(path, params=params)

        return Models.MultiBody_Union_Run__BadRun__AllRunsLinks_(**data)

    async def create_run(
        self, run_data: Optional[Union[Models.RunCreate, Dict[str, Any]]] = None
    ) -> Models.SimpleBody_Run_:
        """
        POST /runs
        Create a new run to track robot interaction.

        When too many runs already exist, old ones are automatically deleted
        to make room for the new one.

        Args:
            run_data: Optional RunCreate model or dict containing protocolId,
                      labwareOffsets, or metadata.
        """
        path = Endpoints.Runs.RUNS

        payload = None
        if run_data is not None:
            # Ensure the data is converted to a dictionary for the JSON body
            if hasattr(run_data, "model_dump"):
                payload_data = run_data.model_dump(exclude_none=True)
            else:
                payload_data = dict(run_data)
            payload = {"data": payload_data}

        data = await self.client.post(path, json=payload)

        return Models.SimpleBody_Run_(**data)
