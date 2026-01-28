from src.flex_controller.flex_controller import FlexController


async def main():
    # Initialize once
    bot = FlexController("192.168.1.100")
    await bot.connect()

    # Access namespaces logically
    await bot.system.get_estop_status()
    await bot.hardware.identify(5)
    await bot.runs.execute_command("home", {"target": "robot"})
