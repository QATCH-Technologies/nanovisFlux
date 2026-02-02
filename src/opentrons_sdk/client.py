import asyncio
from typing import Any, Dict, Optional, Union

import aiohttp
from constants import APIDefaults

try:
    from src.common.error import (
        FlexCommandError,
        FlexConflictError,
        FlexConnectionError,
        FlexMaintenanceError,
        FlexNotFoundError,
    )
except ImportError:

    class FlexCommandError(Exception):
        pass

    class FlexConnectionError(Exception):
        pass

    class FlexMaintenanceError(Exception):
        pass

    class FlexConflictError(FlexCommandError):
        pass

    class FlexNotFoundError(FlexCommandError):
        pass


try:
    from src.common.log import get_logger

    log = get_logger("FlexClient")
except ImportError:
    import logging

    log = logging.getLogger("FlexClient")


class FlexHTTPClient:

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None
        self.default_timeout = aiohttp.ClientTimeout(total=APIDefaults.DEFAULT_TIMEOUT)

    async def connect(self):
        if not self.session or self.session.closed:
            log.debug(f"Opening new HTTP Session to {self.base_url}")
            self.session = aiohttp.ClientSession(
                headers=APIDefaults.VERSION_HEADER, timeout=self.default_timeout
            )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
            log.debug("HTTP Session closed.")

    def _parse_opentrons_error(self, error_body: Union[Dict, str]) -> str:
        if isinstance(error_body, dict):
            if "errors" in error_body and isinstance(error_body["errors"], list):
                messages = []
                for err in error_body["errors"]:
                    title = err.get("title", "Error")
                    detail = err.get("detail", "")
                    msg = f"{title}: {detail}" if detail else title
                    messages.append(msg)
                return " | ".join(messages)
            if "message" in error_body:
                return str(error_body["message"])
            if "detail" in error_body:
                return str(error_body["detail"])
        return str(error_body)

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
        Core request handler with enhanced Opentrons error parsing.
        """
        await self.connect()
        url = f"{self.base_url}{path}"
        request_timeout = (
            aiohttp.ClientTimeout(total=timeout) if timeout else self.default_timeout
        )
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

                if resp.status == 503:
                    try:
                        text = await resp.text()
                    except Exception:
                        text = "Service Unavailable"
                    raise FlexMaintenanceError(f"System Busy (503): {text[:100]}")
                if resp.status >= 400:
                    try:
                        error_body = await resp.json()
                    except Exception:
                        error_body = await resp.text()

                    error_msg = self._parse_opentrons_error(error_body)
                    log.error(
                        f"API Error {resp.status} on {method} {path}: {error_msg}"
                    )
                    if resp.status == 409:
                        raise FlexConflictError(f"Conflict (409): {error_msg}")
                    if resp.status == 404:
                        raise FlexNotFoundError(f"Not Found (404): {error_msg}")
                    raise FlexCommandError(f"HTTP {resp.status}: {error_msg}")

                if resp.status == 204:
                    return None

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

    async def get_raw(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> bytes:
        await self.connect()
        url = f"{self.base_url}{path}"

        try:
            async with self.session.get(
                url,
                params=params,
                headers=APIDefaults.VERSION_HEADER,
                timeout=self.default_timeout,
            ) as resp:

                if resp.status >= 400:
                    try:
                        error_body = await resp.json()
                    except:
                        error_body = await resp.text()

                    error_msg = self._parse_opentrons_error(error_body)
                    raise FlexCommandError(
                        f"Download Failed ({resp.status}): {error_msg}"
                    )
                return await resp.read()

        except aiohttp.ClientError as e:
            raise FlexConnectionError(f"Raw download failed: {e}") from e

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
