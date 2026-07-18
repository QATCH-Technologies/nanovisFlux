from __future__ import annotations
from dataclasses import dataclass
from ..geometry.coordinates import DeckPoint
from .base import Tool
from .tips import TipGeometry, TipPickup


@dataclass
class PlungerModel:
    """Maps volume (uL) to plunger microsteps. Calibrate microsteps_per_ul
    and the fully-dispensed position for your specific pipette."""
    microsteps_per_ul: float
    bottom_microsteps: int = 0  # plunger position for 0 uL

    def volume_to_microsteps(self, ul: float) -> int:
        return int(self.bottom_microsteps + round(ul * self.microsteps_per_ul))


class Pipette(Tool):
    """A single-channel pipette. Aspirate/dispense drive the plunger axis of
    whichever mount the pipette is attached to (B on the left, C on right).

    Once a tip is picked up, ``current_tip`` is set and the robot offsets all
    subsequent Z moves by the tip length so the tip *end* lands on target.
    """

    def __init__(self, name: str, plunger: PlungerModel, max_volume_ul: float):
        super().__init__()
        self.name = name
        self.plunger = plunger
        self.max_volume_ul = max_volume_ul
        self.current_volume_ul = 0.0
        self.current_tip: TipGeometry | None = None

    def uses_plunger(self) -> bool:
        return True

    def tip_offset_mm(self) -> float:
        """Length of the installed tip (0 when none) -- read by the robot to
        make Z moves place the tip end rather than the bare nozzle."""
        return self.current_tip.length_mm if self.current_tip else 0.0

    # -- plunger --------------------------------------------------------
    def _move_plunger_to(self, ul: float, feed=None) -> None:
        axis = self._mount.plunger
        target = self.plunger.volume_to_microsteps(ul)
        self._robot.controller.linear_move({axis: target}, feed=feed)

    def aspirate(self, ul: float, feed=None) -> None:
        if self.current_volume_ul + ul > self.max_volume_ul:
            raise ValueError("aspirate would exceed pipette capacity")
        self.current_volume_ul += ul
        self._move_plunger_to(self.current_volume_ul, feed)

    def dispense(self, ul: float | None = None, feed=None) -> None:
        ul = self.current_volume_ul if ul is None else ul
        self.current_volume_ul = max(0.0, self.current_volume_ul - ul)
        self._move_plunger_to(self.current_volume_ul, feed)

    def blow_out(self, feed=None) -> None:
        self.current_volume_ul = 0.0
        self._move_plunger_to(0.0, feed)

    # -- tips -----------------------------------------------------------
    def pick_up_tip(self, xy: DeckPoint, tip: TipGeometry, pickup: TipPickup) -> None:
        """Seat a tip by pressing onto it, over its position in the rack.

        No tip is installed during the strokes (offset 0), so Z is commanded
        against the bare nozzle reference. After the final stroke the tip is
        recorded and the mount lifts away with the tip-aware offset applied.
        """
        if self.current_tip is not None:
            raise RuntimeError("a tip is already attached; drop it first")
        robot, side = self._robot, self._mount.side
        top = pickup.press_z_mm

        # Arrive above the tip, then touch its top with the bare nozzle.
        robot.safe_move_to(DeckPoint(xy.x, xy.y, top), side)
        for stroke in range(pickup.presses):
            robot.move_vertical_to(top - pickup.engage_mm, side, feed=pickup.feed)
            if stroke < pickup.presses - 1:
                robot.move_vertical_to(top + pickup.retract_mm, side, feed=pickup.feed)

        self.current_tip = tip                     # now tip-aware
        robot.raise_z(side)                         # lift clear at travel height

    def drop_tip(self, xy: DeckPoint | None = None, eject_z_mm: float | None = None,
                 side_offset=None) -> None:
        """Eject the tip. On the plunger axes, tip ejection happens at the
        extreme down position (per the hardware notes), so this drives the
        plunger fully down when at the drop location."""
        if self.current_tip is None:
            raise RuntimeError("no tip to drop")
        robot, side = self._robot, self._mount.side
        if xy is not None and eject_z_mm is not None:
            robot.safe_move_to(DeckPoint(xy.x, xy.y, eject_z_mm), side)
        axis = self._mount.plunger
        limit = robot.axes[axis].config.endstop_limit  # extreme down = eject
        robot.controller.linear_move({axis: limit})
        self.current_tip = None
        self.current_volume_ul = 0.0
        self._move_plunger_to(0.0)                  # return plunger to top
        robot.raise_z(side)
