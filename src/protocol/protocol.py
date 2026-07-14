from pathlib import Path
from typing import List, Union

from pydantic import BaseModel

from src.protocol.instruction import Instruction


class Protocol(BaseModel):
    name: str
    instructions: List[Instruction]

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Protocol":
        with open(path, "r") as file:
            return cls.model_validate_json(file.read())
