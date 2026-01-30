# flex_endpoints.py
class Endpoints:
    class Networking:
        """Endpoints for network configuration and status."""

        STATUS = "/networking/status"
        WIFI_LIST = "/wifi/list"
        WIFI_CONFIGURE = "/wifi/configure"
        WIFI_KEYS = "/wifi/keys"
        WIFI_KEY_DELETE = "/wifi/keys/{key_uuid}"
        EAP_OPTIONS = "/wifi/eap-options"
        DISCONNECT = "/wifi/disconnect"

    class RobotControl:
        """Endpoints for physical robot movement and state."""

        HEALTH = "/health"
        IDENTIFY = "/identify"
        POSITIONS = "/robot/positions"
        MOVE = "/robot/move"
        HOME = "/robot/home"
        LIGHTS = "/robot/lights"
        MOTORS_ENGAGED = "/motors/engaged"
        MOTORS_DISENGAGE = "/motors/disengage"
        ESTOP_STATUS = "/robot/control/estopStatus"
        ESTOP_ACKNOWLEDGE = "/robot/control/acknowledgeEstopDisengage"
        DOOR_STATUS = "/robot/door/status"

    class Protocols:
        """Endpoints for managing protocol files and analyses."""

        CREATE = "/protocols"
        GET_ALL = "/protocols"
        GET_IDS = "/protocols/ids"
        GET_BY_ID = "/protocols/{protocolId}"
        DELETE = "/protocols/{protocolId}"

        # Analysis
        CREATE_ANALYSIS = "/protocols/{protocolId}/analyses"
        GET_ANALYSES = "/protocols/{protocolId}/analyses"
        GET_ANALYSIS_ID = "/protocols/{protocolId}/analyses/{analysisId}"
        GET_AS_DOCUMENT = "/protocols/{protocolId}/analyses/{analysisId}/asDocument"
        GET_DATA_FILES = "/protocols/{protocolId}/dataFiles"

    class Runs:
        """Endpoints for the run engine (executing protocols)."""

        CREATE = "/runs"
        GET_ALL = "/runs"
        GET_ID = "/runs/{runId}"
        DELETE = "/runs/{runId}"
        UPDATE = "/runs/{runId}"

        # Run Control & State
        ACTIONS = "/runs/{runId}/actions"
        CURRENT_STATE = "/runs/{runId}/currentState"
        COMMAND_ERRORS = "/runs/{runId}/commandErrors"
        ERROR_RECOVERY_POLICY = "/runs/{runId}/errorRecoveryPolicy"

        # Run Commands
        COMMANDS_CREATE = "/runs/{runId}/commands"
        COMMANDS_GET = "/runs/{runId}/commands"
        COMMANDS_GET_ID = "/runs/{runId}/commands/{commandId}"
        COMMANDS_PRESERIALIZED = "/runs/{runId}/commandsAsPreSerializedList"

        # Labware Context
        LABWARE_OFFSETS = "/runs/{runId}/labware_offsets"
        LABWARE_DEFS = "/runs/{runId}/labware_definitions"
        LOADED_LABWARE = "/runs/{runId}/loaded_labware_definitions"

    class MaintenanceRuns:
        """Endpoints for maintenance specific runs."""

        CREATE = "/maintenance_runs"
        CURRENT = "/maintenance_runs/current_run"
        GET_ID = "/maintenance_runs/{runId}"
        DELETE = "/maintenance_runs/{runId}"
        COMMANDS = "/maintenance_runs/{runId}/commands"
        COMMAND_ID = "/maintenance_runs/{runId}/commands/{commandId}"
        LABWARE_OFFSETS = "/maintenance_runs/{runId}/labware_offsets"
        LABWARE_DEFS = "/maintenance_runs/{runId}/labware_definitions"

    class SystemSettings:
        """Endpoints for general robot configuration."""

        SETTINGS_CHANGE = "/settings"
        SETTINGS_GET = "/settings"
        LOG_LEVEL_LOCAL = "/settings/log_level/local"
        LOG_LEVEL_UPSTREAM = "/settings/log_level/upstream"
        RESET_OPTIONS = "/settings/reset/options"
        RESET = "/settings/reset"
        ROBOT_SETTINGS = "/settings/robot"
        SYSTEM_TIME = "/system/time"
        DECK_CONFIG = "/deck_configuration"
        ERROR_RECOVERY = "/errorRecovery/settings"

    class Components:
        """Endpoints for attached hardware (Pipettes, Modules, Instruments)."""

        PIPETTES_ATTACHED = "/pipettes"
        PIPETTE_SETTINGS = "/settings/pipettes"
        PIPETTE_ID_SETTING = "/settings/pipettes/{pipette_id}"
        MODULES_ATTACHED = "/modules"
        MODULE_COMMAND = "/modules/{serial}"
        MODULE_UPDATE = "/modules/{serial}/update"
        INSTRUMENTS = "/instruments"
        SUBSYSTEMS_STATUS = "/subsystems/status"
        SUBSYSTEM_ID = "/subsystems/status/{subsystem}"
        SUBSYSTEM_UPDATES = "/subsystems/updates/all"

    class Calibration:
        """Endpoints for calibration data and sessions."""

        STATUS = "/calibration/status"
        PIPETTE_OFFSET = "/calibration/pipette_offset"
        TIP_LENGTH = "/calibration/tip_length"
        LABWARE_CALIBRATIONS = "/labware/calibrations"
        LABWARE_CALIBRATION_ID = "/labware/calibrations/{calibrationId}"
        SESSIONS_CREATE = "/sessions"
        SESSIONS_ID = "/sessions/{sessionId}"
        SESSION_COMMAND = "/sessions/{sessionId}/commands/execute"

    class Data:
        """Endpoints for file management and logs."""

        LOGS = "/logs/{log_identifier}"
        CAMERA_PICTURE = "/camera/picture"
        CLIENT_DATA = "/clientData"
        CLIENT_DATA_KEY = "/clientData/{key}"
        DATA_FILES = "/dataFiles"
        DATA_FILE_ID = "/dataFiles/{dataFileId}"
        DATA_FILE_DOWNLOAD = "/dataFiles/{dataFileId}/download"
        LABWARE_OFFSETS = "/labwareOffsets"
        LABWARE_OFFSET_SEARCH = "/labwareOffsets/searches"
        LABWARE_OFFSET_ID = "/labwareOffsets/{id}"
        COMMAND_QUEUE = "/commands"
        COMMAND_ID = "/commands/{commandId}"
