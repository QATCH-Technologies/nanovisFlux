"""
src.opentrons_sdk.constants

Common HTTP constants for Opentrons

Author(s):
    Paul MacNichol (paul.macnichol@qatchtech.com)

Date:
    2026-02-02

Version:
    0.1.0
"""


class APIDefaults:
    PORT = 31950
    VERSION_HEADER = {"Opentrons-Version": "*", "Content-Type": "application/json"}
    DEFAULT_TIMEOUT = 30


class StatusCodes:
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    NOT_FOUND = 404
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422
    INTERNAL_SERVER_ERROR = 500


class Commands:
    [
        "airGapInPlace",
        "aspirate",
        "aspirateWhileTracking",
        "aspirateInPlace",
        "comment",
        "configureForVolume",
        "configureNozzleLayout",
        "custom",
        "dispense",
        "dispenseInPlace",
        "dispenseWhileTracking",
        "blowout",
        "blowOutInPlace",
        "dropTip",
        "dropTipInPlace",
        "home",
        "retractAxis",
        "loadLabware",
        "reloadLabware",
        "loadLiquid",
        "loadLiquidClass",
        "loadModule",
        "identifyModule",
        "loadPipette",
        "loadLidStack",
        "loadLid",
        "moveLabware",
        "moveRelative",
        "moveToCoordinates",
        "moveToWell",
        "moveToAddressableArea",
        "moveToAddressableAreaForDropTip",
        "prepareToAspirate",
        "waitForResume",
        "pause",
        "waitForDuration",
        "waitForTasks",
        "createTimer",
        "pickUpTip",
        "savePosition",
        "setRailLights",
        "touchTip",
        "setStatusBar",
        "verifyTipPresence",
        "getTipPresence",
        "getNextTip",
        "setTipState",
        "liquidProbe",
        "tryLiquidProbe",
        "sealPipetteToTip",
        "pressureDispense",
        "unsealPipetteFromTip",
        "captureImage",
        "heaterShaker/waitForTemperature",
        "heaterShaker/setTargetTemperature",
        "heaterShaker/deactivateHeater",
        "heaterShaker/setAndWaitForShakeSpeed",
        "heaterShaker/setShakeSpeed",
        "heaterShaker/deactivateShaker",
        "heaterShaker/openLabwareLatch",
        "heaterShaker/closeLabwareLatch",
        "magneticModule/disengage",
        "magneticModule/engage",
        "temperatureModule/setTargetTemperature",
        "temperatureModule/waitForTemperature",
        "temperatureModule/deactivate",
        "thermocycler/setTargetBlockTemperature",
        "thermocycler/waitForBlockTemperature",
        "thermocycler/setTargetLidTemperature",
        "thermocycler/waitForLidTemperature",
        "thermocycler/deactivateBlock",
        "thermocycler/deactivateLid",
        "thermocycler/openLid",
        "thermocycler/closeLid",
        "thermocycler/runProfile",
        "thermocycler/startRunExtendedProfile",
        "thermocycler/runExtendedProfile",
        "absorbanceReader/closeLid",
        "absorbanceReader/openLid",
        "absorbanceReader/initialize",
        "absorbanceReader/read",
        "flexStacker/retrieve",
        "flexStacker/store",
        "flexStacker/setStoredLabware",
        "flexStacker/fill",
        "flexStacker/empty",
        "calibration/calibrateGripper",
        "calibration/calibratePipette",
        "calibration/calibrateModule",
        "calibration/moveToMaintenancePosition",
        "unsafe/blowOutInPlace",
        "unsafe/dropTipInPlace",
        "unsafe/updatePositionEstimators",
        "unsafe/engageAxes",
        "unsafe/ungripLabware",
        "unsafe/placeLabware",
        "unsafe/flexStacker/manualRetrieve",
        "unsafe/flexStacker/closeLatch",
        "unsafe/flexStacker/openLatch",
        "unsafe/flexStacker/prepareShuttle",
        "robot/moveAxesRelative",
        "robot/moveAxesTo",
        "robot/moveTo",
        "robot/openGripperJaw",
        "robot/closeGripperJaw",
    ]
