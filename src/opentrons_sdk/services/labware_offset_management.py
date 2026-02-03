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

    async def get_labware_offsets(self, cursor=None, page_length="unlimited"):
        """
        GET /labwareOffsets
        """
        path = Paths.Endpoints.Data.LABWARE_OFFSETS
        params = {"cursor": cursor, "pageLength": page_length}
        clean_params = {k: v for k, v in params.items() if v is not None}
        # Return raw dict to avoid validation errors
        return await self.client.get(path, params=clean_params)

    async def add_labware_offsets(self, offsets):
        """
        POST /labwareOffsets
        Store one or more labware offsets.
        """
        path = Paths.Endpoints.Data.LABWARE_OFFSETS

        # Helper to serialize Pydantic models if passed, otherwise use dicts
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

        # The API accepts data as a list or single object, but wrapping in list is safer
        # if the input was a single dict.
        if isinstance(payload_data, dict):
            payload_data = [payload_data]

        payload = {"data": payload_data}

        # Return raw dict to avoid validation errors
        return await self.client.post(path, json=payload)

    async def search_labware_offsets(self, search_query):
        """
        POST /labwareOffsets/searches
        """
        path = Paths.Endpoints.Data.LABWARE_OFFSET_SEARCH

        if hasattr(search_query, "model_dump"):
            query_data = search_query.model_dump(exclude_none=True)
        else:
            query_data = search_query

        payload = {"data": query_data}
        # Return raw dict to avoid validation errors
        return await self.client.post(path, json=payload)

    async def delete_all_labware_offsets(self):
        """DELETE /labwareOffsets"""
        path = Paths.Endpoints.Data.LABWARE_OFFSETS
        return await self.client.delete(path)

    async def delete_labware_offset(self, offset_id: str):
        """DELETE /labwareOffsets/{id}"""
        path = Paths.Endpoints.Data.LABWARE_OFFSET_ID.format(id=offset_id)
        return await self.client.delete(path)
