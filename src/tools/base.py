from abc import ABC
from typing import Callable, Dict, Type

from src.core.motion import MotionController
from src.utils.logger import logger


class Tool(ABC):
    """
    Only unifies mount_axis, motion, and from_config. Action methods are
    NOT part of this interface -- each tool exposes its own heterogeneous
    actions (aspirate/dispense vs. probe/is_active), dispatched by name
    (getattr) by the protocol runner rather than through a shared execute().
    """

    def __init__(self, mount_axis: str, motion: MotionController):
        self.mount_axis = mount_axis.upper()
        self.motion = motion

    @classmethod
    def from_config(cls, tool_data: dict, motion: MotionController) -> "Tool":
        raise NotImplementedError


_TOOL_REGISTRY: Dict[str, Type[Tool]] = {}


def register_tool(tool_type: str) -> Callable[[Type[Tool]], Type[Tool]]:
    def decorator(tool_cls: Type[Tool]) -> Type[Tool]:
        _TOOL_REGISTRY[tool_type] = tool_cls
        return tool_cls

    return decorator


def create_tool(tool_type: str, tool_data: dict, motion: MotionController) -> Tool:
    if tool_type not in _TOOL_REGISTRY:
        raise ValueError(
            f"Unknown tool type '{tool_type}'. Registered types: {sorted(_TOOL_REGISTRY.keys())}."
        )
    tool_cls = _TOOL_REGISTRY[tool_type]
    logger.debug(f"Creating tool of type '{tool_type}' via {tool_cls.__name__}.from_config().")
    return tool_cls.from_config(tool_data, motion)
