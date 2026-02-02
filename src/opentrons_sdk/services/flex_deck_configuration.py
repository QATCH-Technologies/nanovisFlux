"""
src.opentrons_sdk.services.flex_deck_configuration

Service interface for configuring Flex deck layout.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

from typing import Any, Dict, List

import models as Models
import paths as Paths
from client import FlexHTTPClient


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
