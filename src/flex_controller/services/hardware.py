from typing import Any, Dict, List, Optional

from ..client import FlexHTTPClient
from ..constants import Endpoints
from ..schemas import (
    EngagedMotor,
    InstrumentData,
    MotorsStatusResponse,
    PipettesResponse,
    Subsystem,
    SubsystemInfo,
    SubsystemUpdate,
)

# Logging import
try:
    from src.common.log import get_logger

    log = get_logger("FlexHardware")
except ImportError:
    import logging

    log = logging.getLogger("FlexHardware")


class HardwareService:
    """
    Manages low-level hardware interactions:
    - Instruments (Pipettes, Grippers)
    - Modules (HeaterShaker, MagDeck, etc.)
    - Subsystems (Firmware Updates, Health)
    - Motors (Engage/Disengage)
    - Peripherals (Lights)
    """

    def __init__(self, client: FlexHTTPClient):
        self.client = client

    # ============================================================================
    #                                 SUBSYSTEMS
    # ============================================================================

    async def get_all_subsystems(self) -> List[SubsystemInfo]:
        """
        GET /subsystems/status
        Get the status of all attached hardware components (Firmware version, health).
        """
        data = await self.client.get(Endpoints.SUBSYSTEMS_STATUS)
        return [SubsystemInfo(**item) for item in data.get("data", [])]

    async def get_subsystem_status(self, subsystem: Subsystem) -> SubsystemInfo:
        """
        GET /subsystems/status/{subsystem}
        Get details for a specific component.
        """
        path = f"{Endpoints.SUBSYSTEMS_STATUS}/{subsystem.value}"
        data = await self.client.get(path)
        return SubsystemInfo(**data["data"])

    async def get_ongoing_updates(self) -> List[SubsystemUpdate]:
        """
        GET /subsystems/updates/current
        List currently running firmware updates.
        """
        data = await self.client.get(Endpoints.SUBSYSTEMS_UPDATES_CURRENT)
        return [SubsystemUpdate(**item) for item in data.get("data", [])]

    async def update_subsystem(self, subsystem: Subsystem) -> SubsystemUpdate:
        """
        POST /subsystems/updates/{subsystem}
        Start a firmware update for a specific component.

        WARNING: This operation can take time and may require a system restart.
        """
        path = Endpoints.SUBSYSTEM_UPDATE.format(subsystem=subsystem.value)
        # 200/201/303 are all valid success indicators handled by client
        data = await self.client.post(path)
        return SubsystemUpdate(**data["data"])

    # ============================================================================
    #                                  MODULES
    # ============================================================================

    async def get_modules(self) -> List[Dict[str, Any]]:
        """
        GET /modules
        Get a list of all modules currently attached to the robot.
        """
        response_json = await self.client.get(Endpoints.MODULES)

        # Robust check: Flex API uses 'data', older OT-2 FW might use 'modules'
        if "data" in response_json:
            return response_json["data"]
        elif "modules" in response_json:
            return response_json["modules"]
        else:
            return []

    async def update_module_firmware(self, serial: str):
        """
        POST /modules/{serial}/update
        Command the robot to flash its bundled firmware file to this specific module.
        """
        path = Endpoints.MODULE_UPDATE.format(serial=serial)
        await self.client.post(path)
        log.info(f"Initiated firmware update for module {serial}")

    # ============================================================================
    #                                INSTRUMENTS
    # ============================================================================

    async def get_instruments(self) -> List[InstrumentData]:
        """
        GET /instruments
        Get a list of all instruments (pipettes & gripper) attached to the Flex.
        This is the modern replacement for 'get_pipettes'.
        """
        data = await self.client.get(Endpoints.INSTRUMENTS)
        data_list = data.get("data", [])

        instruments = []
        for item in data_list:
            # Only return instruments reported as healthy/present
            if item.get("ok"):
                instruments.append(InstrumentData(**item))
            else:
                log.warning(f"Instrument at {item.get('mount')} reported as NOT OK.")

        return instruments

    async def get_pipettes(self) -> PipettesResponse:
        """
        GET /pipettes
        Legacy compatibility endpoint.
        On Flex, prefer get_instruments().
        """
        # Enforce refresh=false to prevent motor disable on Flex
        params = {"refresh": "false"}
        data = await self.client.get(Endpoints.PIPETTES, params=params)
        return PipettesResponse(**data)

    # ============================================================================
    #                                  MOTORS
    # ============================================================================

    async def get_engaged_motors(self) -> MotorsStatusResponse:
        """
        GET /motors/engaged
        Query which motors are currently powered and holding position.
        """
        data = await self.client.get(Endpoints.MOTORS_ENGAGED)
        return MotorsStatusResponse(**data)

    async def disengage_motors(self, axes: List[str]):
        """
        POST /motors/disengaged
        Cut power to specific motors, allowing them to be moved manually.

        Args:
            axes: Valid Flex axes ["x", "y", "z_l", "z_r", "p_l", "p_r", "q", "g"]
        """
        payload = {"axes": [a.lower() for a in axes]}
        await self.client.post(Endpoints.MOTORS_DISENGAGED, json=payload)
        log.info(f"Motors disengaged: {axes}")

    # ============================================================================
    #                             ROBOT PERIPHERALS
    # ============================================================================

    async def identify(self, seconds: int = 10):
        """
        POST /identify
        Blink the gantry lights so you can pick the robot out of a crowd.
        """
        params = {"seconds": seconds}
        await self.client.post(Endpoints.IDENTIFY, params=params)
        log.info(f"Robot identifying (blinking) for {seconds} seconds.")

    async def get_lights_status(self) -> bool:
        """
        GET /robot/lights
        Returns True if the rail lights are currently ON.
        """
        data = await self.client.get(Endpoints.ROBOT_LIGHTS)
        return data.get("on", False)

    async def set_lights(self, on: bool = True):
        """
        POST /robot/lights
        Turn the rail lights on or off.
        """
        payload = {"on": on}
        data = await self.client.post(Endpoints.ROBOT_LIGHTS, json=payload)
        state = "ON" if data.get("on") else "OFF"
        log.info(f"Robot lights turned {state}")
