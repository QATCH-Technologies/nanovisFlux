from src.common.motion import MotionController
from src.core.mount import MountPosition
from src.tools.base import Tool, register_tool


@register_tool("empty")
class Empty(Tool):
    """Placeholder tool for a mount position with nothing physically
    installed."""

    def __init__(self, mount_axis: str, motion: MotionController, mount_position: MountPosition):
        super().__init__(mount_axis=mount_axis, motion=motion)
        self.mount_position = mount_position

    @classmethod
    def from_config(cls, tool_data: dict, motion: MotionController) -> "Empty":
        return cls(
            mount_axis=tool_data.get("mount_axis", ""),
            motion=motion,
            mount_position=MountPosition(tool_data["position"]),
        )
