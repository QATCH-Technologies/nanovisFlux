from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from src.core.deck import DeckLocation


class Instruction(BaseModel):
    """
    One high-level protocol entry. Deliberately named Instruction, not
    'Step' -- 'step'/'microstep' already means motor step throughout this
    codebase (see src.backend.dispatcher).
    """

    name: str = ""
    tool_side: Literal["left", "right"]
    action: str
    location: Optional[DeckLocation] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    speed: Optional[float] = None
