"""
src.opentrons_sdk.services.camera

Service interface for accessing OT-2 camera.

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""

import paths as Paths
from client import FlexHTTPClient


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
