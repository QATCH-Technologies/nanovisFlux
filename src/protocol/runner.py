from src.core.robot import Robot
from src.protocol.instruction import Instruction
from src.protocol.protocol import Protocol
from src.utils.logger import logger


class ProtocolRunner:
    def __init__(self, robot: Robot):
        self.robot = robot

    def run(self, protocol: Protocol) -> None:
        count = len(protocol.instructions)
        logger.info(f"Running protocol '{protocol.name}' ({count} instructions).")
        for index, instruction in enumerate(protocol.instructions):
            self.run_instruction(instruction, index)
        logger.info(f"Protocol '{protocol.name}' complete.")

    def run_instruction(self, instruction: Instruction, index: int = 0) -> None:
        logger.info(f"[{index}] {instruction.name or instruction.action}")

        if instruction.location is not None:
            self.robot.move_to_location(instruction.location, speed=instruction.speed)

        tool = self.robot.get_tool(instruction.tool_side)
        action = getattr(tool, instruction.action, None)
        if not callable(action):
            raise AttributeError(
                f"Tool on '{instruction.tool_side}' mount has no action '{instruction.action}'."
            )
        action(**instruction.params)
