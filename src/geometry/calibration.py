from __future__ import annotations
from dataclasses import dataclass, field
from ..core import AxisId, MountSide
from .coordinates import DeckPoint
from .transform import AffineTransform2D
from .units import AxisScale


@dataclass
class DeckCalibration:
    """The bridge between deck space (mm) and motor space (microsteps).

    XY is a full affine transform learned from calibration points. Z is a
    per-mount linear map: a reference microstep value at deck z = 0 plus a
    scale. Home is up, so descending toward the deck increases microsteps.
    """
    xy: AffineTransform2D
    z_scale: AxisScale
    z_zero: dict = field(default_factory=dict)  # MountSide -> microsteps at deck z=0

    def vertical_axis(self, side: MountSide) -> AxisId:
        return AxisId.Z if side is MountSide.LEFT else AxisId.A

    def deck_to_motor(self, point: DeckPoint, side: MountSide,
                      tip_length_mm: float = 0.0) -> dict:
        """Motor targets that place the *working point* at ``point`` (deck mm).

        ``z_zero`` is the nozzle-reference position (tip-independent), so the
        tip end is ``tip_length_mm`` below the nozzle. To land the tip end at
        ``point.z`` the nozzle must sit ``tip_length_mm`` higher, i.e. fewer
        microsteps (home is up). One calibration serves every tip length.
        """
        mx, my = self.xy.apply(point.x, point.y)
        vertical = self.vertical_axis(side)
        zref = self.z_zero.get(side, 0)
        mz = zref - self.z_scale.to_microsteps(point.z + tip_length_mm)
        return {AxisId.X: round(mx), AxisId.Y: round(my), vertical: int(mz)}

    def z_zero_from_contact(self, contact_microsteps: int,
                            tip_length_mm: float = 0.0) -> int:
        """Given the microsteps at which a probe of length ``tip_length_mm``
        touched deck z = 0, return the nozzle-reference ``z_zero``.

        At contact the tip end is on the surface, so the nozzle reference is
        ``tip_length_mm`` above it: ``z_zero = contact + msteps(tip_length)``.
        """
        return int(contact_microsteps + self.z_scale.to_microsteps(tip_length_mm))

    def motor_to_deck_xy(self, mx: float, my: float) -> tuple:
        return self.xy.inverse().apply(mx, my)

    @classmethod
    def from_points(cls, deck_pts, motor_xy, z_scale, z_zero=None) -> "DeckCalibration":
        xy = AffineTransform2D.from_point_pairs(
            [(p.x, p.y) for p in deck_pts], list(motor_xy))
        return cls(xy=xy, z_scale=z_scale, z_zero=z_zero or {})
