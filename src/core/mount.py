"""
Contains the available and valid types of mount positions on the gantry.
"""

from enum import Enum


class MountPosition(Enum):
    """Valid mount positions for tools on the machine.

    LEFT_PRIMARY/LEFT_SECONDARY/RIGHT_PRIMARY/RIGHT_SECONDARY ride on the
    gantry carriage and move with it. FRONT/REAR are bolted directly to the
    machine frame and never move.
    """

    LEFT_PRIMARY = "left_primary"
    LEFT_SECONDARY = "left_secondary"
    RIGHT_PRIMARY = "right_primary"
    RIGHT_SECONDARY = "right_secondary"
    FRONT = "front"
    REAR = "rear"

    def fixed(self) -> bool:
        """Whether this position is bolted to the machine frame rather than
        riding on the moving gantry carriage."""
        return self in (MountPosition.FRONT, MountPosition.REAR)
