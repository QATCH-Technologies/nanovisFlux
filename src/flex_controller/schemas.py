from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

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


# PARAMETERS ==================>


class AspirateInPlaceParams(BaseModel):
    pipetteId: str
    volume: float = Field(..., ge=0)
    flowRate: float = Field(..., gt=0)
    correctionVolume: Optional[float] = None


class Coordinate(BaseModel):
    x: float
    y: float
    z: float


class WellOrigin(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    CENTER = "center"
    MENISCUS = "meniscus"


class WellOffset(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class LiquidHandlingWellLocation(BaseModel):
    origin: WellOrigin = Field(
        default=WellOrigin.TOP, description="Reference point within the well."
    )
    offset: Optional[WellOffset] = Field(
        default_factory=WellOffset, description="XYZ offset from the origin."
    )
    volumeOffset: Union[float, Literal["operationVolume"]] = Field(
        default=0,
        description="A volume of liquid (µL) to offset the z-axis. If 'operationVolume', uses command volume.",
    )


class AspirateParams(BaseModel):
    pipetteId: str
    labwareId: str
    wellName: str
    wellLocation: Optional[LiquidHandlingWellLocation] = None
    flowRate: float = Field(..., gt=0)
    volume: float = Field(..., ge=0)
    correctionVolume: Optional[float] = None


class AspirateWhileTrackingParams(BaseModel):
    pipetteId: str
    labwareId: str
    wellName: str
    wellLocation: Optional[LiquidHandlingWellLocation] = None
    flowRate: float = Field(..., gt=0)
    volume: float = Field(..., ge=0)
    correctionVolume: Optional[float] = None


class BlowOutInPlaceParams(BaseModel):
    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    flowRate: float = Field(
        ..., gt=0, description="Speed in µL/s configured for the pipette"
    )


class WellLocation(BaseModel):
    """
    A relative location in reference to a well's location.
    """

    origin: WellOrigin = Field(
        default=WellOrigin.TOP, description="Reference point within the well."
    )
    offset: Optional[WellOffset] = Field(
        default_factory=WellOffset, description="XYZ offset from the origin."
    )


class BlowOutParams(BaseModel):
    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    labwareId: str = Field(..., description="Identifier of labware to use.")
    wellName: str = Field(..., description="Name of well to use in labware.")
    flowRate: float = Field(
        ..., gt=0, description="Speed in µL/s configured for the pipette"
    )
    wellLocation: Optional[WellLocation] = Field(
        None, description="Relative well location at which to perform the operation"
    )


class Vec3f(BaseModel):
    """A 3D vector of floats."""

    x: float
    y: float
    z: float


class CalibrateGripperParamsJaw(str, Enum):
    FRONT = "front"
    REAR = "rear"


class CalibrateGripperParams(BaseModel):
    jaw: CalibrateGripperParamsJaw = Field(
        ..., description="Which jaw (front/rear) has the probe attached."
    )
    otherJawOffset: Optional[Vec3f] = Field(
        None,
        description="If provided, completes calibration by calculating total offset using this pre-measured value.",
    )


class CalibrateGripperCommand(BaseModel):
    commandType: Literal["calibrateGripper"] = "calibrateGripper"
    params: CalibrateGripperParams


class MountType(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    EXTENSION = "extension"  # Used for Gripper


class CalibrateModuleParams(BaseModel):
    moduleId: str = Field(..., description="The unique id of module to calibrate.")
    labwareId: str = Field(
        ..., description="The unique id of module calibration adapter labware."
    )
    mount: MountType = Field(
        ..., description="The instrument mount used to calibrate the module."
    )


class CalibratePipetteParams(BaseModel):

    mount: MountType = Field(
        ..., description="Instrument mount to calibrate (left/right)."
    )


class CloseGripperJawParams(BaseModel):
    force: Optional[float] = Field(
        None,
        description="The force the gripper should use to hold the jaws. Falls to default if none is provided.",
    )


class CloseLabwareLatchParams(BaseModel):
    moduleId: str = Field(..., description="Unique ID of the Heater-Shaker Module.")


class CommentParams(BaseModel):
    message: str = Field(..., description="A user-facing message.")


class ConfigureForVolumeParams(BaseModel):
    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    volume: float = Field(
        ...,
        ge=0,
        description="Amount of liquid in uL. Must be at least 0 and no greater than a pipette-specific maximum volume.",
    )
    tipOverlapNotAfterVersion: Optional[str] = Field(
        None,
        description="A version of tip overlap data to not exceed (e.g., 'v0'). If None, the current highest version will be used.",
    )


class PrimaryNozzle(str, Enum):
    A1 = "A1"
    H1 = "H1"
    A12 = "A12"
    H12 = "H12"


class AllNozzleLayoutConfiguration(BaseModel):
    style: Literal["ALL"] = "ALL"


class SingleNozzleLayoutConfiguration(BaseModel):
    style: Literal["SINGLE"] = "SINGLE"
    primaryNozzle: PrimaryNozzle = Field(..., description="The nozzle to use.")


class RowNozzleLayoutConfiguration(BaseModel):
    style: Literal["ROW"] = "ROW"
    primaryNozzle: PrimaryNozzle = Field(
        ..., description="The primary nozzle (start of row)."
    )


class ColumnNozzleLayoutConfiguration(BaseModel):
    style: Literal["COLUMN"] = "COLUMN"
    primaryNozzle: PrimaryNozzle = Field(
        ..., description="The primary nozzle (start of column)."
    )


class QuadrantNozzleLayoutConfiguration(BaseModel):
    style: Literal["QUADRANT"] = "QUADRANT"
    primaryNozzle: PrimaryNozzle
    frontRightNozzle: str = Field(..., pattern=r"[A-Z]\d{1,2}", description="e.g. H12")
    backLeftNozzle: str = Field(..., pattern=r"[A-Z]\d{1,2}", description="e.g. A1")


class ConfigureNozzleLayoutParams(BaseModel):
    pipetteId: str = Field(..., description="Identifier of pipette to use.")
    configurationParams: Union[
        AllNozzleLayoutConfiguration,
        SingleNozzleLayoutConfiguration,
        RowNozzleLayoutConfiguration,
        ColumnNozzleLayoutConfiguration,
        QuadrantNozzleLayoutConfiguration,
    ] = Field(..., description="The specific layout configuration to apply.")


class CustomParams(BaseModel):
    model_config = {"extra": "allow"}


class DeactivateBlockParams(BaseModel):
    moduleId: str = Field(..., description="Unique ID of the Thermocycler.")


class DeactivateHeaterParams(BaseModel):
    """
    Input parameters to unset a Heater-Shaker's target temperature.
    """

    moduleId: str = Field(..., description="Unique ID of the Heater-Shaker Module.")


class DeactivateLidParams(BaseModel):
    """
    Input parameters to unset a Thermocycler's target lid temperature.
    """

    moduleId: str = Field(..., description="Unique ID of the Thermocycler.")


class DeactivateShakerParams(BaseModel):
    """
    Input parameters to deactivate shaker for a Heater-Shaker Module.
    """

    moduleId: str = Field(..., description="Unique ID of the Heater-Shaker Module.")


class DeactivateTemperatureParams(BaseModel):
    """
    Input parameters to deactivate a Temperature Module.
    """

    moduleId: str = Field(..., description="Unique ID of the Temperature Module.")


class DelayParams(BaseModel):
    """
    Parameters for a delay or wait command.
    """

    duration: float = Field(..., ge=0, description="Duration of delay, in seconds.")

    model_config = {"extra": "forbid"}  # additionalProperties: false


class DisengageParams(BaseModel):
    """
    Input data to disengage a Magnetic Module's magnets.
    """

    moduleId: str = Field(
        ...,
        description="The ID of the Magnetic Module whose magnets you want to disengage.",
    )


class DispenseInPlaceParams(BaseModel):
    """
    Payload required to dispense in place.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    volume: float = Field(
        ...,
        ge=0,
        description="The amount of liquid to dispense, in µL. Must not be greater than currently aspirated volume.",
    )
    flowRate: float = Field(
        ..., gt=0, description="Speed in µL/s configured for the pipette."
    )
    pushOut: Optional[float] = Field(
        None,
        description="Push the plunger a small amount farther than necessary for accurate low-volume dispensing.",
    )
    correctionVolume: Optional[float] = Field(
        None, description="The correction volume in uL."
    )


class DispenseParams(BaseModel):
    """
    Payload required to dispense liquid to a specific well.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    labwareId: str = Field(..., description="Identifier of labware to use.")
    wellName: str = Field(..., description="Name of well to use in labware.")
    volume: float = Field(
        ..., ge=0, description="The amount of liquid to dispense, in µL."
    )
    flowRate: float = Field(
        ..., gt=0, description="Speed in µL/s configured for the pipette."
    )
    wellLocation: Optional[LiquidHandlingWellLocation] = Field(
        None, description="Relative well location at which to perform the operation."
    )
    pushOut: Optional[float] = Field(
        None,
        description="Push the plunger a small amount farther than necessary for accurate low-volume dispensing.",
    )
    correctionVolume: Optional[float] = Field(
        None, description="The correction volume in uL."
    )


class DispenseWhileTrackingParams(BaseModel):
    """
    Payload required to dispense to a specific well while tracking the liquid level.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    labwareId: str = Field(..., description="Identifier of labware to use.")
    wellName: str = Field(..., description="Name of well to use in labware.")
    volume: float = Field(
        ..., ge=0, description="The amount of liquid to dispense, in µL."
    )
    flowRate: float = Field(
        ..., gt=0, description="Speed in µL/s configured for the pipette."
    )
    wellLocation: Optional[LiquidHandlingWellLocation] = Field(
        None, description="Relative well location at which to perform the operation."
    )
    pushOut: Optional[float] = Field(
        None,
        description="Push the plunger a small amount farther than necessary for accurate low-volume dispensing.",
    )
    correctionVolume: Optional[float] = Field(
        None, description="The correction volume in uL."
    )


class DropTipInPlaceParams(BaseModel):
    """
    Payload required to drop a tip in place.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    homeAfter: Optional[bool] = Field(
        None,
        description=(
            "Whether to home this pipette's plunger after dropping the tip. "
            "Usually left unspecified to allow the robot to choose a safe default."
        ),
    )


# --- Drop Tip Specific Location Types ---


class DropTipWellOrigin(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    CENTER = "center"
    DEFAULT = "default"


class DropTipWellLocation(BaseModel):
    """
    Specialized location for dropping tips.
    Defaults to a height based on tip length rather than just the well top.
    """

    origin: DropTipWellOrigin = Field(
        default=DropTipWellOrigin.DEFAULT,
        description="The reference origin within the well.",
    )
    offset: Optional[WellOffset] = Field(
        default_factory=WellOffset, description="XYZ offset from the origin."
    )


class DropTipParams(BaseModel):
    """
    Payload required to drop a tip in a specific well or waste location.
    """

    pipetteId: str = Field(..., description="Identifier of pipette to use.")
    labwareId: str = Field(
        ..., description="Identifier of labware (e.g., a waste bin or tip rack)."
    )
    wellName: str = Field(
        ..., description="Name of well to use (usually 'A1' for waste chutes)."
    )
    wellLocation: Optional[DropTipWellLocation] = Field(
        None, description="Relative well location at which to drop the tip."
    )
    homeAfter: Optional[bool] = Field(
        None,
        description="Whether to home the plunger after dropping. Default is hardware-dependent.",
    )
    alternateDropLocation: Optional[bool] = Field(
        None,
        description="If True, alternates between two locations to avoid tip piling.",
    )
    scrape_tips: Optional[bool] = Field(
        None,
        description="If True, moves horizontally to 'scrape' tips off against the rack/bin edge.",
    )


class StackerFillEmptyStrategy(str, Enum):
    MANUAL_WITH_PAUSE = "manualWithPause"
    LOGICAL = "logical"


class EmptyParams(BaseModel):
    """
    The parameters defining how a stacker should be emptied.
    """

    moduleId: str = Field(..., description="Unique ID of the Flex Stacker.")
    strategy: StackerFillEmptyStrategy = Field(
        ...,
        description=(
            "How to empty the stacker. 'manualWithPause' triggers a user interaction; "
            "'logical' updates the state immediately without pausing."
        ),
    )
    message: Optional[str] = Field(
        None,
        description="The message to display on the Flex touchscreen during a manual empty.",
    )
    count: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "The new count of labware in the pool. If None, defaults to empty. "
            "The actual count used should be retrieved from the command results."
        ),
    )


class EngageParams(BaseModel):
    """
    Input data to engage a Magnetic Module (raise the magnets).
    """

    moduleId: str = Field(
        ...,
        description="The ID of the Magnetic Module whose magnets you want to raise.",
    )
    height: float = Field(
        ...,
        description=(
            "How high, in millimeters, to raise the magnets. "
            "0.0 is level with the labware ledge. Units are true millimeters."
        ),
    )


class StackerStoredLabwareGroup(BaseModel):
    """
    Represents one group of labware stored in a stacker hopper.
    A group consists of the primary labware and any attached components.
    """

    primaryLabwareId: str = Field(
        ..., description="ID of the main labware (e.g., the plate)."
    )
    adapterLabwareId: Optional[str] = Field(
        None,
        description="ID of the adapter underneath the primary labware, if present.",
    )
    lidLabwareId: Optional[str] = Field(
        None, description="ID of the lid on top of the primary labware, if present."
    )


class FillParams(BaseModel):
    """
    The parameters defining how a stacker should be filled.
    """

    moduleId: str = Field(..., description="Unique ID of the Flex Stacker.")
    strategy: StackerFillEmptyStrategy = Field(
        ...,
        description=(
            "How to fill the stacker. 'manualWithPause' triggers a user prompt; "
            "'logical' updates state immediately."
        ),
    )
    message: Optional[str] = Field(
        None,
        description="The message to display on the Flex touchscreen during a manual fill.",
    )
    count: Optional[int] = Field(
        None,
        ge=1,
        description=(
            "How full the labware pool should now be. If None, defaults to maximum "
            "capacity for the current labware configuration."
        ),
    )
    labwareToStore: Optional[List[StackerStoredLabwareGroup]] = Field(
        None,
        description=(
            "A list of specific labware IDs to be stored in the stacker. "
            "Index 0 represents the labware on the physical bottom."
        ),
    )


class GetNextTipParams(BaseModel):
    """
    Payload needed to resolve the next available tip(s) from a list of tip racks.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    labwareIds: List[str] = Field(
        ...,
        description=(
            "Labware ID(s) of tip racks to resolve next available tip(s) from. "
            "Racks will be checked sequentially."
        ),
    )
    startingTipWell: Optional[str] = Field(
        None,
        description=(
            "Name of starting tip rack 'well'. Only applies to the first rack "
            "in the labwareIds list."
        ),
    )


class GetTipPresenceParams(BaseModel):
    """
    Payload required to check if a tip is currently attached to the pipette.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )


class MotorAxis(str, Enum):
    """Motor axis on which to issue a home command."""

    X = "x"
    Y = "y"
    LEFT_Z = "leftZ"
    RIGHT_Z = "rightZ"
    LEFT_PLUNGER = "leftPlunger"
    RIGHT_PLUNGER = "rightPlunger"
    EXTENSION_Z = "extensionZ"
    EXTENSION_JAW = "extensionJaw"
    AXIS_96_CHANNEL_CAM = "axis96ChannelCam"


class HomeParams(BaseModel):
    """
    Payload required to home specific axes or the entire robot.
    """

    axes: Optional[List[MotorAxis]] = Field(
        None,
        description=(
            "Axes to return to home positions. If omitted, homes all motors. "
            "Note: homing Z often triggers a home of X/Y for safety."
        ),
    )
    skipIfMountPositionOk: Optional[MountType] = Field(
        None,
        description=(
            "If provided, the gantry only homes if the specified mount's "
            "position is lost/invalid. Helps save time in long protocols."
        ),
    )


class ModuleModel(str, Enum):
    """All available modules' models."""

    TEMPERATURE_V1 = "temperatureModuleV1"
    TEMPERATURE_V2 = "temperatureModuleV2"
    MAGNETIC_V1 = "magneticModuleV1"
    MAGNETIC_V2 = "magneticModuleV2"
    THERMOCYCLER_V1 = "thermocyclerModuleV1"
    THERMOCYCLER_V2 = "thermocyclerModuleV2"
    HEATER_SHAKER_V1 = "heaterShakerModuleV1"
    MAGNETIC_BLOCK_V1 = "magneticBlockV1"
    ABSORBANCE_READER_V1 = "absorbanceReaderV1"
    FLEX_STACKER_V1 = "flexStackerModuleV1"


class IdentifyModuleParams(BaseModel):
    """
    The parameters defining the module to be identified (usually via flashing LEDs).
    """

    moduleId: str = Field(..., description="Unique ID of the module.")
    model: ModuleModel = Field(
        ..., description="The specific hardware model of the module."
    )
    start: bool = Field(
        ..., description="True to start identifying (flashing); False to stop."
    )
    color: Optional[str] = Field(
        None,
        description="Optional color string to identify the module if supported by hardware.",
    )


class MeasureMode(str, Enum):
    """Initialize single or multi measurement mode."""

    SINGLE = "single"
    MULTI = "multi"


class InitializeParams(BaseModel):
    """
    Input parameters to initialize an absorbance reading on the Plate Reader.
    """

    moduleId: str = Field(..., description="Unique ID of the absorbance reader.")
    measureMode: MeasureMode = Field(
        ..., description="Initialize single or multi-wavelength measurement mode."
    )
    sampleWavelengths: List[int] = Field(
        ..., description="Sample wavelengths in nm (e.g., [450, 600])."
    )
    referenceWavelength: Optional[int] = Field(
        None,
        description="Optional reference wavelength in nm for background correction.",
    )


class LiquidClassTouchTipParams(BaseModel):
    """
    Parameters for touch-tip
    """

    z_offset: float = Field(
        ...,
        description="Offset from the top of the well for touch-tip, in millimeters.",
    )
    mm_from_edge: float = Field(
        ..., description="Offset away from the the well edge, in millimeters."
    )
    speed: float = Field(
        ..., gt=0, description="Touch-tip speed, in millimeters per second."
    )

    model_config = {"extra": "forbid"}


class LiquidProbeParams(BaseModel):
    """
    Parameters required to probe the liquid level in a specific well.
    Uses the Flex pipette's sensors to detect the meniscus.
    """

    pipetteId: str = Field(..., description="Identifier of pipette to use for probing.")
    labwareId: str = Field(..., description="Identifier of labware to use.")
    wellName: str = Field(..., description="Name of well to probe (e.g., 'A1').")
    wellLocation: Optional[WellLocation] = Field(
        None, description="Relative well location at which to perform the probe."
    )


class DeckSlotName(str, Enum):
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    D1 = "D1"
    D2 = "D2"
    D3 = "D3"


class DeckSlotLocation(BaseModel):
    slotName: DeckSlotName


class ModuleLocation(BaseModel):
    moduleId: str = Field(..., description="ID of a previously loaded module.")


class OnLabwareLocation(BaseModel):
    labwareId: str = Field(..., description="ID of labware to stack on top of.")


class AddressableAreaLocation(BaseModel):
    addressableAreaName: str = Field(..., description="Name from the deck definition.")


class LoadLabwareParams(BaseModel):
    """
    Payload required to load labware into a specific location.
    """

    location: Union[
        DeckSlotLocation,
        ModuleLocation,
        OnLabwareLocation,
        AddressableAreaLocation,
        Literal["offDeck", "systemLocation"],
    ] = Field(..., description="Where the labware is physically located.")

    loadName: str = Field(..., description="API load name for the labware definition.")
    namespace: str = Field(..., description="Namespace (e.g., 'opentrons').")
    version: int = Field(..., description="Version of the labware definition.")

    labwareId: Optional[str] = Field(None, description="User-assigned ID.")
    displayName: Optional[str] = Field(None, description="Human-readable label.")


class LoadLidParams(BaseModel):
    """
    Payload required to load a lid onto a labware or specific deck location.
    """

    location: Union[
        DeckSlotLocation,
        ModuleLocation,
        OnLabwareLocation,
        AddressableAreaLocation,
        Literal["offDeck", "systemLocation"],
    ] = Field(..., description="The location the lid should be loaded onto.")

    loadName: str = Field(
        ..., description="Name used to reference a lid labware definition."
    )
    namespace: str = Field(
        ..., description="The namespace the lid labware definition belongs to."
    )
    version: int = Field(..., description="The lid labware definition version.")


class LoadLidStackParams(BaseModel):
    """
    Payload required to load a stack of lids onto a specific location.
    """

    location: Union[
        DeckSlotLocation,
        ModuleLocation,
        OnLabwareLocation,
        AddressableAreaLocation,
        Literal["offDeck", "systemLocation"],
    ] = Field(..., description="Location where the lid stack should be loaded.")

    loadName: str = Field(
        ..., description="Name used to reference the lid labware definition."
    )
    namespace: str = Field(
        ..., description="The namespace the lid labware definition belongs to."
    )
    version: int = Field(..., description="The lid labware definition version.")
    quantity: int = Field(
        ..., ge=1, description="The number of lids to load into this stack."
    )
    stackLabwareId: Optional[str] = Field(
        None, description="Optional ID for the stack object itself."
    )
    labwareIds: Optional[List[str]] = Field(
        None, description="Optional list of individual IDs for each lid in the stack."
    )


class PositionReference(str, Enum):
    WELL_BOTTOM = "well-bottom"
    WELL_TOP = "well-top"
    WELL_CENTER = "well-center"
    LIQUID_MENISCUS = "liquid-meniscus"


class TipPosition(BaseModel):
    """
    Properties for tip position reference and relative offset.
    """

    position_reference: PositionReference = Field(
        ..., description="Position reference for tip position."
    )
    offset: Coordinate = Field(
        ..., description="Relative offset from position reference."
    )

    model_config = {"extra": "forbid"}


# --- Delay Properties ---
class DelayProperties(BaseModel):
    """Shared properties for delay."""

    enable: bool = Field(..., description="Whether delay is enabled.")
    params: Optional[DelayParams] = Field(
        None, description="Parameters for the delay function."
    )

    model_config = {"extra": "forbid"}


# --- Touch Tip Properties ---
class TouchTipProperties(BaseModel):
    """Shared properties for the touch-tip function."""

    enable: bool = Field(..., description="Whether touch-tip is enabled.")
    params: Optional[LiquidClassTouchTipParams] = Field(
        None, description="Parameters for the touch-tip function."
    )

    model_config = {"extra": "forbid"}


# --- Submerge ---
class Submerge(BaseModel):
    """
    Shared properties for the submerge function before aspiration or dispense.
    """

    start_position: TipPosition = Field(
        ..., description="Tip position before starting the submerge."
    )
    speed: float = Field(..., ge=0, description="Speed of submerging, in mm/s.")
    delay: DelayProperties = Field(..., description="Delay settings for submerge.")

    model_config = {"extra": "forbid"}


# --- Retract ---
class RetractAspirate(BaseModel):
    """
    Shared properties for the retract function after aspiration.
    """

    end_position: TipPosition = Field(
        ..., description="Tip position at the end of the retract."
    )
    speed: float = Field(..., ge=0, description="Speed of retraction, in mm/s.")

    # List of tuples [volume, gap_volume]
    air_gap_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for air gap keyed by target aspiration volume.",
    )
    touch_tip: TouchTipProperties = Field(
        ..., description="Touch tip settings for retract after aspirate."
    )
    delay: DelayProperties = Field(
        ..., description="Delay settings for retract after aspirate."
    )

    model_config = {"extra": "forbid"}


class MixParams(BaseModel):
    """
    Parameters for the mix function.
    """

    repetitions: int = Field(
        ...,
        ge=0,
        description="Number of mixing repetitions. 0 is valid, but no mixing will occur.",
    )
    volume: float = Field(
        ..., gt=0, description="Volume used for mixing, in microliters."
    )

    model_config = {"extra": "forbid"}


class MixProperties(BaseModel):
    """
    Mixing properties configuration.
    """

    enable: bool = Field(..., description="Whether mix is enabled.")
    params: Optional[MixParams] = Field(
        None,
        description="Parameters for the mix function (required if enable is True).",
    )

    model_config = {"extra": "forbid"}


# --- Aspirate Properties ---
class AspirateProperties(BaseModel):
    """
    Properties specific to the aspirate function.
    """

    submerge: Submerge = Field(..., description="Submerge settings for aspirate.")
    retract: RetractAspirate = Field(
        ..., description="Pipette retract settings after an aspirate."
    )
    aspirate_position: TipPosition = Field(
        ..., description="Tip position during aspirate."
    )

    # List of tuples [volume, flow_rate]
    flow_rate_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for flow rate keyed by target aspiration volume.",
    )

    # List of tuples [volume, correction_volume]
    correction_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for volume correction keyed by target aspiration volume.",
    )

    pre_wet: bool = Field(..., description="Whether to perform a pre-wet action.")
    mix: MixProperties = Field(
        ..., description="Mixing settings for before an aspirate."
    )
    delay: DelayProperties = Field(..., description="Delay settings after an aspirate.")

    model_config = {"extra": "forbid"}


class RetractDispense(BaseModel):
    """
    Properties for the retract function after a single dispense.
    """

    end_position: TipPosition = Field(
        ..., description="Tip position at the end of the retract."
    )
    speed: float = Field(..., ge=0, description="Speed of retraction, in mm/s.")

    air_gap_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for air gap keyed by target dispense volume.",
    )

    touch_tip: TouchTipProperties = Field(
        ..., description="Touch tip settings for retract after dispense."
    )
    delay: DelayProperties = Field(
        ..., description="Delay settings for retract after dispense."
    )

    model_config = {"extra": "forbid"}


class SingleDispenseProperties(BaseModel):
    """
    Properties specific to the single-dispense function.
    """

    submerge: Submerge = Field(
        ..., description="Submerge settings for single dispense."
    )
    retract: RetractDispense = Field(
        ..., description="Pipette retract settings after a single dispense."
    )
    dispense_position: TipPosition = Field(
        ..., description="Tip position during dispense."
    )

    flow_rate_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for flow rate keyed by target dispense volume.",
    )

    correction_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for volume correction keyed by target dispense volume.",
    )

    mix: MixProperties = Field(..., description="Mixing settings for after a dispense.")

    push_out_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for pushout keyed by target dispense volume.",
    )

    delay: DelayProperties = Field(
        ..., description="Delay settings after dispense, in seconds."
    )

    model_config = {"extra": "forbid"}


class MultiDispenseProperties(BaseModel):
    """
    Properties specific to the multi-dispense function (distribute).
    """

    submerge: Submerge = Field(..., description="Submerge settings for multi-dispense.")
    retract: RetractDispense = Field(
        ..., description="Pipette retract settings after a multi-dispense."
    )
    dispense_position: TipPosition = Field(
        ..., description="Tip position during dispense."
    )
    flow_rate_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for flow rate keyed by target dispense volume.",
    )
    correction_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for volume correction keyed by target dispense volume.",
    )
    conditioning_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for conditioning volume (extra aspirate) keyed by target dispense volume.",
    )
    disposal_by_volume: List[Tuple[float, float]] = Field(
        ...,
        min_length=1,
        description="Settings for disposal volume (blowout) keyed by target dispense volume.",
    )

    delay: DelayProperties = Field(
        ..., description="Delay settings after each dispense."
    )

    model_config = {"extra": "forbid"}


class LiquidClassRecord(BaseModel):
    """
    Internal representation of an immutable liquid class.
    """

    liquidClassName: str = Field(
        ..., description="Identifier for the liquid (e.g. glycerol50)."
    )
    pipetteModel: str = Field(..., description="Identifier for the pipette.")
    tiprack: str = Field(..., description="Name of tiprack associated with this class.")

    aspirate: AspirateProperties = Field(..., description="Aspirate parameters.")
    dispense: SingleDispenseProperties = Field(
        ..., description="Single dispense parameters."
    )
    multi_dispense: Optional[MultiDispenseProperties] = Field(
        None, description="Optional multi-dispense parameters."
    )

    model_config = {"extra": "forbid"}


class LoadLiquidClassParams(BaseModel):
    """
    Payload required to load a custom liquid class definition.
    """

    liquidClassRecord: LiquidClassRecord = Field(
        ..., description="The liquid class to store."
    )
    liquidClassId: Optional[str] = Field(
        None,
        description="Unique ID for the liquid class. If None, one will be generated.",
    )


class LoadLiquidParams(BaseModel):
    """
    Payload required to load a liquid definition into specific wells of a labware.
    This sets the initial state for the protocol (e.g., indicating that A1 contains 50uL of 'Buffer').
    """

    liquidId: Union[Literal["EMPTY"], str] = Field(
        ...,
        description=(
            "Unique identifier of the liquid to load. "
            "If this is the sentinel value 'EMPTY', all values in volumeByWell must be 0."
        ),
    )
    labwareId: str = Field(
        ..., description="Unique identifier of labware to load liquid into."
    )
    volumeByWell: Dict[str, float] = Field(
        ...,
        description=(
            "Volume of liquid, in µL, loaded into each well (keyed by well name). "
            "If liquidId is 'EMPTY', all volumes must be 0."
        ),
    )


class LoadModuleParams(BaseModel):
    """
    Payload required to load a hardware module onto the deck.
    The Protocol Engine will attempt to find a connected module that
    is either an exact match or a compatible version.
    """

    model: ModuleModel = Field(
        ...,
        description=(
            "The model name of the module to load. Compatible hardware "
            "may be substituted (e.g., V2 for a requested V1)."
        ),
    )
    location: DeckSlotLocation = Field(
        ...,
        description=(
            "The deck slot for the module. For the Thermocycler, "
            "use the front-most slot (typically Slot 7 or A1/B1 depending on robot)."
        ),
    )
    moduleId: Optional[str] = Field(
        None,
        description="Optional unique ID for this module instance. Generated if not provided.",
    )


class PipetteNameType(str, Enum):
    P10_SINGLE = "p10_single"
    P10_MULTI = "p10_multi"
    P20_SINGLE_GEN2 = "p20_single_gen2"
    P20_MULTI_GEN2 = "p20_multi_gen2"
    P50_SINGLE = "p50_single"
    P50_MULTI = "p50_multi"
    P50_SINGLE_FLEX = "p50_single_flex"
    P50_MULTI_FLEX = "p50_multi_flex"
    P300_SINGLE = "p300_single"
    P300_MULTI = "p300_multi"
    P300_SINGLE_GEN2 = "p300_single_gen2"
    P300_MULTI_GEN2 = "p300_multi_gen2"
    P1000_SINGLE = "p1000_single"
    P1000_SINGLE_GEN2 = "p1000_single_gen2"
    P1000_SINGLE_FLEX = "p1000_single_flex"
    P1000_MULTI_FLEX = "p1000_multi_flex"
    P1000_MULTI_EM_FLEX = "p1000_multi_em_flex"
    P1000_96 = "p1000_96"
    P200_96 = "p200_96"


class LoadPipetteParams(BaseModel):
    """
    Payload needed to load a pipette onto a gantry mount.
    """

    pipetteName: PipetteNameType = Field(
        ..., description="The load name of the pipette to be required."
    )
    mount: MountType = Field(
        ..., description="The mount (left or right) the pipette should be present on."
    )
    pipetteId: Optional[str] = Field(
        None, description="Optional unique ID. If None, one will be generated."
    )
    tipOverlapNotAfterVersion: Optional[str] = Field(
        None,
        description=(
            "Version of tip overlap data (vN) to not exceed. "
            "Defaults to current highest version."
        ),
    )
    liquidPresenceDetection: bool = Field(
        False,
        description="Enable real-time liquid presence detection. Defaults to False.",
    )


class MoveAxesRelativeParams(BaseModel):
    """
    Payload required to move specific axes relative to their current position.
    This is useful for fine-tuning tip depth or clearing obstacles.
    """

    axis_map: Dict[MotorAxis, float] = Field(
        ...,
        description=(
            "A dictionary mapping motor axes to relative movement distances in mm. "
        ),
    )
    speed: Optional[float] = Field(
        None,
        description=(
            "The maximum velocity (mm/s) for the move. "
            "Uses hardware defaults if not specified."
        ),
    )


class MoveAxesToParams(BaseModel):
    """
    Payload required to move specified axes to an absolute deck position.
    This provides direct control over the hardware's coordinate system.
    """

    axis_map: Dict[MotorAxis, float] = Field(
        ...,
        description=(
            "The specified axes to move to an absolute deck position. "
            "Keys are the MotorAxis enum and values are absolute mm positions."
        ),
    )
    critical_point: Optional[Dict[str, float]] = Field(
        None,
        description=(
            "The critical point to move the mount with. "
            "Defines which part of the pipette or tool should align with the coordinate."
        ),
    )
    speed: Optional[float] = Field(
        None,
        description=(
            "The max velocity (mm/s) to move the axes at. "
            "Will fall to hardware defaults if none provided."
        ),
    )


# --- Labware Movement Strategy ---


class LabwareMovementStrategy(str, Enum):
    """
    Strategy to use for labware movement within the protocol.
    """

    USING_GRIPPER = "usingGripper"
    MANUAL_MOVE_WITH_PAUSE = "manualMoveWithPause"
    MANUAL_MOVE_WITHOUT_PAUSE = "manualMoveWithoutPause"


# --- Labware Offset Vector ---


class LabwareOffsetVector(BaseModel):
    """
    Offset in deck coordinates (mm) from nominal to actual position.
    Used for fine-tuning gripper engagement or labware placement.
    """

    x: float = Field(..., title="X Offset")
    y: float = Field(..., title="Y Offset")
    z: float = Field(..., title="Z Offset")

    model_config = {"extra": "forbid"}


class MoveLabwareParams(BaseModel):
    """
    Input parameters for the `moveLabware` command.
    Controls the Flex Gripper or prompts for manual user intervention.
    """

    labwareId: str = Field(..., description="The ID of the labware to move.")
    newLocation: Union[
        DeckSlotLocation,
        ModuleLocation,
        OnLabwareLocation,
        AddressableAreaLocation,
        Literal["offDeck", "systemLocation"],
    ] = Field(..., description="The target destination for the labware.")

    strategy: LabwareMovementStrategy = Field(
        ...,
        description=(
            "The method of movement: 'usingGripper' for automation, "
            "or 'manualMoveWithPause'/'manualMoveWithoutPause' for human intervention."
        ),
    )

    pickUpOffset: Optional[LabwareOffsetVector] = Field(
        None,
        description=(
            "Experimental: Offset vector (x, y, z) to use when picking up labware. "
            "Adjusts the gripper engagement point."
        ),
    )
    dropOffset: Optional[LabwareOffsetVector] = Field(
        None,
        description=(
            "Experimental: Offset vector (x, y, z) to use when dropping off labware. "
            "Adjusts the final placement position."
        ),
    )

    model_config = {"extra": "forbid"}


class MovementAxis(str, Enum):
    X = "x"
    Y = "y"
    Z = "z"


class MoveRelativeParams(BaseModel):
    """
    Payload required to move a specific pipette relative to its current position.
    """

    pipetteId: str = Field(..., description="The ID of the pipette to move.")
    axis: MovementAxis = Field(
        ..., description="The cartesian axis along which to move (x, y, or z)."
    )
    distance: float = Field(
        ...,
        description=(
            "Distance to move in millimeters. "
            "Positive = right (x), back (y), or up (z). "
            "Negative = left (x), front (y), or down (z)."
        ),
    )


class AddressableOffsetVector(BaseModel):
    """
    Offset, in deck coordinates (mm), from nominal to actual position
    of an addressable area.
    """

    x: float = Field(..., title="X", description="X offset in mm.")
    y: float = Field(..., title="Y", description="Y offset in mm.")
    z: float = Field(..., title="Z", description="Z offset in mm.")

    model_config = {"extra": "forbid"}


# --- Move To Addressable Area (Drop Tip) ---


class MoveToAddressableAreaForDropTipParams(BaseModel):
    """
    Payload required to move a pipette to a specific addressable area (e.g., waste chute)
    specifically for the purpose of dropping a tip.
    """

    pipetteId: str = Field(..., description="Identifier of pipette to use.")
    addressableAreaName: str = Field(
        ...,
        description=(
            "The name of the addressable area (e.g., '12-holeTrash', 'wasteChute'). "
            "Must be valid in the robot's deck definition."
        ),
    )
    offset: AddressableOffsetVector = Field(
        default_factory=lambda: AddressableOffsetVector(x=0, y=0, z=0),
        description="Relative offset to apply to the move destination.",
    )
    minimumZHeight: Optional[float] = Field(
        None, description="Optional minimal Z margin in mm for the arc."
    )
    forceDirect: bool = Field(
        False,
        description=(
            "If True, moves directly to the target without arcing to a safe Z height. "
            "Use with caution to avoid collisions."
        ),
    )
    speed: Optional[float] = Field(None, description="Override travel speed in mm/s.")
    alternateDropLocation: Optional[bool] = Field(
        None,
        description=(
            "If True, alternates drop locations to prevent tip pile-up. "
            "Ignores provided offset if enabled."
        ),
    )
    ignoreTipConfiguration: Optional[bool] = Field(
        None,
        description=(
            "If True, centers the entire instrument mount over the area "
            "rather than the active tip configuration."
        ),
    )


class MoveToAddressableAreaParams(BaseModel):
    """
    Payload required to move a pipette to a specific addressable area (e.g., '12-holeTrash', 'B4').
    The pipette nozzles (all physical nozzles) will be centered over the area.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    addressableAreaName: str = Field(
        ...,
        description=(
            "The name of the addressable area (e.g., 'wasteChute', 'B4'). "
            "Must verify against the robot's current deck configuration."
        ),
    )
    offset: AddressableOffsetVector = Field(
        default_factory=lambda: AddressableOffsetVector(x=0.0, y=0.0, z=0.0),
        description="Relative offset to apply to the move destination.",
    )
    minimumZHeight: Optional[float] = Field(
        None, description="Optional minimal Z margin in mm for the arc."
    )
    forceDirect: bool = Field(
        False,
        description=(
            "If True, moves directly to the target without arcing. "
            "Ignores minimumZHeight."
        ),
    )
    speed: Optional[float] = Field(None, description="Override travel speed in mm/s.")
    stayAtHighestPossibleZ: bool = Field(
        False,
        description=(
            "If True, retracts to the highest possible Z and stays there "
            "instead of descending to the addressable area's height."
        ),
    )


class DeckPoint(BaseModel):
    """
    Coordinates of a point in deck space (mm).
    The origin (0, 0, 0) is the left-front-bottom corner of the workspace.
    """

    x: float = Field(..., description="X coordinate in mm.")
    y: float = Field(..., description="Y coordinate in mm.")
    z: float = Field(..., description="Z coordinate in mm.")

    model_config = {"extra": "forbid"}


class MoveToCoordinatesParams(BaseModel):
    """
    Payload required to move a pipette to specific absolute coordinates.
    Useful for calibration, custom hardware interaction, or sensor probing.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    coordinates: DeckPoint = Field(
        ..., description="Target X, Y, Z coordinates in mm from deck's origin."
    )
    minimumZHeight: Optional[float] = Field(
        None,
        description="Optional minimal Z margin in mm. Overrides default safe Z if larger.",
    )
    forceDirect: bool = Field(
        False,
        description=(
            "If True, moves directly to the target without arcing (X/Y/Z simultaneous). "
            "WARNING: Disables collision avoidance logic."
        ),
    )
    speed: Optional[float] = Field(
        None, description="Override the travel speed in mm/s."
    )

    model_config = {"extra": "forbid"}


class MaintenancePosition(str, Enum):
    ATTACH_PLATE = "attachPlate"
    ATTACH_INSTRUMENT = "attachInstrument"


class MoveToMaintenancePositionParams(BaseModel):
    """
    Payload required to move a specific mount to a maintenance coordinate.
    Useful for automated tool swapping or calibration routines.
    """

    mount: MountType = Field(..., description="The gantry mount (left/right) to move.")
    maintenancePosition: MaintenancePosition = Field(
        MaintenancePosition.ATTACH_INSTRUMENT,
        description="The specific maintenance configuration to move to.",
    )

    model_config = {"extra": "forbid"}


class MoveToParams(BaseModel):
    """
    Payload required to move a specific Mount (Left/Right/Gripper) to an absolute destination.

    WARNING: This moves the MOUNT to the coordinate, not the pipette tip.
    Use 'moveToCoordinates' if you want to position the tip at a specific point.
    """

    mount: MountType = Field(
        ..., description="The mount to move to the destination point."
    )
    destination: DeckPoint = Field(
        ..., description="Target X, Y, Z coordinates in mm from deck's origin."
    )
    speed: Optional[float] = Field(
        None, description="The max velocity (mm/s). Falls to hardware defaults if None."
    )

    model_config = {"extra": "forbid"}


class MoveToWellParams(BaseModel):
    """
    Payload required to move a pipette to a specific well.
    This calculates the target coordinates based on the labware definition and calibration.
    """

    pipetteId: str = Field(..., description="Identifier of pipette to use.")
    labwareId: str = Field(..., description="Identifier of the labware.")
    wellName: str = Field(..., description="Name of the well (e.g., 'A1').")
    wellLocation: Optional[LiquidHandlingWellLocation] = Field(
        None,
        description="Relative location within the well. Defaults to top-center if None.",
    )
    minimumZHeight: Optional[float] = Field(
        None, description="Optional minimal Z margin in mm for the arc."
    )
    forceDirect: bool = Field(
        False,
        description=(
            "If True, moves directly to the target without arcing. "
            "Dangerous if obstacles are present."
        ),
    )
    speed: Optional[float] = Field(None, description="Override travel speed in mm/s.")


class OpenGripperJawParams(BaseModel):
    """
    Payload required to open the gripper jaws to their maximum width.
    Used for releasing labware or preparing to engage a new plate.
    """

    model_config = {"extra": "forbid"}


class OpenLabwareLatchParams(BaseModel):
    """
    Input parameters to open the labware latch on a Heater-Shaker Module.
    The latch must be open before the Gripper can add or remove labware.
    """

    moduleId: str = Field(
        ..., description="The unique identifier of the loaded Heater-Shaker Module."
    )

    model_config = {"extra": "forbid"}


class PickUpTipWellOrigin(str, Enum):
    """The origin of a PickUpTipWellLocation offset."""

    TOP = "top"
    BOTTOM = "bottom"
    CENTER = "center"


class PickUpTipWellLocation(BaseModel):
    """
    A relative location in reference to a well's location
    specifically for tip pickup operations.
    """

    origin: PickUpTipWellOrigin = Field(
        PickUpTipWellOrigin.TOP, description="The reference point within the well."
    )
    offset: Optional[WellOffset] = Field(
        default_factory=lambda: WellOffset(x=0.0, y=0.0, z=0.0),
        description="Offset in mm from the origin point.",
    )


class PickUpTipParams(BaseModel):
    """
    Payload required to move a pipette to a specific well to pick up a tip.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    labwareId: str = Field(..., description="Identifier of the tip rack labware.")
    wellName: str = Field(
        ..., description="Name of the well (e.g., 'A1') containing the tip."
    )
    wellLocation: Optional[PickUpTipWellLocation] = Field(
        default_factory=PickUpTipWellLocation,
        description="Relative well location for the pickup.",
    )


class SessionCreateParams(BaseModel):
    """
    Parameters required to initiate Tip Length Calibration (TLC),
    Pipette Offset Calibration, or a combined session.
    """

    mount: MountType = Field(
        ..., description="The mount (left or right) where the pipette is attached."
    )
    hasCalibrationBlock: bool = Field(
        False,
        description="Whether to use a physical calibration block for the session.",
    )
    tipRackDefinition: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "Full labware definition of the tip rack. "
            "Defaults to existing calibration or pipette default if None."
        ),
    )
    shouldRecalibrateTipLength: bool = Field(
        True,
        description="Whether to perform TLC prior to recalibrating the pipette offset.",
    )

    model_config = {"extra": "forbid"}


class PipetteOffsetCalibrationCreateAttributes(BaseModel):
    """
    Attributes for a pipette offset calibration create request.
    Identifies the session type and provides necessary parameters.
    """

    sessionType: Literal["pipetteOffsetCalibration"] = Field(
        "pipetteOffsetCalibration",
        description="The type of calibration session to create.",
    )
    createParams: SessionCreateParams = Field(
        ..., description="Specific parameters for initializing the session."
    )

    model_config = {"extra": "forbid"}


class PrepareToAspirateParams(BaseModel):
    """
    Parameters required to prepare a specific pipette for aspiration.
    This command moves the plunger to the 'bottom' position so it is
    ready to draw liquid upward.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )

    model_config = {"extra": "forbid"}


class PressureDispenseParams(BaseModel):
    """
    Payload required to perform a pressure-controlled dispense.
    This is often used for high-accuracy dispensing or when
    monitoring for clogs and fluid resistance.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    labwareId: str = Field(..., description="Identifier of target labware.")
    wellName: str = Field(..., description="Name of well (e.g., 'B2').")
    wellLocation: Optional[LiquidHandlingWellLocation] = Field(
        default_factory=LiquidHandlingWellLocation,
        description="Relative well location for the dispense.",
    )
    flowRate: float = Field(
        ..., exclusiveMinimum=0, description="Speed in µL/s for the dispense action."
    )
    volume: float = Field(..., ge=0, description="Amount of liquid to dispense in µL.")
    correctionVolume: Optional[float] = Field(
        None,
        description="The volume correction in µL to account for system dead space or air gaps.",
    )

    model_config = {"extra": "forbid"}


class ReadAbsorbanceParams(BaseModel):
    """
    Input parameters for an absorbance reading using the Absorbance Reader Module.
    This triggers the optical sensor to capture data across the loaded plate.
    """

    moduleId: str = Field(
        ..., description="Unique ID of the loaded Absorbance Reader Module."
    )
    fileName: Optional[str] = Field(
        None,
        description=(
            "Optional file name to use when storing the measurement results "
            "on the robot's local storage."
        ),
    )

    model_config = {"extra": "forbid"}


class ReloadLabwareParams(BaseModel):
    """
    Payload required to refresh or 'reload' an existing labware instance.
    Commonly used when a human operator replaces an empty tip rack or plate
    during a protocol pause, allowing the system to reset its tip/well tracking.
    """

    labwareId: str = Field(
        ..., description="The ID of the already-loaded labware instance to update."
    )

    model_config = {"extra": "forbid"}


class RetractAxisParams(BaseModel):
    """
    Payload required to retract a specific axis to its home position.

    Retraction is optimized for speed. On the Flex, it moves the axis
    to the previously recorded home position at maximum safe velocity,
    whereas a 'home' command would perform a slower probe of the limit switch.
    """

    axis: MotorAxis = Field(
        ...,
        description=(
            "The specific motor axis to retract. Must have been "
            "previously homed to use this command."
        ),
    )

    model_config = {"extra": "forbid"}


class RetrieveParams(BaseModel):
    """
    Input parameters for a labware retrieval command from the Flex Stacker.
    This triggers the Stacker's internal elevator to move labware from
    a column to the transfer position.
    """

    moduleId: str = Field(..., description="Unique ID of the Flex Stacker module.")

    labwareId: Optional[str] = Field(
        None,
        description="DEPRECATED: Do not use. Present for internal backward compatibility.",
    )
    displayName: Optional[str] = Field(
        None,
        description="DEPRECATED: Do not use. Present for internal backward compatibility.",
    )
    adapterId: Optional[str] = Field(
        None,
        description="DEPRECATED: Do not use. Present for internal backward compatibility.",
    )
    lidId: Optional[str] = Field(
        None,
        description="DEPRECATED: Do not use. Present for internal backward compatibility.",
    )

    model_config = {"extra": "forbid"}


class ProfileStep(BaseModel):
    """
    An individual temperature step in a Thermocycler profile.
    """

    celsius: float = Field(
        ..., title="Celsius", description="Target temperature in °C."
    )
    holdSeconds: float = Field(
        ...,
        title="Hold Seconds",
        description="Time to hold target temperature in seconds.",
    )


class ProfileCycle(BaseModel):
    """
    A set of steps to be repeated a specific number of times.
    """

    steps: List[ProfileStep] = Field(
        ..., description="The sequence of steps to repeat in this cycle."
    )
    repetitions: int = Field(
        ..., ge=1, description="Number of times to repeat the steps."
    )


class RunExtendedProfileParams(BaseModel):
    """
    Input parameters to execute a complex thermal profile on the Thermocycler.
    """

    moduleId: str = Field(
        ..., description="Unique ID of the loaded Thermocycler Module."
    )
    profileElements: List[Union[ProfileStep, ProfileCycle]] = Field(
        ..., description="A list of steps or cycles that make up the thermal profile."
    )
    blockMaxVolumeUl: Optional[float] = Field(
        None,
        description=(
            "Maximum volume in µL in any single well. Used by the module "
            "to calculate ramp rates and prevent sample evaporation."
        ),
    )

    model_config = {"extra": "forbid"}


class RunProfileStepParams(BaseModel):
    """
    Input parameters for a standalone Thermocycler profile step.
    Differs from a basic 'set temperature' command by including
     a specific hold duration.
    """

    celsius: float = Field(
        ..., title="Celsius", description="Target temperature in °C."
    )
    holdSeconds: float = Field(
        ...,
        title="Hold Seconds",
        description="Time to hold the target temperature in seconds.",
    )

    model_config = {"extra": "forbid"}


class SavePositionParams(BaseModel):
    """
    Payload needed to record the pipette's current absolute coordinates.
    This is often used during calibration routines to save a 'taught' position
    into the Protocol Engine's state.
    """

    pipetteId: str = Field(
        ...,
        description="Unique identifier of the pipette whose position is being saved.",
    )
    positionId: Optional[str] = Field(
        None,
        description="Optional ID for this position record. A UUID is generated if not provided.",
    )
    failOnNotHomed: bool = Field(
        False,
        description=(
            "If True, the command will fail if any axis is unhomed. "
            "Ensures the saved coordinate is accurate relative to the deck origin."
        ),
    )

    model_config = {"extra": "forbid"}


class TipPickUpParams(BaseModel):
    """
    Advanced parameters for the physical engagement of a tip,
    including press force and speed.
    """

    force: Optional[float] = Field(None, description="Press force in Newtons.")
    speed: Optional[float] = Field(None, description="Approach speed in mm/s.")


# --- Seal Pipette to Tip Command ---


class SealPipetteToTipParams(BaseModel):
    """
    Payload required to seal specialized tips (like resin tips) to a pipette.
    This involves specific vertical force to ensure an airtight seal.
    """

    pipetteId: str = Field(
        ..., description="Identifier of pipette to use for liquid handling."
    )
    labwareId: str = Field(..., description="Identifier of tip rack labware.")
    wellName: str = Field(..., description="Name of the well containing the tip.")
    wellLocation: Optional[PickUpTipWellLocation] = Field(
        default_factory=PickUpTipWellLocation,
        description="Relative well location for the seal operation.",
    )
    tipPickUpParams: Optional[TipPickUpParams] = Field(
        None, description="Detailed force and speed parameters for tip engagement."
    )

    model_config = {"extra": "forbid"}


class SetAndWaitForShakeSpeedParams(BaseModel):
    """
    Input parameters for the Heater-Shaker Module to set a target RPM
    and block execution until that speed is reached.
    """

    moduleId: str = Field(
        ..., description="Unique ID of the loaded Heater-Shaker Module."
    )
    rpm: float = Field(
        ...,
        ge=200,
        le=3000,
        description="Target speed in rotations per minute (RPM). Typical range is 200-3000.",
    )

    model_config = {"extra": "forbid"}


class SetRailLightsParams(BaseModel):
    """
    Payload required to toggle the robot's interior rail lights.
    """

    on: bool = Field(..., description="True to turn lights on, False to turn them off.")

    model_config = {"extra": "forbid"}


class StatusBarAnimation(str, Enum):
    """Available animations for the Flex status bar."""

    IDLE = "idle"
    CONFIRM = "confirm"
    UPDATING = "updating"
    DISCO = "disco"
    OFF = "off"


class SetStatusBarParams(BaseModel):
    """
    Payload required to set the status bar to run a specific animation.
    Useful for providing visual cues to users in the lab.
    """

    animation: StatusBarAnimation = Field(
        ..., description="The animation that should be executed on the status bar."
    )

    model_config = {"extra": "forbid"}
