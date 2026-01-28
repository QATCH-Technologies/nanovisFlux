import asyncio
import json
import re
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

from src.common.error import FlexCommandError, FlexConnectionError, FlexMaintenanceError

# --- Safety & Estop Models ---


class EstopState(str, Enum):
    NOT_PRESENT = "notPresent"  # No E-stop detected (rare on Flex)
    PHYSICALLY_ENGAGED = "physicallyEngaged"  # Button is currently pressed down
    LOGICALLY_ENGAGED = "logicallyEngaged"  # Button released, waiting for software ACK
    DISENGAGED = "disengaged"  # System is live and ready


class PhysicalEstopStatus(str, Enum):
    ENGAGED = "engaged"
    DISENGAGED = "disengaged"
    NOT_PRESENT = "notPresent"


class EstopStatusResponse(BaseModel):
    status: EstopState
    leftEstopPhysicalStatus: PhysicalEstopStatus
    rightEstopPhysicalStatus: PhysicalEstopStatus


class DoorState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class DoorStatusResponse(BaseModel):
    status: DoorState
    doorRequiredClosedForProtocol: bool
    moduleSerial: Optional[str] = None


# --- Subsystem & Firmware Models ---


class Subsystem(str, Enum):
    GANTRY_X = "gantry_x"
    GANTRY_Y = "gantry_y"
    HEAD = "head"
    PIPETTE_LEFT = "pipette_left"
    PIPETTE_RIGHT = "pipette_right"
    GRIPPER = "gripper"
    REAR_PANEL = "rear_panel"
    HEPA_UV = "hepa_uv"
    MOTOR_CONTROLLER = "motor_controller_board"


class SubsystemInfo(BaseModel):
    name: str
    ok: bool
    current_fw_version: str
    next_fw_version: Optional[str] = None
    fw_update_needed: bool
    revision: Optional[str] = None


class SubsystemUpdate(BaseModel):
    id: str
    createdAt: str
    subsystem: str
    updateStatus: str  # e.g., "queued", "updating", "done", "failed"
    updateProgress: int
    updateError: Optional[str] = None


# --- System Status Models ---


class SystemTime(BaseModel):
    systemTime: str  # ISO 8601 Format
    id: Optional[str] = None
    # Optional fields often present but not in strict schema samples
    timezone: Optional[str] = None
    synchronized: Optional[bool] = None  # NTP status


# --- Instrument Models ---


class InstrumentData(BaseModel):
    mount: str  # "left", "right", or "extension" (for Gripper)
    instrumentType: str  # "pipette" or "gripper"
    instrumentModel: str  # e.g. "p1000_single_gen3"
    serialNumber: str
    subsystem: Optional[str] = None  # e.g. "pipette_left"
    ok: bool  # True if communication is healthy
    firmwareVersion: Optional[str] = None
    data: Optional[Dict[str, Any]] = None  # Contains min/max volume for pipettes

    @property
    def is_gripper(self) -> bool:
        return self.instrumentType == "gripper"

    @property
    def is_pipette(self) -> bool:
        return self.instrumentType == "pipette"


# --- Error Recovery Models ---


class ErrorRecoverySettings(BaseModel):
    enabled: bool


# --- Flex Deck Configuration Models ---


class CutoutFixture(BaseModel):
    """
    Maps a physical cutout slot on the Flex frame to a fixture.
    Example: cutoutId="cutoutD3", cutoutFixtureId="wasteChuteRightAdapterNoCover"
    """

    cutoutId: str
    cutoutFixtureId: str


class DeckConfiguration(BaseModel):
    cutoutFixtures: List[CutoutFixture]
    lastModifiedAt: Optional[str] = None


# --- Protocol & Analysis Models ---


class ProtocolAnalysisStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ProtocolAnalysis(BaseModel):
    id: str
    status: ProtocolAnalysisStatus
    result: Optional[str] = None  # simplified, often contains a huge list of commands
    errors: List[Dict[str, Any]] = []


class ProtocolData(BaseModel):
    id: str
    createdAt: str
    protocolType: str  # "python" or "json"
    robotType: str  # "OT-2 Standard" or "OT-3 Standard"
    metadata: Dict[str, Any]
    analyses: List[ProtocolAnalysis] = []
    key: Optional[str] = None
    protocolKind: str = "standard"


class DataFile(BaseModel):
    id: str
    name: str
    source: str  # "uploaded"
    createdAt: str


# --- Run Management Models ---


class RunStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AWAITING_RECOVERY = "awaiting-recovery"


class RunActionType(str, Enum):
    PLAY = "play"
    PAUSE = "pause"
    STOP = "stop"
    RESUME_FROM_RECOVERY = "resume-from-recovery"


class RunData(BaseModel):
    id: str
    status: RunStatus
    current: bool
    createdAt: str
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    protocolId: Optional[str] = None
    errors: List[Dict[str, Any]] = []


class RunCommandSummary(BaseModel):
    id: str
    commandType: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


# --- Labware Offset Models ---


class OffsetVector(BaseModel):
    x: float
    y: float
    z: float


class LabwareOffset(BaseModel):
    id: str
    createdAt: str
    definitionUri: str
    locationSequence: List[Dict[str, Any]]
    vector: OffsetVector


class LabwareOffsetFilter(BaseModel):
    """
    Criteria for searching offsets.
    Common filters: definitionUri, locationSequence.
    """

    definitionUri: Optional[str] = None
    locationSequence: Optional[List[Dict[str, Any]]] = None


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
        self.current_maintenance_run_id: Optional[str] = None
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

    # --- Client Data (Shared Volatile Memory) ---

    def _validate_client_key(self, key: str):
        """
        Internal helper to enforce API key constraints: ^[a-zA-Z0-9-_]+$
        """
        if not re.match(r"^[a-zA-Z0-9-_]+$", key):
            raise ValueError(
                f"Invalid Client Data Key: '{key}'. Must be alphanumeric, '-', or '_'."
            )

    async def set_client_data(self, key: str, data: Dict[str, Any]):
        """
        PUT /clientData/{key}
        Store arbitrary JSON data on the robot.

        NOTE: Data is lost if the robot reboots.
        """
        self._validate_client_key(key)

        # The API expects the actual payload wrapped in a "data" key
        payload = {"data": data}

        async with self.session.put(
            f"{self.base_url}/clientData/{key}", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to store client data: {resp.status}")

            log.debug(f"Stored client data at key: {key}")

    async def get_client_data(self, key: str) -> Optional[Dict[str, Any]]:
        """
        GET /clientData/{key}
        Retrieve data stored at the specific key.
        Returns None if the key does not exist.
        """
        self._validate_client_key(key)

        async with self.session.get(f"{self.base_url}/clientData/{key}") as resp:
            if resp.status == 404:
                return None

            if resp.status != 200:
                raise FlexCommandError(f"Failed to retrieve client data: {resp.status}")

            response_json = await resp.json()
            # Unwrap the response to return just the user's data object
            return response_json.get("data", {})

    async def delete_client_data(self, key: str):
        """
        DELETE /clientData/{key}
        Deletes the data at the specific key.
        """
        self._validate_client_key(key)

        async with self.session.delete(f"{self.base_url}/clientData/{key}") as resp:
            if resp.status == 404:
                log.warning(f"Attempted to delete non-existent key: {key}")
                return

            if resp.status != 200:
                raise FlexCommandError(f"Failed to delete client data: {resp.status}")

            log.debug(f"Deleted client data key: {key}")

    async def clear_all_client_data(self):
        """
        DELETE /clientData
        Wipes ALL client data stored on the robot.
        Use with caution if multiple clients are accessing the robot.
        """
        async with self.session.delete(f"{self.base_url}/clientData") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to clear all data: {resp.status}")
            log.warning("All Client Data on robot has been wiped.")

    # --- Labware Offsets ---

    async def add_labware_offset(
        self,
        definition_uri: str,
        location_sequence: List[Dict[str, Any]],
        vector: Dict[str, float],
    ) -> LabwareOffset:
        """
        POST /labwareOffsets
        Store a new labware offset.

        Args:
            definition_uri: The unique URI of the labware (e.g., "opentrons/opentrons_96_tiprack_300ul/1").
            location_sequence: Ordered list describing where the labware is (Slot -> Module -> Adapter).
            vector: Dictionary containing {"x": float, "y": float, "z": float}.

        Returns:
            The created LabwareOffset object including its new ID.
        """
        payload = {
            "data": {
                "definitionUri": definition_uri,
                "locationSequence": location_sequence,
                "vector": vector,
            }
        }

        async with self.session.post(
            f"{self.base_url}/labwareOffsets", json=payload
        ) as resp:
            if resp.status != 201:
                raise FlexCommandError(
                    f"Failed to add offset: {resp.status} - {await resp.text()}"
                )

            response_data = await resp.json()
            return LabwareOffset(**response_data["data"])

    async def get_labware_offsets(
        self, limit: str = "unlimited"
    ) -> List[LabwareOffset]:
        """
        GET /labwareOffsets
        Get all stored offsets, ordered oldest to newest.
        """
        params = {"pageLength": limit}
        async with self.session.get(
            f"{self.base_url}/labwareOffsets", params=params
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to fetch offsets: {resp.status}")

            data = await resp.json()
            return [LabwareOffset(**item) for item in data.get("data", [])]

    async def search_labware_offsets(
        self, filters: List[Dict[str, Any]]
    ) -> List[LabwareOffset]:
        """
        POST /labwareOffsets/searches
        Search for offsets matching specific criteria.

        Args:
            filters: A list of dictionary filters (e.g. matching a specific definitionUri).
        """
        payload = {"data": {"filters": filters}}

        async with self.session.post(
            f"{self.base_url}/labwareOffsets/searches", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Offset search failed: {resp.status}")

            data = await resp.json()
            return [LabwareOffset(**item) for item in data.get("data", [])]

    async def delete_labware_offset(self, offset_id: str):
        """
        DELETE /labwareOffsets/{id}
        Delete a single offset by ID.
        """
        async with self.session.delete(
            f"{self.base_url}/labwareOffsets/{offset_id}"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to delete offset {offset_id}: {resp.status}"
                )
            log.info(f"Deleted offset: {offset_id}")

    async def clear_all_offsets(self):
        """
        DELETE /labwareOffsets
        Wipe ALL stored labware offsets from the robot.
        """
        async with self.session.delete(f"{self.base_url}/labwareOffsets") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to clear offsets: {resp.status}")
            log.warning("All labware offsets cleared.")

    # --- Run Management (Lifecycle) ---

    async def create_run(
        self,
        protocol_id: Optional[str] = None,
        labware_offsets: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        POST /runs
        Create a new run.

        Args:
            protocol_id: Optional ID if running a previously uploaded protocol file.
            labware_offsets: Optional list of offsets to apply immediately.
        """
        payload_data = {}
        if protocol_id:
            payload_data["protocolId"] = protocol_id
        if labware_offsets:
            payload_data["labwareOffsets"] = labware_offsets

        # If a run is already current and active, we might want to warn the user
        # But per standard logic, we usually just create a new one which becomes current.

        async with self.session.post(
            f"{self.base_url}/runs", json={"data": payload_data}
        ) as resp:
            if resp.status != 201:
                raise FlexCommandError(f"Failed to create run: {await resp.text()}")

            data = await resp.json()
            self.current_run_id = data["data"]["id"]
            log.info(f"Created new run: {self.current_run_id}")
            return self.current_run_id

    async def get_run(self, run_id: str) -> RunData:
        """
        GET /runs/{runId}
        Get details about a specific run.
        """
        async with self.session.get(f"{self.base_url}/runs/{run_id}") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get run {run_id}: {resp.status}")
            data = await resp.json()
            return RunData(**data["data"])

    async def get_all_runs(self, limit: int = 20) -> List[RunData]:
        """
        GET /runs
        Get a list of recent runs.
        """
        params = {"pageLength": limit}
        async with self.session.get(f"{self.base_url}/runs", params=params) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to list runs: {resp.status}")
            data = await resp.json()
            return [RunData(**item) for item in data.get("data", [])]

    async def delete_run(self, run_id: str):
        """
        DELETE /runs/{runId}
        Removes a run record.
        """
        async with self.session.delete(f"{self.base_url}/runs/{run_id}") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to delete run {run_id}: {resp.status}")

            if self.current_run_id == run_id:
                self.current_run_id = None
            log.debug(f"Deleted run: {run_id}")

    # --- Run Actions (Controls) ---

    async def send_run_action(self, action: RunActionType):
        """
        POST /runs/{runId}/actions
        Issue a control action (Play, Pause, Stop, Resume).
        """
        if not self.current_run_id:
            raise FlexCommandError("No active run to control.")

        payload = {"data": {"actionType": action.value}}

        async with self.session.post(
            f"{self.base_url}/runs/{self.current_run_id}/actions", json=payload
        ) as resp:
            if resp.status != 201:
                # 409 Conflict is common if you try to 'play' a run that is already running
                if resp.status == 409:
                    log.warning(f"Action {action.value} ignored: {await resp.text()}")
                    return
                raise FlexCommandError(
                    f"Failed to {action.value} run: {await resp.text()}"
                )

            log.info(f"Run Action Sent: {action.value}")

    async def play(self):
        """Start or Resume the current run."""
        await self.send_run_action(RunActionType.PLAY)

    async def pause(self):
        """Pause the current run."""
        await self.send_run_action(RunActionType.PAUSE)

    async def stop(self):
        """Stop the current run permanently."""
        await self.send_run_action(RunActionType.STOP)

    async def resume_from_recovery(self):
        """Confirm that a manual fix has been applied and resume execution."""
        await self.send_run_action(RunActionType.RESUME_FROM_RECOVERY)

    # --- Run Commands (Queue Management) ---

    async def execute_command(
        self,
        command_type: str,
        params: Dict[str, Any],
        wait: bool = True,
        intent: str = "setup",
    ) -> Dict[str, Any]:
        """
        POST /runs/{runId}/commands
        Enqueue a command.

        Args:
            intent: "setup" (runs immediately), "protocol" (waits for Play), "fixit" (error recovery).
        """
        if not self.current_run_id:
            await self.create_run()

        url = f"{self.base_url}/runs/{self.current_run_id}/commands"
        payload = {
            "data": {"commandType": command_type, "params": params, "intent": intent}
        }

        # If waiting, infinite timeout is safest for long physical moves
        params_qs = {"waitUntilComplete": "true", "timeout": "infinite"} if wait else {}

        async with self.session.post(url, json=payload, params=params_qs) as resp:
            if resp.status != 201:
                raise FlexCommandError(
                    f"Command failed HTTP ({resp.status}): {await resp.text()}"
                )

            response_data = await resp.json()
            result_data = response_data.get("data", {})

            # Check for Protocol Engine logic errors
            if result_data.get("status") == "failed":
                error_detail = result_data.get("error", {}).get(
                    "detail", "Unknown Error"
                )
                log.error(f"Command {command_type} FAILED: {error_detail}")
                raise FlexCommandError(error_detail)

            return result_data

    async def get_run_commands(self, run_id: str = None) -> List[RunCommandSummary]:
        """
        GET /runs/{runId}/commands
        Get the history of commands executed in a run.
        """
        target_id = run_id or self.current_run_id
        if not target_id:
            raise ValueError("No run specified.")

        async with self.session.get(
            f"{self.base_url}/runs/{target_id}/commands"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get commands: {resp.status}")
            data = await resp.json()
            return [RunCommandSummary(**item) for item in data.get("data", [])]

    async def get_run_errors(self, run_id: str = None) -> List[Dict[str, Any]]:
        """
        GET /runs/{runId}/commandErrors
        Get list of errors that occurred during the run.
        """
        target_id = run_id or self.current_run_id
        async with self.session.get(
            f"{self.base_url}/runs/{target_id}/commandErrors"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get errors: {resp.status}")
            data = await resp.json()
            return data.get("data", [])

    # --- Run Configuration ---

    async def add_run_labware_offset(self, offset: LabwareOffset):
        """
        POST /runs/{runId}/labware_offsets
        Apply a specific offset to the CURRENT run.
        """
        if not self.current_run_id:
            raise FlexCommandError("No active run.")

        # API expects the body to be the creation object, effectively re-submitting definition info
        # Simplification: We construct the payload manually to match LabwareOffsetCreate
        payload = {
            "data": {
                "definitionUri": offset.definitionUri,
                "locationSequence": offset.locationSequence,
                "vector": offset.vector.model_dump(),
            }
        }

        async with self.session.post(
            f"{self.base_url}/runs/{self.current_run_id}/labware_offsets", json=payload
        ) as resp:
            if resp.status != 201:
                raise FlexCommandError(f"Failed to add offset to run: {resp.status}")
            log.debug(f"Offset added to run {self.current_run_id}")

    # --- Maintenance Run Management ---

    async def create_maintenance_run(
        self, labware_offsets: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        POST /maintenance_runs
        Create a new maintenance run.

        Note: If a standard Protocol Run is currently 'running' or 'paused',
        this will raise a FlexCommandError (409 Conflict).
        """
        payload_data = {}
        if labware_offsets:
            payload_data["labwareOffsets"] = labware_offsets

        async with self.session.post(
            f"{self.base_url}/maintenance_runs", json={"data": payload_data}
        ) as resp:
            if resp.status == 409:
                raise FlexCommandError(
                    "Cannot create Maintenance Run: A Protocol Run is currently active."
                )

            if resp.status != 201:
                raise FlexCommandError(
                    f"Failed to create maintenance run: {await resp.text()}"
                )

            data = await resp.json()
            self.current_maintenance_run_id = data["data"]["id"]
            log.info(f"Created Maintenance Run: {self.current_maintenance_run_id}")
            return self.current_maintenance_run_id

    async def get_current_maintenance_run(self) -> Optional[RunData]:
        """
        GET /maintenance_runs/current_run
        Get the currently active maintenance run.
        """
        async with self.session.get(
            f"{self.base_url}/maintenance_runs/current_run"
        ) as resp:
            if resp.status == 404:
                return None

            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to get current maintenance run: {resp.status}"
                )

            data = await resp.json()
            # Reuse the RunData model from standard runs as the structure is identical
            run_data = RunData(**data["data"])
            self.current_maintenance_run_id = run_data.id
            return run_data

    async def delete_maintenance_run(self, run_id: str = None):
        """
        DELETE /maintenance_runs/{runId}
        """
        target_id = run_id or self.current_maintenance_run_id
        if not target_id:
            return

        async with self.session.delete(
            f"{self.base_url}/maintenance_runs/{target_id}"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to delete maintenance run: {resp.status}"
                )

            if self.current_maintenance_run_id == target_id:
                self.current_maintenance_run_id = None
            log.debug(f"Deleted maintenance run: {target_id}")

    # --- Maintenance Commands (Immediate Execution) ---

    async def execute_maintenance_command(
        self, command_type: str, params: Dict[str, Any], wait: bool = True
    ) -> Dict[str, Any]:
        """
        POST /maintenance_runs/{runId}/commands

        CRITICAL DIFFERENCE: These commands execute IMMEDIATELY upon receipt.
        There is no 'Queue' and no 'Play' button for maintenance runs.
        """
        if not self.current_maintenance_run_id:
            await self.create_maintenance_run()

        url = f"{self.base_url}/maintenance_runs/{self.current_maintenance_run_id}/commands"
        payload = {
            "data": {
                "commandType": command_type,
                "params": params,
                "intent": "setup",  # Maintenance commands are usually setup/fixit intent
            }
        }

        # Maintenance runs execute immediately, so we almost always want to wait for result
        params_qs = {"waitUntilComplete": "true", "timeout": "infinite"} if wait else {}

        async with self.session.post(url, json=payload, params=params_qs) as resp:
            if resp.status != 201:
                raise FlexCommandError(
                    f"Maintenance command failed ({resp.status}): {await resp.text()}"
                )

            response_data = await resp.json()
            result_data = response_data.get("data", {})

            if result_data.get("status") == "failed":
                error_detail = result_data.get("error", {}).get(
                    "detail", "Unknown Error"
                )
                log.error(f"Maintenance Command {command_type} FAILED: {error_detail}")
                raise FlexCommandError(error_detail)

            return result_data

    # --- Maintenance Configuration ---

    async def add_maintenance_labware_offset(self, offset: LabwareOffset):
        """
        POST /maintenance_runs/{runId}/labware_offsets
        """
        if not self.current_maintenance_run_id:
            raise FlexCommandError("No active maintenance run.")

        payload = {
            "data": {
                "definitionUri": offset.definitionUri,
                "locationSequence": offset.locationSequence,
                "vector": offset.vector.model_dump(),
            }
        }

        async with self.session.post(
            f"{self.base_url}/maintenance_runs/{self.current_maintenance_run_id}/labware_offsets",
            json=payload,
        ) as resp:
            if resp.status != 201:
                raise FlexCommandError(f"Failed to add offset: {resp.status}")
            log.debug("Offset added to maintenance run.")

    async def add_maintenance_labware_definition(self, definition: Dict[str, Any]):
        """
        POST /maintenance_runs/{runId}/labware_definitions
        Add a custom labware definition (JSON) to the current maintenance run.
        """
        if not self.current_maintenance_run_id:
            raise FlexCommandError("No active maintenance run.")

        payload = {"data": definition}

        async with self.session.post(
            f"{self.base_url}/maintenance_runs/{self.current_maintenance_run_id}/labware_definitions",
            json=payload,
        ) as resp:
            if resp.status != 201:
                raise FlexCommandError(
                    f"Failed to add labware definition: {resp.status}"
                )
            log.debug("Custom labware definition added to maintenance run.")

    # --- Protocol Management ---

    async def upload_protocol(
        self,
        file_path: str,
        labware_paths: Optional[List[str]] = None,
        protocol_kind: str = "standard",
        key: Optional[str] = None,
    ) -> ProtocolData:
        """
        POST /protocols
        Upload a .py or .json protocol file to the robot.

        Args:
            file_path: Path to the main protocol file.
            labware_paths: List of paths to custom labware .json definitions (optional).
            protocol_kind: "standard" or "quick-transfer".
            key: Optional client-side ID to track this protocol.
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Protocol file not found: {file_path}")

        data = aiohttp.FormData()

        # Add Main Protocol File
        filename = os.path.basename(file_path)
        data.add_field("files", open(file_path, "rb"), filename=filename)

        # Add Custom Labware Files if any
        if labware_paths:
            for lw_path in labware_paths:
                if os.path.exists(lw_path):
                    lw_name = os.path.basename(lw_path)
                    data.add_field("files", open(lw_path, "rb"), filename=lw_name)
                else:
                    log.warning(f"Skipping missing labware file: {lw_path}")

        # Add Metadata fields
        if key:
            data.add_field("key", key)
        data.add_field("protocol_kind", protocol_kind)

        async with self.session.post(f"{self.base_url}/protocols", data=data) as resp:
            if resp.status not in [200, 201]:
                raise FlexCommandError(
                    f"Protocol upload failed: {resp.status} - {await resp.text()}"
                )

            response_data = await resp.json()
            return ProtocolData(**response_data["data"])

    async def get_protocols(self, limit: int = 20) -> List[ProtocolData]:
        """
        GET /protocols
        List stored protocols.
        """
        params = {
            "pageLength": limit
        }  # Note: API docs imply pageLength might not be supported here, but often is standard
        async with self.session.get(f"{self.base_url}/protocols") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to list protocols: {resp.status}")

            data = await resp.json()
            return [ProtocolData(**item) for item in data.get("data", [])]

    async def get_protocol(self, protocol_id: str) -> ProtocolData:
        """
        GET /protocols/{protocolId}
        """
        async with self.session.get(f"{self.base_url}/protocols/{protocol_id}") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get protocol: {resp.status}")

            data = await resp.json()
            return ProtocolData(**data["data"])

    async def delete_protocol(self, protocol_id: str):
        """
        DELETE /protocols/{protocolId}
        """
        async with self.session.delete(
            f"{self.base_url}/protocols/{protocol_id}"
        ) as resp:
            if resp.status == 409:
                raise FlexCommandError(
                    "Cannot delete protocol: It is currently linked to an active run."
                )
            if resp.status != 200:
                raise FlexCommandError(f"Failed to delete protocol: {resp.status}")
            log.info(f"Deleted protocol: {protocol_id}")

    # --- Analysis (Simulation) ---

    async def analyze_protocol(self, protocol_id: str, force_reanalyze: bool = False):
        """
        POST /protocols/{protocolId}/analyses
        Trigger a new analysis (simulation) of the protocol.
        Useful if you want to check for errors before running.
        """
        payload = {"data": {"forceReAnalyze": force_reanalyze}}
        async with self.session.post(
            f"{self.base_url}/protocols/{protocol_id}/analyses", json=payload
        ) as resp:
            if resp.status not in [200, 201]:
                raise FlexCommandError(f"Analysis failed to start: {resp.status}")
            # Returns list of analyses initiated
            return await resp.json()

    async def get_analysis_status(
        self, protocol_id: str, analysis_id: str
    ) -> Dict[str, Any]:
        """
        GET /protocols/{protocolId}/analyses/{analysisId}
        Check if analysis is complete and get results.
        """
        async with self.session.get(
            f"{self.base_url}/protocols/{protocol_id}/analyses/{analysis_id}"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get analysis: {resp.status}")

            data = await resp.json()
            return data.get("data", {})

    # --- Data Files (CSV/Input Management) ---

    async def upload_data_file(self, file_path: str) -> DataFile:
        """
        POST /dataFiles
        Upload a CSV or text file to be read by the protocol.
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Data file not found: {file_path}")

        data = aiohttp.FormData()
        filename = os.path.basename(file_path)
        data.add_field("file", open(file_path, "rb"), filename=filename)

        async with self.session.post(f"{self.base_url}/dataFiles", data=data) as resp:
            if resp.status not in [200, 201]:
                raise FlexCommandError(f"Data file upload failed: {resp.status}")

            response_data = await resp.json()
            return DataFile(**response_data["data"])

    # --- Stateless "Simple" Commands ---

    async def execute_stateless_command(
        self,
        command_type: str,
        params: Dict[str, Any],
        wait: bool = True,
        timeout: int = None,
    ) -> Dict[str, Any]:
        """
        POST /commands
        Execute a single, stateless command (e.g., 'home', 'setRailLights').

        Args:
            command_type: The Protocol Engine command type.
            params: Parameters for the command.
            wait: If True, waits for completion (default True).
            timeout: Max time in milliseconds to wait (if wait=True). Default is infinite.
        """
        payload = {"data": {"commandType": command_type, "params": params}}

        # Build query parameters
        qs_params = {}
        if wait:
            qs_params["waitUntilComplete"] = "true"
            if timeout:
                qs_params["timeout"] = str(timeout)
            # If wait is True and timeout is None, API defaults to infinite

        async with self.session.post(
            f"{self.base_url}/commands", json=payload, params=qs_params
        ) as resp:
            # 409 Conflict can happen if a Run is currently active and locking the hardware
            if resp.status == 409:
                raise FlexCommandError(
                    "Cannot execute stateless command: A Run is currently active."
                )

            if resp.status != 201:
                raise FlexCommandError(
                    f"Stateless command failed ({resp.status}): {await resp.text()}"
                )

            response_data = await resp.json()
            result_data = response_data.get("data", {})

            # Check for logic errors inside the success response
            if result_data.get("status") == "failed":
                error_detail = result_data.get("error", {}).get(
                    "detail", "Unknown Error"
                )
                log.error(f"Stateless Command {command_type} FAILED: {error_detail}")
                raise FlexCommandError(error_detail)

            return result_data

    async def get_stateless_commands(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        GET /commands
        Get a history of stateless commands executed since boot.
        """
        params = {"pageLength": limit}
        async with self.session.get(f"{self.base_url}/commands", params=params) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to list stateless commands: {resp.status}"
                )

            data = await resp.json()
            return data.get("data", [])

    async def get_stateless_command_detail(self, command_id: str) -> Dict[str, Any]:
        """
        GET /commands/{commandId}
        Get full details/result of a specific stateless command.
        """
        async with self.session.get(f"{self.base_url}/commands/{command_id}") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get command detail: {resp.status}")

            data = await resp.json()
            return data.get("data", {})

    # --- Flex Deck Configuration (Collision Avoidance) ---

    async def get_deck_configuration(self) -> DeckConfiguration:
        """
        GET /deck_configuration
        Get the current physical layout of the Flex deck (Staging areas, Waste chutes, etc).

        WARNING: This endpoint is Flex-only.
        """
        async with self.session.get(f"{self.base_url}/deck_configuration") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get deck config: {resp.status}")

            data = await resp.json()
            return DeckConfiguration(**data["data"])

    async def set_deck_configuration(
        self, fixtures: List[CutoutFixture]
    ) -> DeckConfiguration:
        """
        PUT /deck_configuration
        Inform the robot of its physical setup so it can dodge obstacles.

        Persists across reboots.

        Args:
            fixtures: List of CutoutFixture objects defining what is installed where.
                      Any cutout NOT mentioned will remain unchanged (or reset depending on FW version).
                      It is best practice to send the COMPLETE list of fixtures.
        """
        # Convert Pydantic models to list of dicts for JSON serialization
        fixtures_data = [f.model_dump(exclude_none=True) for f in fixtures]

        payload = {"data": {"cutoutFixtures": fixtures_data}}

        async with self.session.put(
            f"{self.base_url}/deck_configuration", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to set deck config: {resp.status} - {await resp.text()}"
                )

            response_data = await resp.json()
            log.info("Flex Deck Configuration updated successfully.")
            return DeckConfiguration(**response_data["data"])

    # --- Error Recovery Configuration ---

    async def get_error_recovery_settings(self) -> ErrorRecoverySettings:
        """
        GET /errorRecovery/settings
        Check if the robot is configured to attempt recovery on failure.
        """
        async with self.session.get(f"{self.base_url}/errorRecovery/settings") as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to get recovery settings: {resp.status}"
                )

            data = await resp.json()
            # Response: { "data": { "enabled": true } }
            return ErrorRecoverySettings(**data["data"])

    async def set_error_recovery_settings(self, enabled: bool) -> ErrorRecoverySettings:
        """
        PATCH /errorRecovery/settings
        Enable or disable global error recovery.

        If enabled, the robot will pause and wait for user intervention (on the touchscreen
        or via API) when a recoverable error occurs (e.g., missing tips).
        """
        payload = {"data": {"enabled": enabled}}

        async with self.session.patch(
            f"{self.base_url}/errorRecovery/settings", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to set recovery settings: {resp.status}"
                )

            data = await resp.json()
            log.info(f"Error Recovery enabled: {enabled}")
            return ErrorRecoverySettings(**data["data"])

    async def reset_error_recovery_settings(self) -> ErrorRecoverySettings:
        """
        DELETE /errorRecovery/settings
        Reset error recovery settings to factory defaults.
        """
        async with self.session.delete(
            f"{self.base_url}/errorRecovery/settings"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to reset recovery settings: {resp.status}"
                )

            data = await resp.json()
            return ErrorRecoverySettings(**data["data"])

    # --- Modules (Updated for Modern API) ---

    async def get_modules(self) -> List[Dict[str, Any]]:
        """
        GET /modules
        Get a list of all modules currently attached to the robot.

        Updated to support the modern 'data' envelope structure used by Flex.
        """
        async with self.session.get(f"{self.base_url}/modules") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get modules: {resp.status}")

            response_json = await resp.json()

            # Robust check: Flex API uses 'data', older OT-2 FW might use 'modules'
            # We prioritize 'data' as per the spec provided.
            if "data" in response_json:
                return response_json["data"]
            elif "modules" in response_json:
                return response_json["modules"]
            else:
                return []

    # --- Instrument Management (Flex Specific) ---

    async def get_instruments(self) -> List[InstrumentData]:
        """
        GET /instruments
        Get a list of all instruments (pipettes & gripper) attached to the Flex.

        This is the modern replacement for 'get_pipettes'.
        """
        async with self.session.get(f"{self.base_url}/instruments") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get instruments: {resp.status}")

            response_json = await resp.json()
            data_list = response_json.get("data", [])

            # Convert JSON to Pydantic Models
            instruments = []
            for item in data_list:
                # We filter out 'empty' slots unless you specifically want them
                # The API usually only returns physically detected instruments
                if item.get("ok"):
                    instruments.append(InstrumentData(**item))
                else:
                    log.warning(
                        f"Instrument at {item.get('mount')} reported as NOT OK."
                    )

            return instruments
        # --- Calibration Data Management ---

    async def get_pipette_offset_calibrations(
        self, pipette_id: Optional[str] = None, mount: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        GET /calibration/pipette_offset
        Fetch saved pipette offset calibrations.

        Args:
            pipette_id: Filter by specific pipette serial.
            mount: Filter by 'left' or 'right'.
        """
        params = {}
        if pipette_id:
            params["pipette_id"] = pipette_id
        if mount:
            params["mount"] = mount

        async with self.session.get(
            f"{self.base_url}/calibration/pipette_offset", params=params
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get pipette offsets: {resp.status}")

            data = await resp.json()
            return data.get("data", [])

    async def delete_pipette_offset_calibration(self, pipette_id: str, mount: str):
        """
        DELETE /calibration/pipette_offset
        Delete a specific pipette offset calibration.

        CRITICAL: Use this if a pipette has been physically re-seated or collided,
        and you want to force the robot to require recalibration.
        """
        params = {"pipette_id": pipette_id, "mount": mount}

        async with self.session.delete(
            f"{self.base_url}/calibration/pipette_offset", params=params
        ) as resp:
            if resp.status == 404:
                log.warning(
                    f"No offset found to delete for {mount} pipette {pipette_id}"
                )
                return

            if resp.status != 200:
                raise FlexCommandError(f"Failed to delete offset: {resp.status}")

            log.info(f"Deleted pipette offset calibration for {mount}")

    # --- Tip Length Calibration Management ---

    async def get_tip_length_calibrations(
        self, pipette_id: Optional[str] = None, tiprack_uri: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        GET /calibration/tip_length
        Fetch saved tip length calibrations.

        Args:
            pipette_id: Filter by the pipette serial number.
            tiprack_uri: Filter by the labware URI (e.g., "opentrons/opentrons_96_tiprack_300ul/1").
        """
        params = {}
        if pipette_id:
            params["pipette_id"] = pipette_id
        if tiprack_uri:
            params["tiprack_uri"] = tiprack_uri

        async with self.session.get(
            f"{self.base_url}/calibration/tip_length", params=params
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to get tip length calibrations: {resp.status}"
                )

            data = await resp.json()
            return data.get("data", [])

    async def delete_tip_length_calibration(self, pipette_id: str, tiprack_uri: str):
        """
        DELETE /calibration/tip_length
        Delete a specific tip length calibration.

        Args:
            pipette_id: The serial number of the pipette associated with the calibration.
            tiprack_uri: The URI of the tiprack (e.g., "opentrons/opentrons_96_tiprack_300ul/1").
        """
        params = {"pipette_id": pipette_id, "tiprack_uri": tiprack_uri}

        async with self.session.delete(
            f"{self.base_url}/calibration/tip_length", params=params
        ) as resp:
            if resp.status == 404:
                log.warning(
                    f"No tip length calibration found to delete for {pipette_id} + {tiprack_uri}"
                )
                return

            if resp.status != 200:
                raise FlexCommandError(
                    f"Failed to delete tip length calibration: {resp.status}"
                )

            log.info(f"Deleted tip length calibration for {tiprack_uri}")

    # --- System Control (Time & Sync) ---

    async def get_system_time(self) -> SystemTime:
        """
        GET /system/time
        Get the robot's current system time, timezone, and NTP status.
        """
        async with self.session.get(f"{self.base_url}/system/time") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get system time: {resp.status}")

            data = await resp.json()
            return SystemTime(**data["data"])

    async def set_system_time(self, new_dt: datetime):
        """
        PUT /system/time
        Manually update the robot's system clock.

        Args:
            new_dt: Python datetime object (e.g. datetime.utcnow()).

        WARNING: If the robot is connected to the internet, it will likely
        override this via NTP (Network Time Protocol) automatically.
        This is mostly for offline robots.
        """
        # Convert datetime to ISO 8601 string
        iso_time = new_dt.isoformat()

        payload = {"data": {"systemTime": iso_time}}

        async with self.session.put(
            f"{self.base_url}/system/time", json=payload
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to set system time: {resp.status}")

            log.info(f"Robot system time updated to: {iso_time}")

    # --- Subsystem Management (Firmware & Health) ---

    async def get_all_subsystems(self) -> List[SubsystemInfo]:
        """
        GET /subsystems/status
        Get the status of all attached hardware components (Firmware version, health).
        """
        async with self.session.get(f"{self.base_url}/subsystems/status") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get subsystems: {resp.status}")

            data = await resp.json()
            return [SubsystemInfo(**item) for item in data.get("data", [])]

    async def get_subsystem_status(self, subsystem: Subsystem) -> SubsystemInfo:
        """
        GET /subsystems/status/{subsystem}
        Get details for a specific component.
        """
        async with self.session.get(
            f"{self.base_url}/subsystems/status/{subsystem.value}"
        ) as resp:
            if resp.status == 404:
                raise FlexCommandError(
                    f"Subsystem {subsystem.value} not found/attached."
                )
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get status: {resp.status}")

            data = await resp.json()
            return SubsystemInfo(**data["data"])

    async def get_ongoing_updates(self) -> List[SubsystemUpdate]:
        """
        GET /subsystems/updates/current
        List currently running firmware updates.
        """
        async with self.session.get(
            f"{self.base_url}/subsystems/updates/current"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to list current updates: {resp.status}")

            data = await resp.json()
            return [SubsystemUpdate(**item) for item in data.get("data", [])]

    async def update_subsystem(self, subsystem: Subsystem) -> SubsystemUpdate:
        """
        POST /subsystems/updates/{subsystem}
        Start a firmware update for a specific component.

        WARNING: This operation can take time and may require a system restart.
        """
        async with self.session.post(
            f"{self.base_url}/subsystems/updates/{subsystem.value}"
        ) as resp:
            # 200/201/303 are all valid success indicators for starting an update
            if resp.status not in [200, 201, 303]:
                raise FlexCommandError(
                    f"Failed to start update: {resp.status} - {await resp.text()}"
                )

            data = await resp.json()
            return SubsystemUpdate(**data["data"])

    # --- Robot Safety (E-Stop & Door) ---

    async def get_estop_status(self) -> EstopStatusResponse:
        """
        GET /robot/control/estopStatus
        Check the current state of the Emergency Stop system.
        """
        async with self.session.get(
            f"{self.base_url}/robot/control/estopStatus"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get Estop status: {resp.status}")

            data = await resp.json()
            return EstopStatusResponse(**data["data"])

    async def acknowledge_estop_disengage(self) -> EstopStatusResponse:
        """
        PUT /robot/control/acknowledgeEstopDisengage

        If the E-Stop button has been released (Physical=Disengaged) but the
        system is still 'Logically Engaged', this command clears the lock
        and allows motors to move again.
        """
        async with self.session.put(
            f"{self.base_url}/robot/control/acknowledgeEstopDisengage"
        ) as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to acknowledge Estop: {resp.status}")

            data = await resp.json()
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

        Note: The Flex will pause automatically if the door opens during a run.
        """
        async with self.session.get(f"{self.base_url}/robot/door/status") as resp:
            if resp.status != 200:
                raise FlexCommandError(f"Failed to get door status: {resp.status}")

            data = await resp.json()
            return DoorStatusResponse(**data["data"])
