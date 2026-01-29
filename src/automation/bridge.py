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
    print("--- Starting Flex Bridge Demo ---")

    bot = FlexController(ROBOT_IP)
    instruments = await bot.hardware.get_instruments()

    # Find the pipette on the left mount
    left_pipette = next(
        (i for i in instruments if i.mount == "left" and i.is_pipette), None
    )

    if not left_pipette:
        print("Error: No pipette found on Left mount.")
        return

    print(f"Using Pipette ID: {left_pipette.serialNumber}")

    # 2. Execute Move with Correct Structure
    # API expects:
    # - pipetteId: UUID string
    # - coordinates: {x, y, z} dictionary
    # - minimumZHeight: (Optional) float

    try:
        ret = await bot.runs.execute_maintenance_command(
            command_type="moveToCoordinates",
            params={
                "pipetteId": left_pipette.serialNumber,  # Use the UUID, not "left"
                "coordinates": {"x": 100.0, "y": 100.0, "z": 50.0},
                "minimumZHeight": 50.0,
            },
            wait=True,
            intent="setup",
        )
        print("Command Success:", ret)

    except Exception as e:
        print(f"Command Failed: {e}")

    await bot.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
