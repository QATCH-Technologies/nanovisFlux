from enum import Enum


class APIDefaults:
    PORT = 31950
    VERSION_HEADER = {"Opentrons-Version": "*", "Content-Type": "application/json"}
    DEFAULT_TIMEOUT = 30


class Endpoints:
    # --- System & Connection ---
    HEALTH = "/health"
    NETWORKING_STATUS = "/networking/status"
    WIFI_LIST = "/wifi/list"
    WIFI_CONFIGURE = "/wifi/configure"
    WIFI_DISCONNECT = "/wifi/disconnect"
    WIFI_KEYS = "/wifi/keys"
    WIFI_EAP_OPTIONS = "/wifi/eap-options"
    SYSTEM_TIME = "/system/time"
    SETTINGS = "/settings"
    SETTINGS_ROBOT = "/settings/robot"
    SETTINGS_RESET_OPTIONS = "/settings/reset/options"
    SETTINGS_RESET = "/settings/reset"
    LOG_LEVEL_LOCAL = "/settings/log_level/local"

    # --- Hardware & Subsystems ---
    SUBSYSTEMS_STATUS = "/subsystems/status"
    SUBSYSTEMS_UPDATES_CURRENT = "/subsystems/updates/current"
    # Format with .format(subsystem=...)
    SUBSYSTEM_UPDATE = "/subsystems/updates/{subsystem}"
    MODULES = "/modules"
    # Format with .format(serial=...)
    MODULE_UPDATE = "/modules/{serial}/update"
    INSTRUMENTS = "/instruments"
    PIPETTES = "/pipettes"  # Legacy/Compat

    # --- Motor Controls ---
    MOTORS_ENGAGED = "/motors/engaged"
    MOTORS_DISENGAGED = "/motors/disengaged"
    ROBOT_LIGHTS = "/robot/lights"
    IDENTIFY = "/identify"

    # --- Safety ---
    ESTOP_STATUS = "/robot/control/estopStatus"
    ESTOP_ACK = "/robot/control/acknowledgeEstopDisengage"
    DOOR_STATUS = "/robot/door/status"

    # --- Runs & Protocol Engine ---
    RUNS = "/runs"
    MAINTENANCE_RUNS = "/maintenance_runs"
    MAINTENANCE_RUNS_CURRENT = "/maintenance_runs/current_run"
    PROTOCOLS = "/protocols"
    PROTOCOL_ANALYSES = "/protocols/{protocol_id}/analyses"
    COMMANDS = "/commands"  # Stateless/Simple commands
    RUN_ACTIONS = "/runs/{run_id}/actions"

    # --- Data & Configuration ---
    CLIENT_DATA = "/clientData"
    DATA_FILES = "/dataFiles"
    DECK_CONFIGURATION = "/deck_configuration"
    LABWARE_OFFSETS = "/labwareOffsets"
    LABWARE_OFFSETS_SEARCH = "/labwareOffsets/searches"

    # --- Calibration ---
    CALIBRATION_STATUS = "/calibration/status"
    CALIBRATION_PIPETTE_OFFSET = "/calibration/pipette_offset"
    CALIBRATION_TIP_LENGTH = "/calibration/tip_length"

    # --- Logging ---
    # Format with .format(log_type=...)
    LOGS_FETCH = "/logs/{log_type}"
