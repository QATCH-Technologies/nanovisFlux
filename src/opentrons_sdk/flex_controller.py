from client import FlexHTTPClient
from constants import APIDefaults
from services.attached_instruments import AttachedInstrumentsService
from services.attached_modules import AttachedModulesService
from services.camera import CameraService
from services.client_data import ClientDataservice
from services.control import ControlService
from services.data_files_management import (
    DataFilesManagamentService,
)
from services.deck_calibration import DeckCalibrationService
from services.error_recovery_settings import (
    ErrorRecoverySettingsService,
)
from services.flex_deck_configuration import (
    FlexDeckConfigurationService,
)
from services.flex_subsystem_management import (
    FlexSubsystemManagementService,
)
from services.health import HealthService
from services.labware_calibration_management import (
    LabwareCalibrationManagementService,
)
from services.labware_offset_management import (
    LabwareOffsetManagementService,
)
from services.logs import LogsService
from services.maintenance_run_management import (
    MaintenanceRunManagementService,
)
from services.modules import ModuleService
from services.motors import MotorService
from services.networking import NetworkingService
from services.pipette_offset_calibration_management import (
    PipetteOffsetCalibrationManagementService,
)
from services.pipettes import PipetteService
from services.protocol_management import ProtocolManagementService
from services.robot import RobotService
from services.run_management import RunManagementService
from services.settings import SettingsService
from services.simple_commands import SimpleCommandsService
from services.system_control import SystemControlService
from services.tip_length_calibration_management import (
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
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FlexController, cls).__new__(cls)
        return cls._instance

    def __init__(self, robot_ip: str = None, port: int = APIDefaults.PORT):
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

        # HTTP client used by all services
        self._client = FlexHTTPClient(base_url)

        # Domain namespace services
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
        self.camera = CameraService(self._client)

        self._initialized = True
        log.info(f"FlexController initialized at {base_url}")

    @classmethod
    def get_instance(cls) -> "FlexController":
        if cls._instance is None:
            raise RuntimeError(
                "FlexController not initialized. Call FlexController(ip) first."
            )
        return cls._instance

    @classmethod
    def reset_instance(cls):
        cls._instance = None
        cls._initialized = False

    async def connect(self):
        await self._client.connect()
        try:
            health = await self.health.get_health()
            log.info(f"Connected to {health.name} (FW: {health.fw_version})")
        except Exception as e:
            log.error(f"Connection established but Health Check failed: {e}")
            raise e

    async def disconnect(self):
        await self._client.close()
        log.info("Disconnected from Flex.")
