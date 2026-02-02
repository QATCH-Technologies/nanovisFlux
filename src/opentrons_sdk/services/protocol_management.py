"""
src.opentrons_sdk.services.protocol_management

Service interface for creation and manamgement of protocols.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import os
from typing import Any, Dict, List, Optional, Union

import models as Models
import paths as Paths
from client import FlexHTTPClient
from pydantic import BaseModel


class ProtocolManagementService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_protocols(
        self, protocol_kind: Optional[str] = None
    ) -> Models.SimpleMultiBodyProtocol:
        """
        GET /protocols
        Return all stored protocols, in order from first-uploaded to last-uploaded.

        Args:
            protocol_kind: 'standard' or 'quick-transfer'. Defaults to all.
        """
        path = Paths.Endpoints.Protocols.GET_ALL
        params = {"protocolKind": protocol_kind} if protocol_kind else {}
        data = await self.client.get(path, params=params)
        return Models.SimpleMultiBodyProtocol(**data)

    async def upload_protocol(
        self, files: List[str], protocol_kind: str = "standard"
    ) -> Models.SimpleBodyProtocol:
        """
        POST /protocols
        Upload a protocol file and optional custom labware.

        Args:
            files: A list of local file paths. Must include exactly one
                   Python or JSON protocol file.
            protocol_kind: 'standard' or 'quick-transfer'.
        """
        path = Paths.Endpoints.Protocols.CREATE
        form_files = []
        for file_path in files:
            file_name = os.path.basename(file_path)
            form_files.append(("files", (file_name, open(file_path, "rb"))))
        data = {"protocol_kind": protocol_kind}
        try:
            response_data = await self.client.post(path, data=data, files=form_files)
        finally:
            for _, (_, file_handle) in form_files:
                file_handle.close()
        return Models.SimpleBodyProtocol(**response_data)

    async def get_protocol_ids(self) -> Models.SimpleMultiBodyStr:
        """
        GET /protocols/ids
        [Internal/Experimental] Get the IDs of all protocols stored on the server.

        WARNING: This is an experimental endpoint meant for internal use and
        may change or be removed without warning.
        """
        path = Paths.Endpoints.Protocols.GET_IDS
        data = await self.client.get(path)
        return Models.SimpleMultiBodyStr(**data)

    async def get_protocol(self, protocol_id: str) -> Models.BodyProtocolProtocolLinks:
        """
        GET /protocols/{protocolId}
        Get an uploaded protocol's metadata and analysis status by ID.

        Args:
            protocol_id: The unique identifier assigned during upload.
        """
        path = Paths.Endpoints.Protocols.GET_BY_ID.format(protocolId=protocol_id)
        data = await self.client.get(path)
        return Models.BodyProtocolProtocolLinks(**data)

    async def delete_protocol(self, protocol_id: str) -> Models.SimpleEmptyBody:
        """
        DELETE /protocols/{protocolId}
        Remove a protocol from the robot's storage.

        Note: This will fail with a 409 Conflict if there is an existing run
        (active or historical) that refers to this protocol.
        """
        path = Paths.Endpoints.Protocols.DELETE.format(protocolId=protocol_id)
        data = await self.client.delete(path)
        return Models.SimpleEmptyBody(**data)

    async def get_protocol_analyses(
        self, protocol_id: str
    ) -> Models.SimpleMultiBodyUnionPendingAnalysisCompletedAnalysis:
        """
        GET /protocols/{protocolId}/analyses
        Get the full list of analyses for a protocol, ordered from oldest to newest.
        """
        path = Paths.Endpoints.Protocols.GET_ANALYSES.format(protocolId=protocol_id)
        data = await self.client.get(path)
        return Models.SimpleMultiBodyUnionPendingAnalysisCompletedAnalysis(**data)

    async def create_protocol_analysis(
        self,
        protocol_id: str,
        analysis_request: Optional[
            Union[Models.AnalysisRequest, Dict[str, Any]]
        ] = None,
    ) -> Models.SimpleMultiBodyAnalysisSummary:
        """
        POST /protocols/{protocolId}/analyses
        Manually trigger a new analysis. This is useful if you want to re-simulate
        with different run-time parameters.

        Args:
            protocol_id: Unique identifier of the protocol.
            analysis_request: Optional configuration including run-time parameters.
        """
        path = Paths.Endpoints.Protocols.CREATE_ANALYSIS.format(protocolId=protocol_id)
        payload = None

        if analysis_request is not None:
            if isinstance(analysis_request, BaseModel):
                payload_data = analysis_request.model_dump(exclude_none=True)
            else:
                payload_data = dict(analysis_request)

            payload = {"data": payload_data}

        data = await self.client.post(path, json=payload)
        return Models.SimpleMultiBodyAnalysisSummary(**data)

    async def get_protocol_analysis(
        self, protocol_id: str, analysis_id: str
    ) -> Models.SimpleBodyUnionPendingAnalysisCompletedAnalysis:
        """
        GET /protocols/{protocolId}/analyses/{analysisId}
        Retrieve a specific protocol analysis by its ID.

        Args:
            protocol_id: The ID of the protocol.
            analysis_id: The ID of the analysis.
        """
        path = Paths.Endpoints.Protocols.GET_ANALYSIS_ID.format(
            protocolId=protocol_id, analysisId=analysis_id
        )
        data = await self.client.get(path)
        return Models.SimpleBodyUnionPendingAnalysisCompletedAnalysis(**data)

    async def get_protocol_analysis_as_document(
        self, protocol_id: str, analysis_id: str
    ) -> Dict[str, Any]:
        """
        GET /protocols/{protocolId}/analyses/{analysisId}/asDocument
        [Experimental] Get a protocol's completed analysis as a raw JSON document.

        This is a high-speed alternative for large protocols. Note that it
        returns a 404 if the analysis is still 'pending'.

        Args:
            protocol_id: The ID of the protocol.
            analysis_id: The ID of the analysis.
        """
        path = Paths.Endpoints.Protocols.GET_AS_DOCUMENT.format(
            protocolId=protocol_id, analysisId=analysis_id
        )
        return await self.client.get(path)

    async def get_protocol_data_files(
        self, protocol_id: str
    ) -> Models.SimpleMultiBodyDataFile:
        """
        GET /protocols/{protocolId}/dataFiles
        Get all data files used in analyses and runs for a specific protocol.

        Args:
            protocol_id: The unique identifier of the protocol.
        """
        path = Paths.Endpoints.Protocols.GET_DATA_FILES.format(protocolId=protocol_id)
        data = await self.client.get(path)
        return Models.SimpleMultiBodyDataFile(**data)
