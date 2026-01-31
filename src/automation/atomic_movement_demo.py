import asyncio
import re

from src.opentrons_sdk.flex_controller import FlexController


async def main():
    bot = FlexController("169.254.143.61")
    await bot.connect()

    try:
        bot_health = await bot.health.get_health()
        print(bot_health)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("\nClosing connection...")
        await bot.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
