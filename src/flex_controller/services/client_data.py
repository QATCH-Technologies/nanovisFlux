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


class ClientDataservice:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_client_data(self, key: str) -> Dict[str, Any]:
        """
        GET /clientData/{key}
        Return the currently-stored client data at the given key.

        Args:
            key: A unique string key (alphanumeric, -, _) identifying the data.
        """
        path = Paths.Endpoints.Data.CLIENT_DATA_KEY.format(key=key)
        data = await self.client.get(path)
        return data.get("data", {})

    async def update_client_data(self, key: str, value: Dict[str, Any]) -> Dict[str, Any]:
        """
        PUT /clientData/{key}
        Store a small amount of arbitrary client-defined data. 
        Data is cleared when the robot reboots.

        Args:
            key: A unique string key (alphanumeric, -, _) identifying the data.
            value: A dictionary of data to store.
        """
        path = Paths.Endpoints.Data.CLIENT_DATA_KEY.format(key=key)
        payload = {"data": value}
        data = await self.client.put(path, json=payload)
        return data.get("data", {})

    async def delete_client_data(self, key: str) -> Dict[str, Any]:
        """
        DELETE /clientData/{key}
        Delete the client-defined data at the given key.

        Args:
            key: The unique string key identifying the data to delete.
        """
        path = Paths.Endpoints.Data.CLIENT_DATA.format(key=key)
        data = await self.client.delete(path)
        return data

    async def delete_all_client_data(self) -> Dict[str, Any]:
        """
        DELETE /clientData
        Delete all client-defined data currently stored in the robot's volatile memory.
        """
        path = Paths.Endpoints.Data.CLIENT_DATA
        data = await self.client.delete(path)
        return data