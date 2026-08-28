"""One-off diagnostic: is the trash-drop point (slot 12 + offset) reachable
under the CURRENT configs/calibration.yaml? Prints the computed motor
target for the configured offset plus a few smaller candidates closer to
slot 12's front-left corner (still clear of its 37.5x37mm obstacle block),
so a reachable one can be picked without another trial-and-error hardware
run. Doesn't move anything -- pure calibration math."""
from __future__ import annotations

from src.config.loader import build_axes, build_calibration, build_deck, resolve_robot_config
from src.core import AxisId, MountSide
from src.geometry.coordinates import DeckPoint

cfg = resolve_robot_config("configs/robot.yaml")
cal = build_calibration(cfg["calibration"])
deck = build_deck(cfg["deck"])
axes = build_axes(cfg.get("axes", {}))
x_limit = axes[AxisId.X].endstop_limit
y_limit = axes[AxisId.Y].endstop_limit
origin = deck["12"].origin

candidates = [
    (100.0, 100.0),  # current _TRASH_OFFSET in nanovis_transfer_example.py
    (60.0, 60.0),
    (45.0, 45.0),
    (45.0, 80.0),
    (80.0, 45.0),
]

print(f"slot 12 origin: {origin}")
print(f"axis travel range: X [0, {x_limit}], Y [0, {y_limit}]")
print(f"{'offset':>14}  {'deck xy':>18}  {'motor X':>9}  {'motor Y':>9}  reachable?")
for ox, oy in candidates:
    point = DeckPoint(origin.x + ox, origin.y + oy, 0.0)
    targets = cal.deck_to_motor(point, MountSide.LEFT)
    mx, my = targets[AxisId.X], targets[AxisId.Y]
    ok = 0 <= mx <= x_limit and 0 <= my <= y_limit
    print(f"({ox:>5},{oy:>5})  ({point.x:>7.1f},{point.y:>7.1f})  {mx:>9}  {my:>9}  {'YES' if ok else 'no'}")
