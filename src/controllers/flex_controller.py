import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp
from pydantic import BaseModel

# Logging import
try:
    from flex_serial_controls.log import get_tagged_logger

    log = get_tagged_logger("FlexAPI")
except ImportError:
    import logging

    log = logging.getLogger("FlexAPI")
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import aiohttp
from pydantic import BaseModel, Field


class RobotHealth(BaseModel):
    name: str
    robot_model: str
    api_version: str
    fw_version: str
    board_revision: str
    logs: List[str]
    system_version: str
    maximum_protocol_api_version: List[int]
    minimum_protocol_api_version: List[int]
    robot_serial: Optional[str] = Field(default=None)
    links: Dict[str, Any]


# --- Motor Status Models ---
class LogIdentifier(str, Enum):
    API = "api.log"
    SERIAL = "serial.log"
    CAN_BUS = "can_bus.log"
    SERVER = "server.log"
    COMBINED = "combined_api_server.log"
    UPDATE = "update_server.log"
    TOUCHSCREEN = "touchscreen.log"


class EngagedMotor(BaseModel):
    enabled: bool


class MotorsStatusResponse(BaseModel):
    """
    Represents the power state of the Flex's gantry and instrument motors.
    """

    x: EngagedMotor
    y: EngagedMotor
    z_l: EngagedMotor  # Z-stage Left
    z_r: EngagedMotor  # Z-stage Right
    p_l: EngagedMotor  # Pipette Plunger Left
    p_r: EngagedMotor  # Pipette Plunger Right
    q: Optional[EngagedMotor] = None  # Often associated with Gripper Jaws
    g: Optional[EngagedMotor] = None  # Often associated with Gripper Mount


# --- Pipette Data Models (Legacy/Compat) ---


class PipetteModelSpecs(BaseModel):
    displayName: Optional[str] = None
    name: Optional[str] = None
    minVolume: Optional[float] = None
    maxVolume: Optional[float] = None
    channels: Optional[int] = None


class AttachedPipette(BaseModel):
    """
    Represents a pipette attached to the robot (OT-2 Style Response).
    """

    id: Optional[str] = None  # The Pipette ID
    name: Optional[str] = None
    model: Optional[str] = None
    backCompatNames: List[str] = Field(default_factory=list)
    tip_length: Optional[float] = Field(None, alias="tipLength")
    mount_axis: Optional[str] = Field(None, alias="mountAxis")
    plunger_axis: Optional[str] = Field(None, alias="plungerAxis")
    modelSpecs: Optional[PipetteModelSpecs] = None


class PipettesResponse(BaseModel):
    left: Optional[AttachedPipette] = Field(default=None)
    right: Optional[AttachedPipette] = Field(default=None)


# --- Calibration Data Models ---


class CalibrationStatus(BaseModel):
    """
    Shared status model for deck and instrument calibration.
    Based on the 'robot_server__service__shared_models__calibration__CalibrationStatus' schema.
    """

    markedBad: bool = False
    source: Optional[str] = None
    markedAt: Optional[str] = None


class DeckCalibrationStatus(BaseModel):
    status: Union[CalibrationStatus, str, Dict[str, Any]]
    data: Optional[Dict[str, Any]] = None


# --- Pipette Data Models (Legacy/Compat) ---


class PipetteModelSpecs(BaseModel):
    displayName: Optional[str] = None
    name: Optional[str] = None
    minVolume: Optional[float] = None
    maxVolume: Optional[float] = None
    channels: Optional[int] = None


class AttachedPipette(BaseModel):
    """
    Represents a pipette attached to the robot (OT-2 Style Response).
    """

    id: Optional[str] = None  # The Pipette ID
    name: Optional[str] = None
    model: Optional[str] = None
    backCompatNames: List[str] = Field(default_factory=list)
    tip_length: Optional[float] = Field(None, alias="tipLength")
    mount_axis: Optional[str] = Field(None, alias="mountAxis")
    plunger_axis: Optional[str] = Field(None, alias="plungerAxis")
    modelSpecs: Optional[PipetteModelSpecs] = None


class PipettesResponse(BaseModel):
    left: Optional[AttachedPipette] = Field(default=None)
    right: Optional[AttachedPipette] = Field(default=None)


class InstrumentCalibrationStatus(BaseModel):
    # This is often a dictionary mapping mount/instrument IDs to their status
    right: Optional[CalibrationStatus] = None
    left: Optional[CalibrationStatus] = None
    gripper: Optional[CalibrationStatus] = None


class SystemCalibrationResponse(BaseModel):
    deckCalibration: DeckCalibrationStatus
    instrumentCalibration: InstrumentCalibrationStatus


# --- Networking Data Models ---


class SecurityType(str, Enum):
    WPA_PSK = "wpa-psk"
    WPA_EAP = "wpa-eap"
    NONE = "none"


class WifiNetwork(BaseModel):
    ssid: str
    signal: Optional[int] = None
    active: bool = False
    security: str
    securityType: Optional[str] = None


class EapConfig(BaseModel):
    """Configuration for Enterprise Wi-Fi (802.1x)."""

    eapType: str  # e.g., "peap", "tls", "ttls"
    identity: Optional[str] = None
    password: Optional[str] = None
    anonymousIdentity: Optional[str] = None
    caCert: Optional[str] = None
    clientCert: Optional[str] = None
    privateKey: Optional[str] = None
    phase2Auth: Optional[str] = None


# --- Exceptions ---
class FlexConnectionError(Exception):
    pass


class FlexCommandError(Exception):
    pass


# --- Data Models ---
class RunInfo(BaseModel):
    id: str
    status: str
    current: bool


class InstrumentInfo(BaseModel):
    mount: str
    instrumentType: str
    instrumentModel: str
    serialNumber: str
    ok: bool


# --- Singleton Controller ---


class FlexController:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """
        The Core Singleton Logic.
        If an instance already exists, return it.
        If not, create it.
        """
        if cls._instance is None:
            log.debug("Creating new FlexController Singleton instance.")
            cls._instance = super(FlexController, cls).__new__(cls)
        else:
            log.debug("Returning existing FlexController Singleton instance.")
        return cls._instance

    def __init__(self, robot_ip: str = None, port: int = 31950):
        """
        Initializes the controller.
        Note: Checks `self._initialized` to prevent re-running setup logic
        on subsequent calls.
        """
        if self._initialized:
            # Optional: Warning if someone tries to re-init with different IP
            if robot_ip and robot_ip != self._robot_ip:
                log.warning(
                    f"Ignored request to change Flex IP to {robot_ip}. Singleton already bound to {self._robot_ip}."
                )
            return

        # --- Initialization Logic (Runs Once) ---
        if not robot_ip:
            raise ValueError(
                "FlexController requires a robot_ip for the first initialization."
            )

        self._robot_ip = robot_ip
        self.base_url = f"http://{robot_ip}:{port}"
        self.headers = {"Opentrons-Version": "*", "Content-Type": "application/json"}
        self.session: Optional[aiohttp.ClientSession] = None
        self.current_run_id: Optional[str] = None

        # Mark as initialized so __init__ is skipped next time
        self._initialized = True
        log.info(f"FlexController initialized for robot at {self.base_url}")

    @classmethod
    def get_instance(cls) -> "FlexController":
        """
        Helper to retrieve the instance without passing arguments.
        Raises error if not initialized yet.
        """
        if cls._instance is None:
            raise RuntimeError(
                "FlexController has not been initialized. Call FlexController(ip) first."
            )
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """
        FOR TESTING ONLY: Destroys the singleton instance.
        """
        cls._instance = None
        cls._initialized = False

    # --- Connection Management ---

    async def connect(self):
        """Initializes the HTTP session and checks robot health."""
        if self.session and not self.session.closed:
            return  # Already connected

        self.session = aiohttp.ClientSession(headers=self.headers)
        try:
            async with self.session.get(f"{self.base_url}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    log.info(f"Connected to Flex: {data.get('name', 'Unknown')}")
                else:
                    raise FlexConnectionError(f"Health check failed: {resp.status}")
        except aiohttp.ClientError as e:
            raise FlexConnectionError(f"Could not connect to {self.base_url}") from e

    async def disconnect(self):
        """Closes the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
            log.info("Disconnected from Flex.")

    # --- Run & Command Logic (Same as before) ---

    async def create_run(self) -> str:
        async with self.session.get(f"{self.base_url}/runs") as resp:
            runs_data = await resp.json()
            for run in runs_data.get("data", []):
                if run.get("current") is True:
                    self.current_run_id = run["id"]
                    return self.current_run_id

        async with self.session.post(
            f"{self.base_url}/runs", json={"data": {}}
        ) as resp:
            if resp.status != 201:
                error = await resp.text()
                raise FlexCommandError(f"Failed to create run: {error}")
            data = await resp.json()
            self.current_run_id = data["data"]["id"]
            return self.current_run_id

    async def execute_command(
        self, command_type: str, params: Dict[str, Any], wait: bool = True
    ) -> Dict[str, Any]:
        if not self.current_run_id:
            await self.create_run()

        url = f"{self.base_url}/runs/{self.current_run_id}/commands"
        payload = {
            "data": {"commandType": command_type, "params": params, "intent": "setup"}
        }
        params_qs = {"waitUntilComplete": "true"} if wait else {}

        async with self.session.post(url, json=payload, params=params_qs) as resp:
            response_data = await resp.json()
            if resp.status != 201:
                raise FlexCommandError(f"HTTP Error: {await resp.text()}")

            result_data = response_data.get("data", {})
            if result_data.get("status") == "failed":
                error_detail = result_data.get("error", {}).get(
                    "detail", "Unknown Error"
                )
                raise FlexCommandError(error_detail)

            return result_data

    # --- Networking & Wi-Fi Management ---

    async def get_network_status(self) -> Dict[str, Any]:
        """
        GET /networking/status
        Query the current network connectivity state (Ethernet and Wi-Fi).
        """
        async with self.session.get(f"{self.base_url}/networking/status") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get network status: {resp.status}")
            return await resp.json()

    async def scan_wifi(self, rescan: bool = False) -> List[Dict[str, Any]]:
        """
        GET /wifi/list
        Returns a list of visible Wi-Fi networks.

        Args:
            rescan: If True, forces a hardware rescan (approx 10 seconds).
                    If False, returns cached results immediately.
        """
        params = {"rescan": "true"} if rescan else {}

        # Increase timeout for rescan as it is an "expensive operation"
        timeout = (
            aiohttp.ClientTimeout(total=20)
            if rescan
            else aiohttp.ClientTimeout(total=5)
        )

        try:
            async with self.session.get(
                f"{self.base_url}/wifi/list", params=params, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    raise FlexCommandError(f"Failed to scan wifi: {resp.status}")
                data = await resp.json()
                return data.get("list", [])
        except asyncio.TimeoutError:
            raise FlexCommandError("Wi-Fi scan timed out.")

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
        Connects the robot to a specific Wi-Fi network.
        """
        payload = {"ssid": ssid, "hidden": hidden, "securityType": security_type.value}

        if psk:
            payload["psk"] = psk

        if eap_config:
            if isinstance(eap_config, EapConfig):
                payload["eapConfig"] = eap_config.model_dump(exclude_none=True)
            else:
                payload["eapConfig"] = eap_config

        async with self.session.post(
            f"{self.base_url}/wifi/configure", json=payload
        ) as resp:
            if resp.status == 201:
                log.info(f"Successfully connected to Wi-Fi: {ssid}")
                return await resp.json()
            elif resp.status == 401:
                raise FlexCommandError(
                    "Wi-Fi Unauthorized: Incorrect password or credentials."
                )
            else:
                raise FlexCommandError(
                    f"Failed to configure Wi-Fi ({resp.status}): {await resp.text()}"
                )

    async def disconnect_wifi(self, ssid: str):
        """
        POST /wifi/disconnect
        Deactivates the Wi-Fi connection and removes it from known connections.
        """
        payload = {"ssid": ssid}
        # Note: The API path usually implied is /wifi/disconnect based on standard OT logic
        async with self.session.post(
            f"{self.base_url}/wifi/disconnect", json=payload
        ) as resp:
            if resp.status not in [200, 207]:
                raise FlexCommandError(f"Failed to disconnect Wi-Fi: {resp.status}")
            log.info(f"Disconnected/Forgot network: {ssid}")

    # --- Wi-Fi Key Management ---

    async def get_wifi_keys(self) -> List[Dict[str, Any]]:
        """
        GET /wifi/keys
        Get a list of key files known to the system.
        """
        async with self.session.get(f"{self.base_url}/wifi/keys") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to fetch keys: {resp.status}")
            data = await resp.json()
            return data.get("keys", [])

    async def add_wifi_key(
        self, file_path: str, filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        POST /wifi/keys
        Uploads a certificate/key file (e.g., for EAP auth) via multipart/form-data.
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Key file not found: {file_path}")

        final_filename = filename or os.path.basename(file_path)

        # Prepare Multipart upload
        data = aiohttp.FormData()
        data.add_field("key", open(file_path, "rb"), filename=final_filename)

        async with self.session.post(f"{self.base_url}/wifi/keys", data=data) as resp:
            if resp.status in [200, 201]:
                return await resp.json()
            else:
                raise FlexCommandError(
                    f"Failed to upload key ({resp.status}): {await resp.text()}"
                )

    async def delete_wifi_key(self, key_uuid: str):
        """
        DELETE /wifi/keys/{key_uuid}
        Delete a key file from the robot.
        """
        async with self.session.delete(f"{self.base_url}/wifi/keys/{key_uuid}") as resp:
            if resp.status != 200:
                # 404 handled here generically or could be specific
                raise FlexCommandError(
                    f"Failed to delete key {key_uuid}: {resp.status}"
                )
            log.info(f"Deleted Wi-Fi key: {key_uuid}")

    async def get_eap_options(self) -> List[Dict[str, Any]]:
        """
        GET /wifi/eap-options
        Get the supported EAP variants and their configuration parameters.
        """
        async with self.session.get(f"{self.base_url}/wifi/eap-options") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get EAP options: {resp.status}")
            data = await resp.json()
            return data.get("options", [])

    # --- Robot Controls (Lights & Identification) ---

    async def identify(self, seconds: int = 10):
        """
        POST /identify
        Blink the gantry lights so you can pick the robot out of a crowd.

        Args:
            seconds: Duration to blink the lights (default 10s).
        """
        params = {"seconds": seconds}
        async with self.session.post(
            f"{self.base_url}/identify", params=params
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to identify robot: {resp.status}")
            log.info(f"Robot identifying (blinking) for {seconds} seconds.")

    async def get_lights_status(self) -> bool:
        """
        GET /robot/lights
        Returns True if the rail lights are currently ON.
        """
        async with self.session.get(f"{self.base_url}/robot/lights") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get light status: {resp.status}")
            data = await resp.json()
            return data.get("on", False)

    async def set_lights(self, on: bool = True):
        """
        POST /robot/lights
        Turn the rail lights on or off.
        """
        payload = {"on": on}
        async with self.session.post(
            f"{self.base_url}/robot/lights", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to set lights: {resp.status}")
            data = await resp.json()
            state = "ON" if data.get("on") else "OFF"
            log.info(f"Robot lights turned {state}")

    # --- Advanced Settings (Feature Flags) ---

    async def get_settings(self) -> List[Dict[str, Any]]:
        """
        GET /settings
        Returns the list of advanced settings (feature flags).
        """
        async with self.session.get(f"{self.base_url}/settings") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get settings: {resp.status}")
            data = await resp.json()
            return data.get("settings", [])

    # --- System Settings & Logs ---

    async def set_log_level(self, level: str):
        """
        POST /settings/log_level/local
        Set the minimum level of logs saved locally on the robot.

        Args:
            level: One of "debug", "info", "warning", "error".
        """
        valid_levels = ["debug", "info", "warning", "error"]
        if level.lower() not in valid_levels:
            raise ValueError(
                f"Invalid log level: {level}. Must be one of {valid_levels}"
            )

        payload = {"log_level": level.lower()}

        async with self.session.post(
            f"{self.base_url}/settings/log_level/local", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to set log level: {resp.status}")
            log.info(f"Robot local log level set to: {level}")

    async def get_robot_settings(self) -> Dict[str, Any]:
        """
        GET /settings/robot
        Get the current robot configuration/settings.
        """
        async with self.session.get(f"{self.base_url}/settings/robot") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get robot config: {resp.status}")
            return await resp.json()

    # --- Factory Reset & Data Management ---

    async def get_reset_options(self) -> List[Dict[str, Any]]:
        """
        GET /settings/reset/options
        Get the list of settings and data that can be wiped/reset.
        (e.g., 'bootScripts', 'deckCalibration', 'pipetteOffsetCalibrations')
        """
        async with self.session.get(f"{self.base_url}/settings/reset/options") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to fetch reset options: {resp.status}")
            data = await resp.json()
            return data.get("options", [])

    async def reset_data(self, options: Dict[str, bool]):
        """
        POST /settings/reset
        Perform a factory reset of specific data categories.

        WARNING: This requires a robot restart to take effect.

        Args:
            options: A dictionary mapping reset IDs to True.
                     Example: {"deckCalibration": True, "pipetteOffsetCalibrations": True}
        """
        # 1. Validate inputs against available options to prevent bad requests
        available_opts = await self.get_reset_options()
        valid_keys = {opt["id"] for opt in available_opts}

        payload = {}
        for key, should_reset in options.items():
            if key not in valid_keys:
                log.warning(f"Skipping unknown reset key: {key}")
                continue
            if should_reset:
                payload[key] = True

        if not payload:
            log.warning("No valid reset options provided. Aborting reset.")
            return

        # 2. Send Reset Command
        async with self.session.post(
            f"{self.base_url}/settings/reset", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Reset failed ({resp.status}): {await resp.text()}"
                )

            log.warning(f"Reset command successful for: {list(payload.keys())}")
            log.critical("ROBOT MUST BE RESTARTED FOR RESET TO TAKE EFFECT.")

    # --- Enhanced Feature Flag (Update existing method) ---

    async def update_setting(self, setting_id: str, value: Optional[bool]) -> bool:
        """
        POST /settings
        Change an advanced setting (feature flag).

        Returns:
            bool: True if the robot requires a restart to apply this setting.
        """
        payload = {"id": setting_id, "value": value}
        async with self.session.post(f"{self.base_url}/settings", json=payload) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to update setting {setting_id}: {resp.status}"
                )

            response_data = await resp.json()

            # Check for restart link in response
            # Response structure: { "settings": [...], "links": { "restart": "/server/restart" } }
            links = response_data.get("links", {})
            needs_restart = "restart" in links

            log.info(f"Updated Feature Flag: {setting_id} -> {value}")
            if needs_restart:
                log.warning("This setting change requires a robot restart.")

            return needs_restart

    async def get_calibration_status(self) -> SystemCalibrationResponse:
        """
        GET /calibration/status
        Get the high-level calibration status of the deck and attached instruments.
        Useful for checking if the robot requires attention before starting a run.
        """
        async with self.session.get(f"{self.base_url}/calibration/status") as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to get calibration status: {resp.status}"
                )

            data = await resp.json()
            return SystemCalibrationResponse(**data)

    async def get_modules(self) -> List[Dict[str, Any]]:
        """
        GET /modules
        List all attached modules (Magnetic, Temperature, Thermocycler, HeaterShaker).
        Useful for getting the 'id' (serial) required for commands.
        """
        async with self.session.get(f"{self.base_url}/modules") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get modules: {resp.status}")

            data = await resp.json()
            return data.get("modules", [])

    async def update_module_firmware(self, serial: str):
        """
        POST /modules/{serial}/update
        Command the robot to flash its bundled firmware file to this specific module.

        Args:
            serial: The serial number/ID of the module (from get_modules).
        """
        async with self.session.post(
            f"{self.base_url}/modules/{serial}/update"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Module update failed ({resp.status}): {await resp.text()}"
                )

            log.info(f"Initiated firmware update for module {serial}")
            # Note: The API might return immediately, but the update takes time.

    async def send_module_command(
        self, module_id: str, command_name: str, params: Dict[str, Any] = None
    ):
        """
        Helper wrapper for controlling modules via Protocol Engine.
        Replaces the deprecated POST /modules/{serial} endpoint.

        Example:
            send_module_command("heater_shaker_id", "heaterShaker/openLabwareLatch")
        """
        if params is None:
            params = {}

        # Inject the moduleId into params as required by Protocol Engine
        params["moduleId"] = module_id

        # Use the existing execute_command method
        await self.execute_command(command_name, params)

    # --- Pipettes (Legacy View) ---

    async def get_pipettes_legacy(self) -> Dict[str, Any]:
        """
        GET /pipettes
        Get the pipettes currently attached (Legacy OT-2 format).

        WARNING: 'refresh' is forced to False. Actively scanning for pipettes
        on the Flex is undefined behavior and can disable motors.
        """
        # We explicitly enforce refresh=false for Flex safety
        params = {"refresh": "false"}

        async with self.session.get(f"{self.base_url}/pipettes", params=params) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get pipettes: {resp.status}")

            # Returns { "left": {...}, "right": {...} }
            return await resp.json()

    async def get_pipettes(self) -> PipettesResponse:
        """
        GET /pipettes
        Get the pipettes currently attached.

        NOTE: On the Flex, the `/instruments` endpoint is preferred.
        This endpoint is provided for compatibility.

        CRITICAL: This method forces 'refresh=False'. Actively scanning for
        pipettes (refresh=True) is not supported on Flex and can disable motors.
        """
        params = {"refresh": "false"}

        async with self.session.get(f"{self.base_url}/pipettes", params=params) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get pipettes: {resp.status}")

            data = await resp.json()
            # The API returns { "left": {...}, "right": {...} }
            return PipettesResponse(**data)

    # --- Motor Controls ---

    async def get_engaged_motors(self) -> MotorsStatusResponse:
        """
        GET /motors/engaged
        Query which motors are currently powered and holding position.
        """
        async with self.session.get(f"{self.base_url}/motors/engaged") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get motor status: {resp.status}")

            data = await resp.json()
            return MotorsStatusResponse(**data)

    async def disengage_motors(self, axes: List[str]):
        """
        POST /motors/disengaged
        Cut power to specific motors, allowing them to be moved manually.

        Args:
            axes: List of axis names to disengage.
                  Valid Flex axes: ["x", "y", "z_l", "z_r", "p_l", "p_r", "q", "g"]
        """
        # Validate inputs roughly to help the user
        valid_axes = {
            "x",
            "y",
            "z_l",
            "z_r",
            "z_g",
            "p_l",
            "p_r",
            "q",
            "g",
            "z",
            "a",
            "b",
            "c",
        }
        cleaned_axes = [a.lower() for a in axes]

        if not all(a in valid_axes for a in cleaned_axes):
            log.warning(f"Request contains potentially invalid axis names: {axes}")

        payload = {"axes": cleaned_axes}

        # Note: The endpoint is /motors/disengaged (past tense) based on standard OT API conventions
        async with self.session.post(
            f"{self.base_url}/motors/disengaged", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to disengage motors: {resp.status}")

            log.info(f"Motors disengaged: {cleaned_axes}")

    async def get_logs(
        self, log_type: LogIdentifier, records: int = 500, fmt: str = "json"
    ) -> Any:
        """
        GET /logs/{log_identifier}
        Fetch raw logs from the robot.
        """
        params = {"format": fmt, "records": records}

        async with self.session.get(
            f"{self.base_url}/logs/{log_type.value}", params=params
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to fetch {log_type} logs: {resp.status}"
                )

            # Text format returns a huge string, JSON returns a list of dicts
            if fmt == "json":
                return await resp.json()
            else:
                return await resp.text()

    async def ingest_robot_logs(self, log_type: LogIdentifier, records: int = 100):
        """
        Fetches logs from the robot and 're-logs' them into the local NanovisFlux
        log system. This creates a unified timeline of Host + Robot events.

        Args:
            log_type: Which log file to fetch (e.g., LogIdentifier.API).
            records: Number of past records to ingest.
        """
        # 1. Fetch from Robot
        try:
            remote_logs = await self.get_logs(log_type, records=records, fmt="json")
        except FlexCommandError as e:
            log.error(f"Could not retrieve remote logs for ingestion: {e}")
            return

        # 2. Bind a special logger for these entries
        # We tag them as 'RobotRemote' so they are distinct in the file
        robot_log = log.bind(tag="OpentronsFlex")

        # 3. Iterate and Convert
        # Opentrons JSON logs usually follow standard Python logging record attributes
        count = 0
        for record in remote_logs:
            # Extract standard fields (with fallbacks)
            msg = record.get("message") or record.get("msg", "")
            level = record.get("levelname", "INFO")
            timestamp = record.get("created", None)

            # Format a time string if possible
            time_str = ""
            if timestamp:
                dt = datetime.fromtimestamp(timestamp)
                time_str = f"[{dt.strftime('%H:%M:%S')}] "

            # Construct the final message
            # We prepend the original timestamp because the local log will apply
            # the *current* ingestion time, which might differ.
            final_msg = f"({log_type.name}) {time_str}{msg}"

            # 4. Log using the local utility
            # Map string level to loguru function
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

    # --- Health & System Status ---

    async def get_health(self) -> RobotHealth:
        """
        GET /health
        Get comprehensive information about the robot's software and hardware status.

        Raises:
            FlexMaintenanceError: If status is 503 (Motor controller initializing).
            FlexCommandError: If status is 4xx/5xx (other errors).
        """
        async with self.session.get(f"{self.base_url}/health") as resp:
            # Handle the specific "Motor Controller Not Ready" state
            if resp.status == 503:
                error_data = await resp.json()
                msg = error_data.get("message", "Robot motor controller is not ready")
                raise FlexMaintenanceError(f"System Initializing (503): {msg}")

            if resp.status != 200:
                raise FlexCommandError(f"Health check failed: {resp.status}")

            data = await resp.json()
            return RobotHealth(**data)

    async def wait_for_ready(self, timeout: int = 60):
        """
        Helper: Polls /health until the robot returns 200 OK (Motors Ready).
        Useful to call after a reboot or update.
        """
        import time

        start_time = time.time()

        while (time.time() - start_time) < timeout:
            try:
                health = await self.get_health()
                log.info(f"Robot '{health.name}' is ready. FW: {health.fw_version}")
                return health
            except FlexMaintenanceError:
                log.debug("Waiting for motor controller initialization...")
            except Exception as e:
                log.warning(f"Waiting for connection... ({e})")

            await asyncio.sleep(2)

        raise TimeoutError(f"Robot did not become ready within {timeout} seconds.")
