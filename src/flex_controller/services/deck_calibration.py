from typing import Any, Dict, Union

import models as Models
import paths as Paths
from client import FlexHTTPClient

try:
    from src.common.log import get_logger

    log = get_logger("FlexSystem")
except ImportError:
    import logging

    log = logging.getLogger("FlexSystem")


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