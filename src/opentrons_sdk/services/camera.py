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

        # --- FIX: Bypass client.post to avoid UTF-8 decoding errors ---
        # The standard client.post() likely tries to parse JSON, which fails on binary images.
        # We access the underlying session to get raw bytes.

        # 1. Construct Full URL (Try common attribute names for base_url)
        base_url = getattr(self.client, "base_url", "")
        if not base_url:
            # Fallback: Try to reconstruction from internal session if possible,
            # or assume the session has the base_url baked in (httpx behavior).
            url = path
        else:
            url = f"{base_url}{path}"

        session = self.client.session

        # 2. Make Request directly via Session
        # We assume the session is either aiohttp or httpx
        if hasattr(session, "post"):
            # Check if it's aiohttp (context manager style)
            if hasattr(session, "ws_connect"):  # specific to aiohttp
                async with session.post(url) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"Camera Error: {resp.status}")
                    return await resp.read()  # Returns bytes

            # Assume httpx (awaitable)
            else:
                resp = await session.post(url)
                if resp.status_code != 200:
                    raise RuntimeError(f"Camera Error: {resp.status_code}")
                return resp.content  # Returns bytes

        # Fallback if session structure is unknown
        raise RuntimeError("Could not access raw session for binary download.")
