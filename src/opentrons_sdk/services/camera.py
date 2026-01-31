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


class CameraService:
    def __init__(self, client: FlexHTTPClient):
        self.client = client

    async def take_picture(self) -> bytes:
        """
        POST /camera/picture
        Capture an image from the robot's on-board camera and return the raw bytes.
        """
        path = Paths.Endpoints.Camera.CAMERA_PICTURE
        data = await self.client.post(path)
        return data