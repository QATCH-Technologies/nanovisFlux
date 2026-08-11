"""Raster-scans the rear ultrasonic sensor (see src/tools/ultrasonic.py)
across the deck's X/Y plane and builds a top-down topographical map from
the range readings.

The sensor is fixed to the gantry frame behind the Z/A mounts and has no
vertical axis of its own (MountSide.REAR -- see src/core.py and
src/motion/mounts.py), so this script only ever drives X/Y: at each grid
point it moves the gantry, lets vibration settle, and takes one M412 range
reading (Controller.measure_distance / UltrasonicSensor.read_distance_mm).
Z and A (if anything is mounted there) are raised to travel_z_mm first,
purely so a mounted pipette/probe stays clear of labware during the scan --
they play no other part in it.

Output:
  - a CSV of every (x_mm, y_mm, distance_mm) reading (--out)
  - an ASCII heatmap printed to the terminal
  - optionally a PNG heatmap (--png), if matplotlib is installed

Runs against the in-memory FakeTransport by default (no hardware needed):
without --config it also fabricates a smooth synthetic surface so the
heatmap/PNG output can be exercised end-to-end. Pass --port for real
hardware, or --config to load a full robot (calibration + a configured rear
ultrasonic mount -- see src/config/robot.example.yaml).
"""

from __future__ import annotations

import argparse
import csv
import math
import time

from src.config.loader import load_robot
from src.core import MountSide
from src.geometry import AffineTransform2D, AxisScale, DeckCalibration, DeckPoint
from src.robot import Robot
from src.tools import UltrasonicSensor
from src.transport import FakeTransport, SerialTransport

_ASCII_RAMP = " .:-=+*#%@"


def _frange(start: float, stop: float, step: float) -> list:
    """Evenly spaced points from start to stop inclusive, spaced as close to
    `step` as an integer point count allows (avoids float drift landing just
    short of `stop`)."""
    if stop <= start:
        return [start]
    count = max(1, round((stop - start) / step)) + 1
    actual_step = (stop - start) / (count - 1)
    return [start + i * actual_step for i in range(count)]


def synthetic_height_mm(x: float, y: float) -> float:
    """A smooth rolling surface around a nominal standoff -- stand-in terrain
    for exercising the scan/heatmap pipeline without real hardware."""
    base = 300.0
    bump = 40.0 * math.sin(x / 60.0) * math.cos(y / 45.0)
    return max(20.0, base - bump)


def scan_topography(
    robot: Robot,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    step_mm: float,
    feed: int | None = None,
    settle_s: float = 0.05,
    before_read=None,
    on_point=None,
):
    """Boustrophedon (snake) raster scan over [x_min, x_max] x [y_min, y_max].

    Returns (grid, xs, ys) where grid[row][col] is the distance_mm (or None
    on no echo/out of range) at (xs[col], ys[row]). Snaking only changes
    travel order, not the returned layout, which is always in xs/ys order.
    """
    sensor = robot.rear()
    if sensor is None:
        raise RuntimeError("no ultrasonic sensor attached to the rear mount (MountSide.REAR)")

    xs, ys = _frange(x_min, x_max, step_mm), _frange(y_min, y_max, step_mm)
    grid = [[None] * len(xs) for _ in ys]

    for row, y in enumerate(ys):
        cols = range(len(xs)) if row % 2 == 0 else range(len(xs) - 1, -1, -1)
        for col in cols:
            x = xs[col]
            # move_to now handles a vertical-axis-less mount (REAR) cleanly
            # -- deck_to_motor omits the Z/A target instead of crashing --
            # and applies REAR's fixed offset from the gantry reference, so
            # this drives the sensor itself to (x, y), not just the gantry.
            robot.move_to(DeckPoint(x, y), MountSide.REAR, feed=feed)
            if settle_s:
                time.sleep(settle_s)
            if before_read:
                before_read(x, y)
            distance = sensor.read_distance_mm()
            grid[row][col] = distance
            if on_point:
                on_point(row, col, x, y, distance)
    return grid, xs, ys


def write_csv(path: str, grid: list, xs: list, ys: list) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["x_mm", "y_mm", "distance_mm"])
        for row, y in enumerate(ys):
            for col, x in enumerate(xs):
                v = grid[row][col]
                w.writerow([x, y, "" if v is None else v])


def render_ascii(grid: list, xs: list, ys: list) -> str:
    values = [v for row in grid for v in row if v is not None]
    if not values:
        return "(no in-range readings)"
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    lines = []
    for row in reversed(grid):  # print with y increasing upward
        chars = [
            "?" if v is None else _ASCII_RAMP[int((v - lo) / span * (len(_ASCII_RAMP) - 1))]
            for v in row
        ]
        lines.append("".join(chars))
    lines.append(
        f"(range {lo:.1f}-{hi:.1f} mm; closer = '{_ASCII_RAMP[0]}', farther = '{_ASCII_RAMP[-1]}'; "
        f"'?' = no echo)"
    )
    return "\n".join(lines)


def save_png(path: str, grid: list, xs: list, ys: list) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return False
    arr = np.array([[float("nan") if v is None else v for v in row] for row in grid])
    fig, ax = plt.subplots()
    im = ax.imshow(
        arr, origin="lower", extent=(xs[0], xs[-1], ys[0], ys[-1]), cmap="viridis", aspect="auto"
    )
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title("Deck topography (ultrasonic range, mm)")
    fig.colorbar(im, ax=ax, label="distance (mm)")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def build_robot(port: str | None, config: str | None):
    """Returns (robot, fake_transport). fake_transport is the FakeTransport
    instance when one was built here (so main() can feed it synthetic
    terrain for the no-hardware demo), or None for --config/--port."""
    if config:
        return load_robot(config), None

    transport = SerialTransport(port) if port else FakeTransport()

    # Placeholder calibration -- replace with points/z_zero captured for
    # this machine (see src/config/robot.example.yaml for field meanings).
    # Only the XY affine actually matters for this script.
    calibration = DeckCalibration(
        xy=AffineTransform2D.from_point_pairs(
            [(0, 0), (100, 0), (0, 100)], [(0, 0), (21320, 0), (0, 14478)]
        ),
        z_scale=AxisScale(steps_per_mm=25.0),
        z_zero={MountSide.LEFT: 144000, MountSide.RIGHT: 144000},
    )

    robot = Robot(transport, calibration=calibration, travel_z_mm=120)
    robot.attach(MountSide.REAR, UltrasonicSensor())
    return robot, (transport if isinstance(transport, FakeTransport) else None)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--port", help="serial port for real hardware (e.g. COM6); omit to use the fake transport"
    )
    parser.add_argument(
        "--config",
        help="robot config YAML to load (calibration + rear ultrasonic mount); "
        "omit for a bare placeholder-calibration robot",
    )
    parser.add_argument("--x-min", type=float, default=0.0)
    parser.add_argument("--x-max", type=float, default=360.0)
    parser.add_argument("--y-min", type=float, default=0.0)
    parser.add_argument("--y-max", type=float, default=310.0)
    parser.add_argument("--step-mm", type=float, default=20.0, help="grid spacing between readings")
    parser.add_argument(
        "--feed",
        type=int,
        help="travel feed rate, microsteps/sec, between points; omit for rapid (G0) moves",
    )
    parser.add_argument(
        "--settle-s",
        type=float,
        default=0.05,
        help="pause after each move before reading, to let vibration settle",
    )
    parser.add_argument("--out", default="scan_topography.csv", help="CSV output path")
    parser.add_argument("--png", help="optional PNG heatmap output path (needs matplotlib)")
    parser.add_argument(
        "--skip-home",
        action="store_true",
        help="skip homing before the scan (only if already homed)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the planned grid and exit without connecting"
    )
    args = parser.parse_args()

    xs, ys = _frange(args.x_min, args.x_max, args.step_mm), _frange(
        args.y_min, args.y_max, args.step_mm
    )
    print(
        f"Planned scan: {len(xs)} x {len(ys)} = {len(xs) * len(ys)} points over "
        f"x[{args.x_min}, {args.x_max}] y[{args.y_min}, {args.y_max}] @ {args.step_mm} mm"
    )
    if args.dry_run:
        return

    robot, fake_transport = build_robot(args.port, args.config)
    if robot.rear() is None:
        raise SystemExit(
            "no ultrasonic sensor attached to the rear mount -- "
            "attach one via --config, or see build_robot()"
        )

    total = len(xs) * len(ys)

    def before_read(x, y):
        if fake_transport is not None:
            fake_transport.ultrasonic_mm = synthetic_height_mm(x, y)

    def on_point(row, col, x, y, distance):
        n = row * len(xs) + (col + 1 if row % 2 == 0 else len(xs) - col)
        label = "out-of-range" if distance is None else f"{distance:.1f} mm"
        print(f"  [{n}/{total}] ({x:.1f}, {y:.1f}) -> {label}")

    with robot:
        if not args.skip_home:
            robot.home()  # leaves absolute mode
        robot.raise_z(MountSide.LEFT)
        robot.raise_z(MountSide.RIGHT)

        grid, xs, ys = scan_topography(
            robot,
            x_min=args.x_min,
            x_max=args.x_max,
            y_min=args.y_min,
            y_max=args.y_max,
            step_mm=args.step_mm,
            feed=args.feed,
            settle_s=args.settle_s,
            before_read=before_read,
            on_point=on_point,
        )

    write_csv(args.out, grid, xs, ys)
    print(f"\nWrote {args.out}")
    print()
    print(render_ascii(grid, xs, ys))

    if args.png:
        if save_png(args.png, grid, xs, ys):
            print(f"\nWrote {args.png}")
        else:
            print("\nmatplotlib not installed -- skipped PNG output")


if __name__ == "__main__":
    main()
