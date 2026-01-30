from src.flex_controller.client import FlexHTTPClient
from src.flex_controller.constants import APIDefaults
from src.flex_controller.models import Health
from src.flex_controller.services.camera import CameraService
from src.flex_controller.services.client_data import ClientDataservice
from src.flex_controller.services.control import ControlService
from src.flex_controller.services.deck_calibration import DeckCalibrationService
from src.flex_controller.services.health import HealthService
from src.flex_controller.services.labware_offset_management import (
    LabwareOffsetManagementService,
)
from src.flex_controller.services.logs import LogsService
from src.flex_controller.services.modules import ModuleService
from src.flex_controller.services.motors import MotorService
from src.flex_controller.services.networking import NetworkingService
from src.flex_controller.services.pipettes import PipetteService
from src.flex_controller.services.run_management import RunManagementService
from src.flex_controller.services.settings import SettingsService

# Logging import
try:
    from src.common.log import get_logger

    log = get_logger("FlexController")
except ImportError:
    import logging

    log = logging.getLogger("FlexController")


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
        self.networking = NetworkingService(self._client)
        self.control = ControlService(self._client)
        self.settings = SettingsService(self._client)
        self.deck_calibration = DeckCalibrationService(self._client)
        self.modules = ModuleService(self._client)
        self.pipettes = PipetteService(self._client)
        self.motors = MotorService(self._client)
        self.logs = LogsService(self._client)
        self.health = HealthService(self._client)
        self.client_data = ClientDataservice(self._client)
        self.labware_offset_management = LabwareOffsetManagementService(self._client)
        self.runs = RunManagementService(self._client)

        # CameraService disabled for Flex as it has no camera.
        # self.camera = CameraService(self._client)

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
