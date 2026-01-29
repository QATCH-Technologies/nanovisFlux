import asyncio
import re

from src.flex_controller.flex_controller import FlexController


def map_pipette_model(hardware_model: str) -> str:
    model = hardware_model.lower()
    if "p1000_96" in model:
        return "p1000_96"
    if "p200_96" in model:
        return "p200_96"
    if "flex" in model:
        return model
    if "p50" in model:
        if "multi" in model:
            return "p50_multi_flex"
        return "p50_single_flex"
    if "p1000" in model:
        if "multi" in model:
            return "p1000_multi_flex"
        return "p1000_single_flex"
    return model


async def main():
    bot = FlexController("169.254.143.61")
    await bot.connect()

    try:
        instruments = await bot.hardware.get_instruments()
        print(f"Found instruments:\n{instruments}")
        left_physical = next(
            (i for i in instruments if i.mount == "left" and i.is_pipette), None
        )

        if not left_physical:
            print("Error: No pipette found on Left mount.")
            return
        hardware_name = left_physical.instrumentModel
        load_name = map_pipette_model(hardware_name)

        print(f"Found Physical: {hardware_name} (Serial: {left_physical.serialNumber})")
        print(f"Mapped Load Name: {load_name}")

        LOGICAL_ID = "active_pipette"

        load_result = await bot.runs.execute_maintenance_command(
            command_type="loadPipette",
            params={
                "pipetteName": load_name,
                "mount": "left",
                "pipetteId": LOGICAL_ID,
            },
            wait=True,
        )
        print(f"Pipette Loaded Successfully: {load_result}.")
        await bot.runs.execute_maintenance_command(
            command_type="home", params={"target": "robot"}, wait=True
        )
        # move_result = await bot.runs.execute_maintenance_command(
        #     command_type="moveToCoordinates",
        #     params={
        #         "pipetteId": LOGICAL_ID,
        #         "coordinates": {"x": 50.0, "y": 200.0, "z": 150.0},
        #         "minimumZHeight": 50.0,
        #     },
        #     wait=True,
        # )
        # print("Move Complete:", move_result)

    except Exception as e:
        print(f"Command Failed: {e}")

    finally:
        print("\nClosing connection...")
        await bot.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
