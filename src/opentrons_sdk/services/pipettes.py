"""
src.opentrons_sdk.services.pipettes

Service interface for managing pipettes.

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
