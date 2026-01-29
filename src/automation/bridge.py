import asyncio
import logging

# Setup basic logging to console
from src.flex_controller.flex_controller import FlexController
from src.flex_controller.schemas import DoorState, EstopState, Subsystem

try:
    from src.common.log import get_logger

    log = get_logger("Bridge")
except ImportError:
    import logging

    log = logging.getLogger("Bridge")
ROBOT_IP = "169.254.143.61"


async def main():
    bot = FlexController("192.168.1.100")
    await bot.connect()

    print("--- 1. Hardware Discovery ---")
    instruments = await bot.hardware.get_instruments()
    left_physical = next(
        (i for i in instruments if i.mount == "left" and i.is_pipette), None
    )
    if not left_physical:
        print("Error: No pipette found on Left mount.")
        return

    pipette_model = left_physical.instrumentModel
    print(
        f"Found Physical Pipette: {pipette_model} (Serial: {left_physical.serialNumber})"
    )
    LOGICAL_ID = "active_pipette"
    try:
        load_result = await bot.runs.execute_maintenance_command(
            command_type="loadPipette",
            params={
                "pipetteName": pipette_model,
                "mount": "left",
                "pipetteId": LOGICAL_ID,
            },
            wait=True,
        )
        print(f"Pipette Loaded Successfully: {load_result}.")
        move_result = await bot.runs.execute_maintenance_command(
            command_type="moveToCoordinates",
            params={
                "pipetteId": LOGICAL_ID,
                "coordinates": {"x": 100.0, "y": 100.0, "z": 150.0},
                "minimumZHeight": 50.0,
            },
            wait=True,
        )
        print("Move Complete:", move_result)

    except Exception as e:
        print(f"Command Failed: {e}")

    await bot.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
