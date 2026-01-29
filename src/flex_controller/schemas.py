from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

# ============================================================================
#                                 SYSTEM & NETWORK
# ============================================================================


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


class SystemTime(BaseModel):
    systemTime: str  # ISO 8601 Format
    id: Optional[str] = None
    timezone: Optional[str] = None
    synchronized: Optional[bool] = None


class LogIdentifier(str, Enum):
    API = "api.log"
    SERIAL = "serial.log"
    CAN_BUS = "can_bus.log"
    SERVER = "server.log"
    COMBINED = "combined_api_server.log"
    UPDATE = "update_server.log"
    TOUCHSCREEN = "touchscreen.log"


# ============================================================================
#                                 SAFETY & ESTOP
# ============================================================================


class EstopState(str, Enum):
    NOT_PRESENT = "notPresent"
    PHYSICALLY_ENGAGED = "physicallyEngaged"
    LOGICALLY_ENGAGED = "logicallyEngaged"
    DISENGAGED = "disengaged"


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


# ============================================================================
#                              HARDWARE & SUBSYSTEMS
# ============================================================================


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


# ============================================================================
#                                    MOTORS
# ============================================================================


class EngagedMotor(BaseModel):
    enabled: bool


class MotorsStatusResponse(BaseModel):
    x: EngagedMotor
    y: EngagedMotor
    z_l: EngagedMotor
    z_r: EngagedMotor
    p_l: EngagedMotor
    p_r: EngagedMotor
    q: Optional[EngagedMotor] = None
    g: Optional[EngagedMotor] = None


# ============================================================================
#                                  INSTRUMENTS
# ============================================================================


class InstrumentData(BaseModel):
    """Modern Flex Instrument Model (Pipettes & Grippers)."""

    mount: str
    instrumentType: str
    instrumentModel: str
    serialNumber: str
    subsystem: Optional[str] = None
    ok: bool
    firmwareVersion: Optional[str] = None
    data: Optional[Dict[str, Any]] = None

    @property
    def is_gripper(self) -> bool:
        return self.instrumentType == "gripper"

    @property
    def is_pipette(self) -> bool:
        return self.instrumentType == "pipette"


class PipetteModelSpecs(BaseModel):
    displayName: Optional[str] = None
    name: Optional[str] = None
    minVolume: Optional[float] = None
    maxVolume: Optional[float] = None
    channels: Optional[int] = None


class AttachedPipette(BaseModel):
    """Legacy OT-2 Style Pipette Model."""

    id: Optional[str] = None
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


# ============================================================================
#                              DECK & CALIBRATION
# ============================================================================


class CalibrationStatus(BaseModel):
    markedBad: bool = False
    source: Optional[str] = None
    markedAt: Optional[str] = None


class DeckCalibrationStatus(BaseModel):
    status: Union[CalibrationStatus, str, Dict[str, Any]]
    data: Optional[Dict[str, Any]] = None


class InstrumentCalibrationStatus(BaseModel):
    right: Optional[CalibrationStatus] = None
    left: Optional[CalibrationStatus] = None
    gripper: Optional[CalibrationStatus] = None


class SystemCalibrationResponse(BaseModel):
    deckCalibration: DeckCalibrationStatus
    instrumentCalibration: InstrumentCalibrationStatus


class CutoutFixture(BaseModel):
    """Maps a physical cutout slot on the Flex frame to a fixture."""

    cutoutId: str
    cutoutFixtureId: str


class DeckConfiguration(BaseModel):
    cutoutFixtures: List[CutoutFixture]
    lastModifiedAt: Optional[str] = None


# ============================================================================
#                                LABWARE OFFSETS
# ============================================================================


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
    definitionUri: Optional[str] = None
    locationSequence: Optional[List[Dict[str, Any]]] = None


# ============================================================================
#                               RUN MANAGEMENT
# ============================================================================


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


class ErrorRecoverySettings(BaseModel):
    enabled: bool


# ============================================================================
#                            PROTOCOLS & ANALYSIS
# ============================================================================


class ProtocolAnalysisStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ProtocolAnalysis(BaseModel):
    id: str
    status: ProtocolAnalysisStatus
    result: Optional[str] = None
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
    source: str
    createdAt: str


# ... (Previous imports remain the same)

# ============================================================================
#                               RUN MANAGEMENT
# ============================================================================


class CommandType(str, Enum):
    # --- Liquid Handling ---
    ASPIRATE = "aspirate"
    ASPIRATE_IN_PLACE = "aspirateInPlace"
    ASPIRATE_WHILE_TRACKING = "aspirateWhileTracking"  # Flex Specific
    DISPENSE = "dispense"
    DISPENSE_IN_PLACE = "dispenseInPlace"
    DISPENSE_WHILE_TRACKING = "dispenseWhileTracking"  # Flex Specific
    BLOW_OUT = "blowOut"
    BLOW_OUT_IN_PLACE = "blowOutInPlace"
    AIR_GAP_IN_PLACE = "airGapInPlace"
    TOUCH_TIP = "touchTip"

    # --- Tip Management ---
    PICK_UP_TIP = "pickUpTip"
    DROP_TIP = "dropTip"
    DROP_TIP_IN_PLACE = "dropTipInPlace"
    CONFIGURE_NOZZLE_LAYOUT = "configureNozzleLayout"  # Flex Specific (8 vs 96 channel)
    VERIFY_TIP_PRESENCE = "verifyTipPresence"  # Flex Specific (Sensors)
    GET_TIP_PRESENCE = "getTipPresence"
    GET_NEXT_TIP = "getNextTip"

    # --- Motion (Atomic) ---
    MOVE_TO_COORDINATES = "moveToCoordinates"
    MOVE_TO_WELL = "moveToWell"
    MOVE_TO_ADDRESSABLE_AREA = "moveToAddressableArea"  # e.g. Waste Chute
    MOVE_TO_ADDRESSABLE_AREA_FOR_DROP_TIP = "moveToAddressableAreaForDropTip"
    MOVE_RELATIVE = "moveRelative"
    MOVE_LABWARE = "moveLabware"  # Gripper Move
    HOME = "home"
    RETRACT_AXIS = "retractAxis"
    SAVE_POSITION = "savePosition"

    # --- Setup & Configuration ---
    LOAD_LABWARE = "loadLabware"
    RELOAD_LABWARE = "reloadLabware"
    LOAD_PIPETTE = "loadPipette"
    LOAD_MODULE = "loadModule"
    LOAD_LIQUID = "loadLiquid"
    LOAD_LIQUID_CLASS = "loadLiquidClass"
    LOAD_LID_STACK = "loadLidStack"
    LOAD_LID = "loadLid"
    CONFIGURE_FOR_VOLUME = "configureForVolume"

    # --- Module Control ---
    # Thermocycler / HeaterShaker / TempDeck
    SET_TARGET_TEMPERATURE = "setTargetTemperature"
    WAIT_FOR_TEMPERATURE = "waitForTemperature"
    DEACTIVATE_HEATER = "deactivateHeater"
    SET_AND_WAIT_FOR_SHAKE_SPEED = "setAndWaitForShakeSpeed"
    DEACTIVATE_SHAKER = "deactivateShaker"
    OPEN_LABWARE_LATCH = "openLabwareLatch"
    CLOSE_LABWARE_LATCH = "closeLabwareLatch"

    # Thermocycler Specific
    SET_TARGET_BLOCK_TEMPERATURE = "setTargetBlockTemperature"
    WAIT_FOR_BLOCK_TEMPERATURE = "waitForBlockTemperature"
    SET_TARGET_LID_TEMPERATURE = "setTargetLidTemperature"
    WAIT_FOR_LID_TEMPERATURE = "waitForLidTemperature"
    DEACTIVATE_BLOCK = "deactivateBlock"
    DEACTIVATE_LID = "deactivateLid"
    OPEN_LID = "openLid"
    CLOSE_LID = "closeLid"
    RUN_PROFILE = "runProfile"

    # Magnetic Block
    DISENGAGE = "disengage"
    ENGAGE = "engage"

    # Absorbance Reader (Plate Reader)
    INITIALIZE = "initialize"
    READ_ABSORBANCE = "readAbsorbance"

    # Flex Stacker
    RETRIEVE = "retrieve"
    STORE = "store"
    SET_STORED_LABWARE = "setStoredLabware"
    FILL = "fill"
    EMPTY = "empty"

    # --- Utility & System ---
    COMMENT = "comment"
    CUSTOM = "custom"  # Legacy
    SET_RAIL_LIGHTS = "setRailLights"
    SET_STATUS_BAR = "setStatusBar"
    WAIT_FOR_RESUME = "waitForResume"  # Pause Protocol
    WAIT_FOR_DURATION = "waitForDuration"

    # --- Calibration & Maintenance (Unsafe) ---
    CALIBRATE_GRIPPER = "calibrateGripper"
    CALIBRATE_PIPETTE = "calibratePipette"
    CALIBRATE_MODULE = "calibrateModule"
    MOVE_TO_MAINTENANCE_POSITION = "moveToMaintenancePosition"
    UPDATE_POSITION_ESTIMATORS = "updatePositionEstimators"

    # --- Pressure / Liquid Probing (Flex Specific) ---
    LIQUID_PROBE = "liquidProbe"
    TRY_LIQUID_PROBE = "tryLiquidProbe"
    SEAL_PIPETTE_TO_TIP = "sealPipetteToTip"
    UNSEAL_PIPETTE_FROM_TIP = "unsealPipetteFromTip"
    PRESSURE_DISPENSE = "pressureDispense"
