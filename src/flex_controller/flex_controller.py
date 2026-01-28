import asyncio
from typing import Optional

# Import the core client and constants
from .client import FlexHTTPClient
from .constants import APIDefaults
from .services.calibration import CalibrationService
from .services.hardware import HardwareService
from .services.runs import RunService

# Import Domain Services
from .services.system import SystemService

# Logging import
try:
    from flex_serial_controls.log import get_tagged_logger

    log = get_tagged_logger("FlexAPI")
except ImportError:
    import logging

    log = logging.getLogger("FlexAPI")


class FlexController:
    """
    Main Controller for the Opentrons Flex (OT-3).
    Acts as a Singleton to ensure only one connection exists per application lifecycle.

    Architecture:
        - self.system: Health, Network, Safety, Time, Logs
        - self.runs: Protocol Engine, Maintenance Runs, Quick Commands
        - self.hardware: Instruments, Modules, Subsystems, Motors
        - self.calibration: Deck Config, Pipette Offsets, Tip Lengths
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FlexController, cls).__new__(cls)
        return cls._instance

    def __init__(self, robot_ip: str = None, port: int = APIDefaults.PORT):
        """
        Initialize the FlexController.

        Args:
            robot_ip: The IP address of the robot (e.g., "192.168.1.100").
            port: HTTP Port (default 31950).
        """
        if self._initialized:
            if robot_ip and robot_ip != self._robot_ip:
                log.warning(
                    f"Ignored request to change Flex IP to {robot_ip}. Singleton already bound to {self._robot_ip}."
                )
            return

        if not robot_ip:
            raise ValueError(
                "FlexController requires a robot_ip for first initialization."
            )

        self._robot_ip = robot_ip
        base_url = f"http://{robot_ip}:{port}"

        # 1. Initialize the low-level client
        self._client = FlexHTTPClient(base_url)

        # 2. Initialize Domain Services (Namespaces)
        self.system = SystemService(self._client)
        self.runs = RunService(self._client)
        self.hardware = HardwareService(self._client)
        self.calibration = CalibrationService(self._client)

        self._initialized = True
        log.info(f"FlexController initialized at {base_url}")

    @classmethod
    def get_instance(cls) -> "FlexController":
        """
        Retrieve the active singleton instance.
        """
        if cls._instance is None:
            raise RuntimeError(
                "FlexController not initialized. Call FlexController(ip) first."
            )
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """
        FOR TESTING ONLY: Destroys the singleton instance.
        """
        cls._instance = None
        cls._initialized = False

    async def connect(self):
        """
        Establish connection and verify robot health.
        """
        await self._client.connect()
        try:
            # Perform a health check to verify communication
            health = await self.system.get_health()
            log.info(f"Connected to {health.name} (FW: {health.fw_version})")
        except Exception as e:
            # If health check fails, we are not truly 'connected'
            log.error(f"Connection established but Health Check failed: {e}")
            raise e

    async def disconnect(self):
        """
        Close the HTTP session.
        """
        await self._client.close()
        log.info("Disconnected from Flex.")
