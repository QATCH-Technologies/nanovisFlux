"""
Handles what is mounted on the gantry using the mount positions and controls mount availability

class Gantry
    set of Mounts available and what is mounted at each slot.
"""

from typing import Any, Dict, Iterable, List, Optional

from src.core.mount import MountPosition
from src.utils.logger import logger


class Gantry:
    """Tracks which MountPosition slots exist on this machine and what tool
    (if anything) currently occupies each one."""

    def __init__(self, available_mounts: Optional[Iterable[MountPosition]] = None):
        positions = list(available_mounts) if available_mounts is not None else list(MountPosition)
        self._occupants: Dict[MountPosition, Optional[Any]] = {position: None for position in positions}

    def available_mounts(self) -> List[MountPosition]:
        return list(self._occupants.keys())

    def is_mounted(self, position: MountPosition) -> bool:
        return self._get_slot(position) is not None

    def mount(self, position: MountPosition, tool: Any) -> None:
        self._check_known(position)
        if self._occupants[position] is not None:
            raise RuntimeError(f"Mount position {position} already has a tool mounted.")
        self._occupants[position] = tool
        logger.debug(f"Mounted {tool!r} at {position}.")

    def unmount(self, position: MountPosition) -> Any:
        tool = self._get_slot(position)
        if tool is None:
            raise RuntimeError(f"Mount position {position} has no tool mounted.")
        self._occupants[position] = None
        logger.debug(f"Unmounted {tool!r} from {position}.")
        return tool

    def get(self, position: MountPosition) -> Optional[Any]:
        return self._get_slot(position)

    def _get_slot(self, position: MountPosition) -> Optional[Any]:
        self._check_known(position)
        return self._occupants[position]

    def _check_known(self, position: MountPosition) -> None:
        if position not in self._occupants:
            raise KeyError(f"Mount position {position} is not available on this gantry.")
