"""Raster-scans the rear ultrasonic sensor (see src/tools/ultrasonic.py)
across the gantry's full X/Y motor travel and builds a top-down
topographical map from the range readings.

Works directly in raw motor microsteps (Controller.rapid_move/linear_move)
rather than deck millimetres (Robot.move_to/safe_move_to), so it needs no
DeckCalibration at all -- "the deck" doesn't have to exist yet as a fitted
coordinate system for this to run against real hardware. Default scan
bounds are each axis's own configured travel limit (AxisConfig.endstop_limit
-- see motion/axis.py), i.e. the *entire* space the gantry can physically
reach, not just whatever's already been mapped as "the deck".

The sensor is fixed to the gantry frame behind the Z/A mounts and has no
vertical axis of its own (MountSide.REAR -- see src/core.py and
src/motion/mounts.py): it only ever travels along with raw X/Y, offset a
constant 50mm in Y from the gantry's own shared X/Y reference point (see
MOUNT_OFFSET_MM[MountSide.REAR]). Recorded X/Y are that raw gantry
reference point, not the sensor's exact position -- a deliberate
simplification that keeps this script calibration-free; the offset is
fixed and small relative to the scan's own resolution.

Continuous coverage, no settling pauses: within a row the gantry advances
in small ``--step-microsteps`` increments, each a normal, fully-awaited G1
step immediately followed by one M412 poll (Controller.linear_move /
UltrasonicSensor.read_distance_mm) -- no time.sleep anywhere. That G1/M412
round trip is the only "settling" there ever is; a finer
``--step-microsteps`` traces a smoother, more continuous-looking sweep at
the cost of more points (and proportionally more wall-clock time). Z and A
are never touched here -- homing already leaves them at their top/safe
position (home is up), which is all the clearance a rear-only sensor scan
needs.

Output:
  - a CSV of every (x_usteps, y_usteps, distance_mm) reading (--out)
  - an ASCII heatmap printed to the terminal
  - optionally a PNG heatmap (--png), if matplotlib is installed

Runs against the in-memory FakeTransport by default (no hardware needed):
without --config it also fabricates a smooth synthetic surface so the
heatmap/PNG output can be exercised end-to-end. Pass --port for real
hardware, or --config to load a full robot config (for its own transport/
axis-limit overrides and a properly configured rear ultrasonic mount --
see src/config/robot.example.yaml); neither is required for this script's
own motion, which never consults a calibration.
"""

from __future__ import annotations

import argparse
import csv
import math

from src.config.loader import load_robot
from src.core import AxisId, MountSide
from src.geometry import default_axis_scale
from src.robot import Robot
from src.tools import UltrasonicSensor
from src.transport import FakeTransport, SerialTransport

_ASCII_RAMP = " .:-=+*#%@"


def _irange(start: int, stop: int, step: int) -> list:
    """Evenly spaced integer microstep points from start to stop inclusive
    -- always hits both endpoints exactly, spaced as close to `step` as an
    integer point count allows (mirrors a float _frange, but rounded to
    whole microsteps since motor targets must be integers)."""
    if stop <= start:
        return [start]
    count = max(1, round((stop - start) / step)) + 1
    actual_step = (stop - start) / (count - 1)
    return [round(start + i * actual_step) for i in range(count)]


def synthetic_height_mm(x_usteps: float, y_usteps: float) -> float:
    """A smooth rolling surface around a nominal standoff -- stand-in
    terrain for exercising the scan/heatmap pipeline without real
    hardware. Rescales raw motor microsteps to mm internally (via the
    firmware's default per-axis scale, not a real calibration) purely so
    the synthetic bumps stay visually smooth regardless of how many
    microsteps this deck's travel happens to span."""
    x_mm = default_axis_scale(AxisId.X).to_mm(x_usteps)
    y_mm = default_axis_scale(AxisId.Y).to_mm(y_usteps)
    base = 300.0
    bump = 40.0 * math.sin(x_mm / 60.0) * math.cos(y_mm / 45.0)
    return max(20.0, base - bump)


def scan_topography(
    robot: Robot,
    *,
    x_min: int,
    x_max: int,
    y_min: int,
    y_max: int,
    step: int,
    feed: int | None = None,
    before_read=None,
    on_point=None,
):
    """Boustrophedon (snake) raster scan over raw motor [x_min, x_max] x
    [y_min, y_max] microsteps, continuously: every column-to-column move is
    a small, fully-awaited G1 step (see module docstring) with no settling
    pause -- the sensor is polled immediately after each one.

    Returns (grid, xs, ys) where grid[row][col] is the distance_mm (or None
    on no echo/out of range) at (xs[col], ys[row]), both in microsteps.
    Snaking only changes travel order, not the returned layout, which is
    always in xs/ys order.
    """
    sensor = robot.rear()
    if sensor is None:
        raise RuntimeError("no ultrasonic sensor attached to the rear mount (MountSide.REAR)")

    xs, ys = _irange(x_min, x_max, step), _irange(y_min, y_max, step)
    grid = [[None] * len(xs) for _ in ys]

    for row, y in enumerate(ys):
        cols = range(len(xs)) if row % 2 == 0 else range(len(xs) - 1, -1, -1)
        for col in cols:
            x = xs[col]
            robot.controller.linear_move({AxisId.X: x, AxisId.Y: y}, feed=feed)
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
        w.writerow(["x_usteps", "y_usteps", "distance_mm"])
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
    ax.set_xlabel("X (motor microsteps)")
    ax.set_ylabel("Y (motor microsteps)")
    ax.set_title("Deck topography (ultrasonic range, mm)")
    fig.colorbar(im, ax=ax, label="distance (mm)")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def build_robot(port: str | None, config: str | None):
    """Returns (robot, fake_transport). fake_transport is the FakeTransport
    instance when one was built here (so main() can feed it synthetic
    terrain for the no-hardware demo), or None for --config/--port.

    No calibration is built or needed -- this script only ever drives raw
    motor microsteps (see module docstring), so a bare Robot with just a
    transport and a rear ultrasonic sensor is enough for --port; --config
    still works too (its own transport/axis overrides apply), its
    calibration (if any) is simply unused."""
    if config:
        return load_robot(config), None

    transport = SerialTransport(port) if port else FakeTransport()
    robot = Robot(transport, travel_z_mm=120)
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
        help="robot config YAML to load (transport/axis overrides + rear ultrasonic mount); "
        "omit for a bare robot with a default-configured sensor",
    )
    parser.add_argument("--x-min-steps", type=int, help="min X, motor microsteps; default 0")
    parser.add_argument(
        "--x-max-steps",
        type=int,
        help="max X, motor microsteps; default the X axis's endstop_limit",
    )
    parser.add_argument("--y-min-steps", type=int, help="min Y, motor microsteps; default 0")
    parser.add_argument(
        "--y-max-steps",
        type=int,
        help="max Y, motor microsteps; default the Y axis's endstop_limit",
    )
    parser.add_argument(
        "--step-microsteps",
        type=int,
        default=1000,
        help="grid spacing between readings, motor microsteps -- finer means a smoother, more "
        "continuous-looking sweep at the cost of more points",
    )
    parser.add_argument(
        "--feed",
        type=int,
        help="feed rate for each step, microsteps/sec; omit to use the axis's configured travel speed",
    )
    parser.add_argument("--out", default="scan_topography.csv", help="CSV output path")
    parser.add_argument("--png", help="optional PNG heatmap output path (needs matplotlib)")
    parser.add_argument(
        "--skip-home",
        action="store_true",
        help="skip homing before the scan (only if already homed)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the planned grid and exit without scanning"
    )
    args = parser.parse_args()

    robot, fake_transport = build_robot(args.port, args.config)
    if robot.rear() is None:
        raise SystemExit(
            "no ultrasonic sensor attached to the rear mount -- "
            "attach one via --config, or see build_robot()"
        )

    x_min = args.x_min_steps if args.x_min_steps is not None else 0
    x_max = (
        args.x_max_steps
        if args.x_max_steps is not None
        else robot.axes[AxisId.X].config.endstop_limit
    )
    y_min = args.y_min_steps if args.y_min_steps is not None else 0
    y_max = (
        args.y_max_steps
        if args.y_max_steps is not None
        else robot.axes[AxisId.Y].config.endstop_limit
    )

    xs, ys = _irange(x_min, x_max, args.step_microsteps), _irange(
        y_min, y_max, args.step_microsteps
    )
    print(
        f"Planned scan: {len(xs)} x {len(ys)} = {len(xs) * len(ys)} points over "
        f"X[{x_min}, {x_max}] Y[{y_min}, {y_max}] motor microsteps @ {args.step_microsteps} step"
    )
    if args.dry_run:
        return

    total = len(xs) * len(ys)

    def before_read(x, y):
        if fake_transport is not None:
            fake_transport.ultrasonic_mm = synthetic_height_mm(x, y)

    def on_point(row, col, x, y, distance):
        n = row * len(xs) + (col + 1 if row % 2 == 0 else len(xs) - col)
        label = "out-of-range" if distance is None else f"{distance:.1f} mm"
        print(f"  [{n}/{total}] ({x}, {y}) -> {label}")

    with robot:
        if not args.skip_home:
            robot.home()  # leaves absolute mode -- required before any G0/G1

        grid, xs, ys = scan_topography(
            robot,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            step=args.step_microsteps,
            feed=args.feed,
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
