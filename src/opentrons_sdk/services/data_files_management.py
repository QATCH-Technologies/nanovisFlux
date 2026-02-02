"""
src.opentrons_sdk.services.data_files_management

Service interface for managing data files on robot.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import os

import models as Models
import paths as Paths
from client import FlexHTTPClient


class DataFilesManagamentService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_all_data_files(self) -> Models.SimpleMultiBodyStr:
        """
        GET /dataFiles
        Retrieve a list of all data file IDs stored on the robot server.
        """
        path = Paths.Endpoints.Data.DATA_FILES
        data = await self.client.get(path)
        return Models.SimpleMultiBodyStr(**data)

    async def upload_data_file(self, file_path: str) -> Models.SimpleBodyDataFile:
        """
        POST /dataFiles
        Upload a standalone data file (CSV, JSON, etc.) to the robot.

        Args:
            file_path: Local path to the data file to be uploaded.
        """
        path = Paths.Endpoints.Data.DATA_FILES
        file_name = os.path.basename(file_path)
        files = [("file", (file_name, open(file_path, "rb")))]
        try:
            data = await self.client.post(path, files=files)
        finally:
            files[0][1][1].close()
        return Models.SimpleBodyDataFile(**data)

    async def get_data_file(self, file_id: str) -> Models.SimpleBodyDataFile:
        """
        GET /dataFiles/{dataFileId}
        Retrieve metadata about a specific uploaded or generated data file.

        Args:
            file_id: The unique identifier of the data file.
        """
        path = Paths.Endpoints.Data.DATA_FILE_ID.format(dataFileId=file_id)
        data = await self.client.get(path)
        return Models.SimpleBodyDataFile(**data)

    async def delete_data_file(self, file_id: str) -> Models.SimpleEmptyBody:
        """
        DELETE /dataFiles/{dataFileId}
        Delete a data file from the robot's persistent storage.

        Note: This will return a 409 Conflict if the file is currently
        being used by a protocol analysis or a run.
        """
        path = Paths.Endpoints.Data.DATA_FILE_ID.format(dataFileId=file_id)
        data = await self.client.delete(path)
        return Models.SimpleEmptyBody(**data)

    async def download_data_file(self, file_id: str) -> bytes:
        """
        GET /dataFiles/{dataFileId}/download
        Download the raw content of an uploaded or generated data file.

        Args:
            file_id: The unique identifier of the data file.

        Returns:
            The raw bytes of the file (e.g., CSV text or JSON data).
        """

        path = Paths.Endpoints.Data.DATA_FILE_DOWNLOAD.format(dataFileId=file_id)
        return await self.client.get_raw(path)
