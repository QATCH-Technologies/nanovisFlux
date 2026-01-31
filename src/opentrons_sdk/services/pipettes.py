import os
from typing import Any, Dict, Union

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


class PipetteService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_pipettes(self, refresh: bool = False) -> Models.PipettesByMount:
        """
        GET /pipettes
        Get the pipettes currently attached to the robot.

        Args:
            refresh: If True, actively scan for attached pipettes (OT-2 only).
                     Warning: Actively scanning disables pipette motors.
                     If False, query the cached value.
        """
        path = Paths.Endpoints.Components.PIPETTES_ATTACHED
        params = {"refresh": str(refresh).lower()}
        data = await self.client.get(path, params=params)
        return Models.PipettesByMount(**data)
