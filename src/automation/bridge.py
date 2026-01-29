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

    try:
        print("Connecting to robot...")
        await bot.connect()
        print("--- System Status ---")
        sys_time = await bot.system.get_system_time()
        print(f"Robot Time: {sys_time.systemTime} (Synced: {sys_time.synchronized})")
        ret = await bot.runs.execute_maintenance_command(
            "moveToCoordinates",
            {"mount": "left", "point": [100, 100, 0], "target": "mount"},
            wait=True,
            intent="protocol",
        )
        # ret = await bot.runs.execute_maintenance_command(
        #     "commands",
        #     wait=True,
        # )
        print(ret)
    except Exception as e:
        log.critical(f"Bridge Script Crashed: {e}", exc_info=True)

    finally:
        print("Disconnecting...")
        await bot.disconnect()
        print("--- Demo Complete ---")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
