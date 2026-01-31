import os
from typing import Optional

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


class HealthService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_health(self) -> Models.Health:
        """
        GET /health
        Check that the robot server is running and ready to operate.
        Returns information about the software version and system status.
        A 200 OK response indicates the server is healthy.
        """
        path = Paths.Endpoints.RobotControl.HEALTH
        data = await self.client.get(path)
        return Models.Health(**data)