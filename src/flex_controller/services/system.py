import asyncio
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ..client import FlexHTTPClient
from ..constants import Endpoints
from ..schemas import (
    DoorStatusResponse,
    EapConfig,
    EstopState,
    EstopStatusResponse,
    LogIdentifier,
    RobotHealth,
    SecurityType,
    SystemTime,
    WifiNetwork,
)

# Logging import
try:
    from src.common.log import get_logger

    log = get_logger("OpentronsFlex")
except ImportError:
    import logging

    log = logging.getLogger("OpentronsFlex")


class SystemService:
    """
    Manages System-level operations:
    - Health & Connection Status
    - Safety (E-Stop, Door)
    - Networking (Wi-Fi, Ethernet)
    - Time Synchronization
    - Logs & Diagnostics
    - Volatile Memory (Client Data)
    """

    def __init__(self, client: FlexHTTPClient):
        self.client = client

    # ============================================================================
    #                             HEALTH & CONNECTION
    # ============================================================================

    async def get_health(self) -> RobotHealth:
        """
        GET /health
        Get comprehensive information about the robot's software and hardware status.
        """
        data = await self.client.get(Endpoints.HEALTH)
        return RobotHealth(**data)

    async def wait_for_ready(self, timeout: int = 60) -> RobotHealth:
        """
        Helper: Polls /health until the robot returns 200 OK (Motors Ready).
        Useful to call after a reboot or update.
        """
        import time

        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                # The client handles 503 by raising FlexMaintenanceError
                # We catch that inside the loop to keep waiting
                health = await self.get_health()
                log.info(f"Robot '{health.name}' is ready. FW: {health.fw_version}")
                return health
            except Exception as e:
                # 503 comes as FlexMaintenanceError, connection refused as FlexConnectionError
                log.debug(f"Waiting for robot... ({e})")

            await asyncio.sleep(2)

        raise TimeoutError(f"Robot did not become ready within {timeout} seconds.")

    # ============================================================================
    #                             SAFETY (E-STOP & DOOR)
    # ============================================================================

    async def get_estop_status(self) -> EstopStatusResponse:
        """
        GET /robot/control/estopStatus
        Check the current state of the Emergency Stop system.
        """
        data = await self.client.get(Endpoints.ESTOP_STATUS)
        return EstopStatusResponse(**data["data"])

    async def acknowledge_estop_disengage(self) -> EstopStatusResponse:
        """
        PUT /robot/control/acknowledgeEstopDisengage
        Clears 'Logically Engaged' status after the button is physically released.
        """
        data = await self.client.put(Endpoints.ESTOP_ACK)
        status = EstopStatusResponse(**data["data"])

        if status.status == EstopState.DISENGAGED:
            log.info("E-Stop cleared. Robot is ready.")
        else:
            log.warning(
                f"E-Stop acknowledge sent, but status is still: {status.status}"
            )

        return status

    async def get_door_status(self) -> DoorStatusResponse:
        """
        GET /robot/door/status
        Check if the front door is open or closed.
        """
        data = await self.client.get(Endpoints.DOOR_STATUS)
        return DoorStatusResponse(**data["data"])

    # ============================================================================
    #                                  NETWORKING
    # ============================================================================

    async def get_network_status(self) -> Dict[str, Any]:
        """
        GET /networking/status
        """
        return await self.client.get(Endpoints.NETWORKING_STATUS)

    async def scan_wifi(self, rescan: bool = False) -> List[Dict[str, Any]]:
        """
        GET /wifi/list
        """
        params = {"rescan": "true"} if rescan else {}
        timeout = 20 if rescan else 5  # Increase timeout for hardware scan

        data = await self.client.get(
            Endpoints.WIFI_LIST, params=params, timeout=timeout
        )
        return data.get("list", [])

    async def configure_wifi(
        self,
        ssid: str,
        psk: Optional[str] = None,
        security_type: SecurityType = SecurityType.WPA_PSK,
        hidden: bool = False,
        eap_config: Optional[Union[Dict, EapConfig]] = None,
    ) -> Dict[str, Any]:
        """
        POST /wifi/configure
        """
        payload = {"ssid": ssid, "hidden": hidden, "securityType": security_type.value}

        if psk:
            payload["psk"] = psk

        if eap_config:
            if isinstance(eap_config, EapConfig):
                payload["eapConfig"] = eap_config.model_dump(exclude_none=True)
            else:
                payload["eapConfig"] = eap_config

        # Client handles 401/Errors
        response = await self.client.post(Endpoints.WIFI_CONFIGURE, json=payload)
        log.info(f"Successfully connected to Wi-Fi: {ssid}")
        return response

    async def disconnect_wifi(self, ssid: str):
        """
        POST /wifi/disconnect
        """
        payload = {"ssid": ssid}
        await self.client.post(Endpoints.WIFI_DISCONNECT, json=payload)
        log.info(f"Disconnected/Forgot network: {ssid}")

    async def get_wifi_keys(self) -> List[Dict[str, Any]]:
        """
        GET /wifi/keys
        """
        data = await self.client.get(Endpoints.WIFI_KEYS)
        return data.get("keys", [])

    async def add_wifi_key(
        self, file_path: str, filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        POST /wifi/keys
        """
        import os

        import aiohttp  # For FormData

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Key file not found: {file_path}")

        final_filename = filename or os.path.basename(file_path)
        data = aiohttp.FormData()
        data.add_field("key", open(file_path, "rb"), filename=final_filename)

        return await self.client.post(Endpoints.WIFI_KEYS, data=data)

    async def delete_wifi_key(self, key_uuid: str):
        """
        DELETE /wifi/keys/{uuid}
        """
        path = f"{Endpoints.WIFI_KEYS}/{key_uuid}"
        await self.client.delete(path)
        log.info(f"Deleted Wi-Fi key: {key_uuid}")

    # ============================================================================
    #                                SYSTEM TIME
    # ============================================================================

    async def get_system_time(self) -> SystemTime:
        """
        GET /system/time
        """
        data = await self.client.get(Endpoints.SYSTEM_TIME)
        return SystemTime(**data["data"])

    async def set_system_time(self, new_dt: datetime):
        """
        PUT /system/time
        """
        iso_time = new_dt.isoformat()
        payload = {"data": {"systemTime": iso_time}}

        await self.client.put(Endpoints.SYSTEM_TIME, json=payload)
        log.info(f"Robot system time updated to: {iso_time}")

    # ============================================================================
    #                           LOGGING & DIAGNOSTICS
    # ============================================================================

    async def get_logs(
        self, log_type: LogIdentifier, records: int = 500, fmt: str = "json"
    ) -> Any:
        """
        GET /logs/{log_identifier}
        """
        params = {"format": fmt, "records": records}

        path = Endpoints.LOGS_FETCH.format(log_type=log_type.value)
        return await self.client.get(path, params=params)

    async def ingest_robot_logs(self, log_type: LogIdentifier, records: int = 100):
        """
        Fetches logs from the robot and 're-logs' them into the local log system.
        """
        try:
            remote_logs = await self.get_logs(log_type, records=records, fmt="json")
        except Exception as e:
            log.error(f"Could not retrieve remote logs for ingestion: {e}")
            return

        # Bind a special logger tag
        robot_log = log.bind(tag="OpentronsFlex")
        count = 0

        for record in remote_logs:
            msg = record.get("message") or record.get("msg", "")
            level = record.get("levelname", "INFO")
            timestamp = record.get("created", None)

            time_str = ""
            if timestamp:
                dt = datetime.fromtimestamp(timestamp)
                time_str = f"[{dt.strftime('%H:%M:%S')}] "

            final_msg = f"({log_type.name}) {time_str}{msg}"

            if level == "ERROR":
                robot_log.error(final_msg)
            elif level == "WARNING":
                robot_log.warning(final_msg)
            elif level == "CRITICAL":
                robot_log.critical(final_msg)
            elif level == "DEBUG":
                robot_log.debug(final_msg)
            else:
                robot_log.info(final_msg)

            count += 1

        log.info(f"Successfully ingested {count} records from {log_type.value}")

    async def set_log_level(self, level: str):
        """
        POST /settings/log_level/local
        """
        valid_levels = ["debug", "info", "warning", "error"]
        if level.lower() not in valid_levels:
            raise ValueError(f"Invalid log level: {level}")

        payload = {"log_level": level.lower()}
        await self.client.post(Endpoints.LOG_LEVEL_LOCAL, json=payload)
        log.info(f"Robot local log level set to: {level}")

    # ============================================================================
    #                          CLIENT DATA (SHARED MEMORY)
    # ============================================================================

    def _validate_client_key(self, key: str):
        if not re.match(r"^[a-zA-Z0-9-_]+$", key):
            raise ValueError(
                f"Invalid Client Data Key: '{key}'. Must be alphanumeric, '-', or '_'."
            )

    async def set_client_data(self, key: str, data: Dict[str, Any]):
        """
        PUT /clientData/{key}
        Store arbitrary JSON data (cleared on reboot).
        """
        self._validate_client_key(key)
        payload = {"data": data}

        path = f"{Endpoints.CLIENT_DATA}/{key}"
        await self.client.put(path, json=payload)
        log.debug(f"Stored client data at key: {key}")

    async def get_client_data(self, key: str) -> Optional[Dict[str, Any]]:
        """
        GET /clientData/{key}
        """
        self._validate_client_key(key)
        path = f"{Endpoints.CLIENT_DATA}/{key}"

        try:
            data = await self.client.get(path)
            return data.get("data", {})
        except Exception:
            # Client usually raises 404/500 errors.
            # If 404, we return None.
            # Assuming client.get would raise an exception for 404.
            # We need to rely on the Client implementation for handling 404 gracefully or catch here.
            # Based on previous client implementation, it might raise FlexCommandError(HTTP 404).
            return None

    async def delete_client_data(self, key: str):
        """
        DELETE /clientData/{key}
        """
        self._validate_client_key(key)
        path = f"{Endpoints.CLIENT_DATA}/{key}"
        try:
            await self.client.delete(path)
            log.debug(f"Deleted client data key: {key}")
        except Exception:
            pass  # 404 means it's already gone

    async def clear_all_client_data(self):
        """
        DELETE /clientData
        """
        await self.client.delete(Endpoints.CLIENT_DATA)
        log.warning("All Client Data on robot has been wiped.")
