"""
src.opentrons_sdk.services.labware_offset_management

Service interface for managing labware offsets.

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


class LabwareOffsetManagementService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_labware_offsets(
        self, cursor: Optional[int] = None, page_length: Union[int, str] = "unlimited"
    ) -> Models.SimpleMultiBodyStoredLabwareOffset:
        """
        GET /labwareOffsets
        Get all the labware offsets currently stored on the robot.
        Results are returned in order from oldest to newest.

        Args:
            cursor: The first index to return.
            page_length: The maximum number of entries to return (integer or "unlimited").
        """
        path = Paths.Endpoints.Data.LABWARE_OFFSETS
        params = {"cursor": cursor, "pageLength": page_length}
        data = await self.client.get(
            path, params={k: v for k, v in params.items() if v is not None}
        )
        return Models.SimpleMultiBodyStoredLabwareOffset(**data)

    async def add_labware_offsets(
        self,
        offsets: Union[
            Models.StoredLabwareOffsetCreate,
            List[Models.StoredLabwareOffsetCreate],
            Dict[str, Any],
        ],
    ) -> Models.SimpleBodyUnionStoredLabwareOffsetListStoredLabwareOffset:
        """
        POST /labwareOffsets
        Store one or more labware offsets for later retrieval.

        Args:
            offsets: A single offset, a list of offsets, or a raw dictionary.
        """
        path = Paths.Endpoints.Data.LABWARE_OFFSETS

        if isinstance(offsets, list):
            payload_data = [
                o.model_dump(exclude_none=True) if hasattr(o, "model_dump") else o
                for o in offsets
            ]
        else:
            model_dump = getattr(offsets, "model_dump", None)
            if model_dump and callable(model_dump):
                payload_data = model_dump(exclude_none=True)
            else:
                payload_data = offsets
        payload = {"data": payload_data}
        data = await self.client.post(path, json=payload)
        return Models.SimpleBodyUnionStoredLabwareOffsetListStoredLabwareOffset(**data)

    async def delete_all_labware_offsets(self) -> Models.SimpleEmptyBody:
        """
        DELETE /labwareOffsets
        Delete all labware offsets currently stored on the robot.
        """
        path = Paths.Endpoints.Data.LABWARE_OFFSETS
        data = await self.client.delete(path)
        return Models.SimpleEmptyBody(**data)

    async def search_labware_offsets(
        self, search_query: Union[Models.SearchCreate, Dict[str, Any]]
    ) -> Models.SimpleMultiBodyStoredLabwareOffset:
        """
        POST /labwareOffsets/searches
        Search for labware offsets matching specific criteria.

        Args:
            search_query: A SearchCreate model or dict containing search criteria
                         (e.g., labware definition URI, location, etc.).
        """
        path = Paths.Endpoints.Data.LABWARE_OFFSET_SEARCH
        if isinstance(search_query, Models.SearchCreate):
            query_data = search_query.model_dump(exclude_none=True)
        else:
            query_data = search_query

        payload = {"data": query_data}

        data = await self.client.post(path, json=payload)

        return Models.SimpleMultiBodyStoredLabwareOffset(**data)

    async def delete_labware_offset(
        self, offset_id: str
    ) -> Models.SimpleBodyStoredLabwareOffset:
        """
        DELETE /labwareOffsets/{id}
        Delete a single labware offset. The deleted offset is returned.

        Args:
            offset_id: The unique ID of the offset to delete.
        """
        path = Paths.Endpoints.Data.LABWARE_OFFSET_ID.format(id=offset_id)
        data = await self.client.delete(path)
        return Models.SimpleBodyStoredLabwareOffset(**data)
