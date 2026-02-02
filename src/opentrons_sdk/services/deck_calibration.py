"""
src.opentrons_sdk.services.deck_calibration

Service interface for calibrating robot deck(s).

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


class DeckCalibrationService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def get_calibration_status(self) -> Models.DeckCalibrationStatus:
        """
        GET /calibration/status
        Get the current calibration status of the robot.
        """
        path = Paths.Endpoints.Calibration.STATUS
        data = await self.client.get(path)
        return Models.DeckCalibrationStatus(**data)
