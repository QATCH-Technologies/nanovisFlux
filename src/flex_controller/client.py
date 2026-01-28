import asyncio
from typing import Any, Dict, Optional, Union

import aiohttp

# Import Constants
from .constants import APIDefaults

# Import Errors (Adjust path if your error file is located elsewhere)
try:
    from src.common.error import (
        FlexCommandError,
        FlexConnectionError,
        FlexMaintenanceError,
    )
except ImportError:
    # Fallback for standalone testing
    class FlexCommandError(Exception):
        pass

    class FlexConnectionError(Exception):
        pass

    class FlexMaintenanceError(Exception):
        pass


# Logging Setup
try:
    from src.common.log import get_logger

    log = get_logger("FlexClient")
except ImportError:
    import logging

    log = logging.getLogger("FlexClient")


class FlexHTTPClient:
    """
    Centralized HTTP Client for Opentrons Flex.
    Handles session management, headers, timeouts, and exception translation.
    """

    def __init__(self, base_url: str):
        # Ensure no trailing slash to avoid // in URLs
        self.base_url = base_url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None

        # Default timeout from constants
        self.default_timeout = aiohttp.ClientTimeout(total=APIDefaults.DEFAULT_TIMEOUT)

    async def connect(self):
        """Initializes the aiohttp ClientSession if not already open."""
        if not self.session or self.session.closed:
            log.debug(f"Opening new HTTP Session to {self.base_url}")
            self.session = aiohttp.ClientSession(
                headers=APIDefaults.VERSION_HEADER, timeout=self.default_timeout
            )

    async def close(self):
        """Closes the active session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
            log.debug("HTTP Session closed.")

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Any = None,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> Any:
        """
        Core request handler.

        Args:
            method: GET, POST, PUT, DELETE, PATCH.
            path: Endpoint path (e.g., '/health').
            params: URL Query parameters.
            json: JSON body payload.
            data: Raw data or FormData (for file uploads).
            timeout: Custom timeout in seconds (overrides default).

        Returns:
            The parsed JSON response or raw text.

        Raises:
            FlexConnectionError: Network issues.
            FlexMaintenanceError: Robot is booting (503).
            FlexCommandError: 4xx or 5xx API errors.
        """
        await self.connect()

        url = f"{self.base_url}{path}"

        # Handle custom request-specific timeouts
        request_timeout = self.default_timeout
        if timeout:
            request_timeout = aiohttp.ClientTimeout(total=timeout)

        try:
            async with self.session.request(
                method,
                url,
                params=params,
                json=json,
                data=data,
                timeout=request_timeout,
                **kwargs,
            ) as resp:

                # --- 1. Handle Opentrons Specific "Maintenance" State ---
                # 503 usually means the Robot Server is up, but Motor Controller is down/updating.
                if resp.status == 503:
                    try:
                        error_data = await resp.json()
                        msg = error_data.get("message", "Service Unavailable")
                    except Exception:
                        msg = await resp.text()
                    raise FlexMaintenanceError(f"System Busy (503): {msg}")

                # --- 2. Handle Standard Errors (4xx - 5xx) ---
                if resp.status >= 400:
                    try:
                        error_body = await resp.json()
                        # Opentrons usually puts details in 'message' or 'errors' list
                        if "message" in error_body:
                            detail = error_body["message"]
                        elif "errors" in error_body and isinstance(
                            error_body["errors"], list
                        ):
                            detail = str(error_body["errors"])
                        elif "detail" in error_body:
                            detail = str(error_body["detail"])
                        else:
                            detail = str(error_body)
                    except Exception:
                        detail = await resp.text()

                    log.error(f"API Error {resp.status} on {method} {path}: {detail}")
                    raise FlexCommandError(f"HTTP {resp.status}: {detail}")

                # --- 3. Handle Success (2xx) ---

                # 204 No Content
                if resp.status == 204:
                    return None

                # Try parsing JSON, fallback to Text
                try:
                    return await resp.json()
                except Exception:
                    return await resp.text()

        except asyncio.TimeoutError:
            log.error(f"Timeout connecting to {url}")
            raise FlexConnectionError(f"Request timed out: {method} {path}")

        except aiohttp.ClientError as e:
            log.error(f"Connection failed: {e}")
            raise FlexConnectionError(f"Connection failed to {self.base_url}") from e

    # --- Convenience Wrappers ---

    async def get(self, path: str, params: Optional[Dict] = None, **kwargs) -> Any:
        return await self.request("GET", path, params=params, **kwargs)

    async def post(
        self, path: str, json: Optional[Dict] = None, data: Any = None, **kwargs
    ) -> Any:
        return await self.request("POST", path, json=json, data=data, **kwargs)

    async def put(self, path: str, json: Optional[Dict] = None, **kwargs) -> Any:
        return await self.request("PUT", path, json=json, **kwargs)

    async def patch(self, path: str, json: Optional[Dict] = None, **kwargs) -> Any:
        return await self.request("PATCH", path, json=json, **kwargs)

    async def delete(self, path: str, params: Optional[Dict] = None, **kwargs) -> Any:
        return await self.request("DELETE", path, params=params, **kwargs)
