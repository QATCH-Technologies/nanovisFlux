from abc import ABC, abstractmethod
from typing import Tuple


class Surface(ABC):
    def __init__(self, name: str, x_offset: float, y_offset: float, z_offset: float):
        """
        Base geometry for any physical object on the robot deck.
        Coordinates typically represent the bottom-left-front origin of the object's footprint.
        """
        self.name = name
        self.x = x_offset
        self.y = y_offset
        self.z = z_offset

    @property
    @abstractmethod
    def bounding_box(self) -> Tuple[float, float, float]:
        """
        Returns the (width, depth, height) of the physical object in mm.
        Essential for collision detection and calculating safe travel heights.
        """
        pass

    @property
    def safe_z(self) -> float:
        """
        Calculates the absolute Z-height required to safely traverse over this surface.
        Defaults to the object's physical height plus a configurable clearance buffer.
        """
        _, _, height = self.bounding_box
        return self.z + height + 5.0
