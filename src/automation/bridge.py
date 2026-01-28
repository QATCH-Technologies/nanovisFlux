import asyncio
import logging

# Setup basic logging to console
from src.flex_controller.flex_controller import FlexController
from src.flex_controller.schemas import DoorState, EstopState

try:
    from src.common.log import get_logger

    log = get_logger("Bridge")
except ImportError:
    import logging

    log = logging.getLogger("Bridge")
ROBOT_IP = "192.168.1.100"  # Replace with your actual Robot IP


async def main():
    log.info("--- Starting Flex Bridge Demo ---")

    # 1. Initialize Controller (Singleton)
    bot = FlexController(ROBOT_IP)

    try:
        # 2. Connection & Health
        log.info("Connecting to robot...")
        await bot.connect()

        # 3. System Namespace Checks
        log.info("--- System Status ---")

        # Time Sync Check
        sys_time = await bot.system.get_system_time()
        log.info(f"Robot Time: {sys_time.systemTime} (Synced: {sys_time.synchronized})")

        # Safety Checks
        estop = await bot.system.get_estop_status()
        door = await bot.system.get_door_status()

        if estop.status != EstopState.DISENGAGED:
            log.warning(f"E-STOP IS ENGAGED: {estop.status}")
            # Optional: Attempt to clear if logically engaged
            # await bot.system.acknowledge_estop_disengage()
        else:
            log.info("E-Stop is disengaged.")

        if door.status == DoorState.OPEN:
            log.warning("Front Door is OPEN.")
        else:
            log.info("Front Door is closed.")

        # 4. Hardware Namespace Checks
        log.info("--- Hardware Inventory ---")

        # Visual ID
        log.info("Blinking lights to identify robot...")
        await bot.hardware.identify(seconds=3)

        # Instruments (Pipettes/Grippers)
        instruments = await bot.hardware.get_instruments()
        if not instruments:
            log.warning("No instruments detected!")
        for instr in instruments:
            status_icon = "GOOD" if instr.ok else "BAD"
            log.info(
                f"{status_icon} Found {instr.instrumentType}: {instr.instrumentModel} on {instr.mount}"
            )

        # Modules
        modules = await bot.hardware.get_modules()
        log.info(f"Attached Modules: {len(modules)}")
        for mod in modules:
            log.info(f"   - {mod.get('model')} ({mod.get('serial')})")

        # Subsystems (Firmware Health)
        subsystems = await bot.hardware.get_all_subsystems()
        updates_needed = [s.name for s in subsystems if s.fw_update_needed]
        if updates_needed:
            log.error(f"Firmware updates required for: {updates_needed}")
        else:
            log.info("All subsystem firmware is up to date.")

        # 5. Calibration Namespace Checks
        log.info("--- Calibration Data ---")

        deck_config = await bot.calibration.get_deck_configuration()
        log.info(f"Deck Config Last Modified: {deck_config.lastModifiedAt}")

        # 6. Run/Motion Namespace Checks
        log.info("--- Motion Control ---")

        # Only attempt motion if safety checks passed
        if estop.status == EstopState.DISENGAGED and door.status == DoorState.CLOSED:
            log.info("Homing Robot (Stateless Command)...")
            try:
                # 'wait=True' ensures we block here until homing is finished
                await bot.runs.execute_stateless_command(
                    "home", {"target": "robot"}, wait=True
                )
                log.info("Homing Complete.")
            except Exception as e:
                log.error(f"Homing Failed: {e}")
        else:
            log.error("Skipping motion commands due to Safety/Door status.")

    except Exception as e:
        log.critical(f"Bridge Script Crashed: {e}", exc_info=True)

    finally:
        # 7. Cleanup
        log.info("Disconnecting...")
        await bot.disconnect()
        log.info("--- Demo Complete ---")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
