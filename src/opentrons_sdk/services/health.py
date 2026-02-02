"""
src.opentrons_sdk.services.health

Service interface for getting robot health statuses.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import models as Models
import paths as Paths
from client import FlexHTTPClient


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
