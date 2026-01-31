from typing import Any, Dict, List

import models as Models
import paths as Paths
from client import FlexHTTPClient

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


class FlexDeckConfigurationService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_deck_configuration(
        self,
    ) -> Models.SimpleBodyDeckConfigurationResponse:
        """
        GET /deck_configuration
        Retrieve the current physical setup of the Flex deck, including
        trash locations and staging areas.
        """
        path = Paths.Endpoints.FlexDeckConfiguration.DECK_CONFIG
        data = await self.client.get(path)
        return Models.SimpleBodyDeckConfigurationResponse(**data)

    async def set_deck_configuration(
        self, cutouts: List[Dict[str, Any]]
    ) -> Models.SimpleBodyDeckConfigurationResponse:
        """
        PUT /deck_configuration
        Inform the robot of its physical setup. This persists across reboots.

        Args:
            cutouts: A list of cutout configurations (e.g., cutoutId and fixtureId).
        """
        path = Paths.Endpoints.FlexDeckConfiguration.DECK_CONFIG
        payload = {"data": {"cutouts": cutouts}}
        data = await self.client.put(path, json=payload)
        return Models.SimpleBodyDeckConfigurationResponse(**data)
