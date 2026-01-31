from src.opentrons_sdk.client import FlexHTTPClient
from src.opentrons_sdk.constants import APIDefaults
from src.opentrons_sdk.models import Health
from src.opentrons_sdk.services.attached_instruments import AttachedInstrumentsService
from src.opentrons_sdk.services.attached_modules import AttachedModulesService
from src.opentrons_sdk.services.camera import CameraService
from src.opentrons_sdk.services.client_data import ClientDataservice
from src.opentrons_sdk.services.control import ControlService
from src.opentrons_sdk.services.data_files_management import (
    DataFilesManagamentService,
)
from src.opentrons_sdk.services.deck_calibration import DeckCalibrationService
from src.opentrons_sdk.services.error_recovery_settings import (
    ErrorRecoverySettingsService,
)
from src.opentrons_sdk.services.flex_deck_configuration import (
    FlexDeckConfigurationService,
)
from src.opentrons_sdk.services.flex_subsystem_management import (
    FlexSubsystemManagementService,
)
from src.opentrons_sdk.services.health import HealthService
from src.opentrons_sdk.services.labware_calibration_management import (
    LabwareCalibrationManagementService,
)
from src.opentrons_sdk.services.labware_offset_management import (
    LabwareOffsetManagementService,
)
from src.opentrons_sdk.services.logs import LogsService
from src.opentrons_sdk.services.maintenance_run_management import (
    MaintenanceRunManagementService,
)
from src.opentrons_sdk.services.modules import ModuleService
from src.opentrons_sdk.services.motors import MotorService
from src.opentrons_sdk.services.networking import NetworkingService
from src.opentrons_sdk.services.pipette_offset_calibration_management import (
    PipetteOffsetCalibrationManagementService,
)
from src.opentrons_sdk.services.pipettes import PipetteService
from src.opentrons_sdk.services.protocol_management import ProtocolManagementService
from src.opentrons_sdk.services.robot import RobotService
from src.opentrons_sdk.services.run_management import RunManagementService
from src.opentrons_sdk.services.settings import SettingsService
from src.opentrons_sdk.services.simple_commands import SimpleCommandsService
from src.opentrons_sdk.services.system_control import SystemControlService
from src.opentrons_sdk.services.tip_length_calibration_management import (
    TipLengthCalibrationManagementService,
)

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
        self.run_mangament = RunManagementService(self._client)
        self.maintenance_run_management = MaintenanceRunManagementService(self._client)
        self.protocol_management = ProtocolManagementService(self._client)
        self.data_files_management = DataFilesManagamentService(self._client)
        self.simple_commands = SimpleCommandsService(self._client)
        self.flex_deck_configuration = FlexDeckConfigurationService(self._client)
        self.error_recovery_settings = ErrorRecoverySettingsService(self._client)
        self.attached_modules = AttachedModulesService(self._client)
        self.attached_instruments = AttachedInstrumentsService(self._client)
        self.labware_calibration_management = LabwareCalibrationManagementService(
            self._client
        )
        self.pipette_offset_calibration_management = (
            PipetteOffsetCalibrationManagementService(self._client)
        )
        self.tip_length_calibartion_management = TipLengthCalibrationManagementService(
            self._client
        )
        self.system_control = SystemControlService(self._client)
        self.flex_subsystem_management = FlexSubsystemManagementService(self._client)
        self.robot = RobotService(self._client)
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
