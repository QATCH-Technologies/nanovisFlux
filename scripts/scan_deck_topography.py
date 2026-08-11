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

Real continuous sweeps, no settling pauses, no stepped moves: each row is
ONE G1 move covering the whole row (min X to max X or back, depending on
snake direction) at a steady `--feed` microsteps/sec, fired with
wait_for_ok=False (see Controller.execute) so it doesn't block.

M412 is NOT asynchronous on this firmware -- confirmed by reading
firmware/OT2-stepper-controller/OT2-stepper-controller.ino: the M412
handler runs its 10-sample ultrasonic average (each sample floor-limited
to >=30ms by AlashUltrasonic::getDistance's own delay(), so ~300ms+ per
call) entirely synchronously, and the MOTOR_X.run()/MOTOR_Y.run() calls
that actually advance a stepper sit LATER in the same single-threaded
loop() -- unreached until the M412 handler's block finishes. So every
M412 call fully pauses all motor motion for its own duration; there is no
way to poll the sensor for free. M114 (position) is cheap by comparison
(no external timing, just a stored-counter readback) and doesn't
meaningfully interrupt stepping.

Given that, this polls M114 (cheap, doesn't pause motion) at a small
`_POLL_INTERVAL_S` throttle -- not a settling delay, just avoiding a
genuinely unthrottled busy-wait loop that would peg the CPU and hammer the
serial line for no benefit -- and calls M412 sparingly: `--samples-per-row`
times per row, spaced out via wall-clock time so the gantry gets real,
uninterrupted stretches of travel between each ~300ms sensor pause instead
of stalling almost continuously.

This firmware doesn't ack a G1 until the move itself finishes (not merely
once it's queued -- see control/jog.py's JogController, which uses the same
wait_for_ok=False + later drain pattern for its own continuous jog). So
each row ends the same way JogController.end_jog does: Controller.quick_stop
(M410) to make sure nothing's still creeping, reset_input_buffer to discard
that G1's now-irrelevant belated "ok" (it may or may not have already
arrived -- see scan_topography's docstring for the race this avoids), then
a fresh report_position to resync. Never send X and Y in the same G1 here:
this firmware slows the *shorter*-travel axis to match the longer one for
coordinated linear moves, which divides its target speed by zero (a stopped
axis, not a fast one) when that axis isn't actually moving -- rows only
ever command X, and the row-to-row Y step is a separate G0.

Output:
  - a CSV of every (x_usteps, y_usteps, distance_mm) reading (--out),
    exactly as collected -- irregularly spaced, not a regular grid
  - an ASCII heatmap printed to the terminal
  - optionally a PNG heatmap (--png), if matplotlib is installed
  (the heatmaps rasterize the raw samples onto a `--display-columns`-wide
  grid per row -- see bucket_grid -- purely for a legible picture; the CSV
  is never bucketed)

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
import time

from src.config.loader import load_robot
from src.core import AxisId, MountSide
from src.geometry import default_axis_scale
from src.robot import Robot
from src.tools import UltrasonicSensor
from src.transport import FakeTransport, SerialTransport

_ASCII_RAMP = " .:-=+*#%@"
#: A real M412 costs at least this long (10 ultrasonic samples, each
#: floor-limited to >=30ms -- see AlashUltrasonic::getDistance). Sample
#: intervals shorter than this are pointless: M412 itself won't return any
#: faster, so the gantry would stall back-to-back regardless of the target
#: spacing -- see module docstring.
_M412_MIN_INTERVAL_S = 0.3
#: M114 (position) doesn't pause motion the way M412 does, but polling it
#: in a genuinely unthrottled tight loop just busy-waits the CPU (and, on
#: real hardware, contends the serial line) for no benefit -- position
#: doesn't need microsecond-fresh updates to detect "have we arrived" or
#: "is it time for the next M412 yet". This is a poll-loop throttle, not a
#: settling delay: it's not waiting for anything physical, just spacing out
#: otherwise-pointless-to-repeat status checks.
_POLL_INTERVAL_S = 0.02
_MAX_POLLS_PER_ROW = 6000  # safety net against a stuck/never-arriving row (~2 minutes at _POLL_INTERVAL_S)


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


def _read_distance_mm(robot: Robot) -> float | None:
    """Query M412 for all three slots and return whichever came back
    valid, preferring Z (the REAR mount's documented, physically-wired
    slot -- see tools/ultrasonic.py's _MOUNT_RANGE_SLOT and
    firmware/docs/protocol.md, which says X/Y "will always return -1").
    The wire reply is a 3-tuple, [RNG:<x_mm>,<y_mm>,<z_mm>] -- querying
    all three and falling back across them is a defensive read in case a
    given board actually answers on a different slot than documented,
    rather than trusting Z alone."""
    result = robot.controller.measure_distance(AxisId.X, AxisId.Y, AxisId.Z)
    for value in (result.z_mm, result.x_mm, result.y_mm):
        if value is not None:
            return value
    return None


def _sweep_row(robot: Robot, x_end: int, y: int, feed: int | None,
               tolerance: int, sample_interval_s: float,
               before_sample=None, on_sample=None) -> list:
    """Continuously sweep X to `x_end` (the gantry is already at the row's
    start X and at this row's Y). Position (M114) is polled back-to-back
    the whole way -- cheap, doesn't interrupt stepping -- but the sensor
    (M412) is only queried once every `sample_interval_s` of real elapsed
    time, since M412 itself pauses all motion for its own duration (see
    module docstring): querying it less often means fewer, shorter pauses
    instead of one almost every poll. Returns this row's (x, y,
    distance_mm) samples.

    The un-awaited G1's own "ok" isn't consumed here; a poll that lands
    exactly as that "ok" surfaces reads it instead of its own response, so
    report_position can come back missing X entirely -- that specific
    shape (a report with no X in it at all, never a wrong-but-present
    value) is treated as "we just arrived, stop", not an error, since
    that's exactly when it can happen.
    """
    robot.controller.linear_move({AxisId.X: x_end}, feed=feed, wait_for_ok=False)
    samples = []
    next_sample_at = time.monotonic()
    for _ in range(_MAX_POLLS_PER_ROW):
        pos = robot.controller.report_position()
        x_now = pos.get(AxisId.X)
        if x_now is None:
            break
        arrived = abs(x_now - x_end) <= tolerance
        if arrived or time.monotonic() >= next_sample_at:
            if before_sample:
                before_sample(x_now, y)
            distance = _read_distance_mm(robot)
            samples.append((x_now, y, distance))
            if on_sample:
                on_sample(x_now, y, distance)
            next_sample_at = time.monotonic() + sample_interval_s
        if arrived:
            break
        time.sleep(_POLL_INTERVAL_S)  # throttle -- see _POLL_INTERVAL_S's own comment
    # Whatever's left of this row's G1 (arrived, raced, or -- via the
    # safety net -- still short) gets cut off and drained the same way
    # JogController.end_jog cleans up a continuous jog: quick_stop first
    # (safe even if the move already finished on its own), then discard
    # whatever stray reply that leaves sitting unread, then resync.
    robot.controller.quick_stop()
    robot.controller.reset_input_buffer()
    robot.controller.report_position()
    return samples


def scan_topography(
    robot: Robot,
    *,
    x_min: int,
    x_max: int,
    y_min: int,
    y_max: int,
    row_step: int,
    feed: int | None = None,
    samples_per_row: int = 10,
    before_sample=None,
    on_row_start=None,
    on_sample=None,
):
    """Boustrophedon (snake) raster over raw motor [x_min, x_max] x
    [y_min, y_max] microsteps: each row is one continuous sweep (see
    _sweep_row), Y stepped by `row_step` between rows, sampling the sensor
    `samples_per_row` times per row (spaced by wall-clock time, not
    position -- see _sweep_row for why).

    Returns a flat list of (x_usteps, y_usteps, distance_mm_or_None)
    samples in collection order -- irregularly spaced along X (real
    positions read back mid-sweep, not a predetermined grid). Use
    bucket_grid to rasterize this onto a regular grid for display.
    """
    sensor = robot.rear()
    if sensor is None:
        raise RuntimeError("no ultrasonic sensor attached to the rear mount (MountSide.REAR)")

    ys = _irange(y_min, y_max, row_step)
    tolerance = max(2, (x_max - x_min) // 500)

    # Estimate row travel time from the configured/overridden feed, so
    # samples_per_row spreads out over roughly the whole row instead of
    # bunching at one end -- floored at _M412_MIN_INTERVAL_S since M412
    # can't return any faster than that regardless of the target spacing.
    feed_effective = feed or robot.axes[AxisId.X].config.travel_speed
    row_duration_s = (x_max - x_min) / feed_effective if feed_effective else 0.0
    sample_interval_s = max(_M412_MIN_INTERVAL_S, row_duration_s / max(1, samples_per_row))

    samples = []
    forward = True
    for row_idx, y in enumerate(ys):
        x_start, x_end = (x_min, x_max) if forward else (x_max, x_min)
        if row_idx == 0:
            robot.controller.rapid_move({AxisId.X: x_start, AxisId.Y: y})
        else:
            robot.controller.rapid_move({AxisId.Y: y})  # X unchanged: already at x_start
        if on_row_start:
            on_row_start(row_idx, len(ys), y, x_start, x_end)

        def before(x, y=y):
            if before_sample:
                before_sample(x, y)

        def sample(x, y_, distance, row_idx=row_idx):
            if on_sample:
                on_sample(row_idx, x, y_, distance)

        samples.extend(_sweep_row(robot, x_end, y, feed, tolerance, sample_interval_s,
                                  before_sample=before, on_sample=sample))
        forward = not forward
    return samples


def bucket_grid(samples: list, x_min: int, x_max: int, ys: list, columns: int):
    """Rasterize the (irregularly X-spaced) continuous-sweep `samples` onto
    a regular display grid -- one row per entry in `ys` (already regular,
    from the row step), `columns` evenly spaced X buckets per row, each the
    mean of every sample landing closest to that bucket's X. Purely for the
    ASCII/PNG heatmap; the CSV export uses the raw samples untouched.

    Returns (grid, xs) -- grid[row][col] is a distance_mm or None (bucket
    got no samples); xs are the bucket centers, aligned with ys' rows.
    """
    xs = _irange(x_min, x_max, max(1, (x_max - x_min) // max(1, columns - 1)))
    row_of_y = {y: i for i, y in enumerate(ys)}
    sums = [[0.0] * len(xs) for _ in ys]
    counts = [[0] * len(xs) for _ in ys]
    for x, y, d in samples:
        if d is None:
            continue
        row = row_of_y.get(y)
        if row is None:
            continue
        col = min(range(len(xs)), key=lambda i: abs(xs[i] - x))
        sums[row][col] += d
        counts[row][col] += 1
    grid = [[(sums[r][c] / counts[r][c]) if counts[r][c] else None for c in range(len(xs))]
           for r in range(len(ys))]
    return grid, xs


def write_csv(path: str, samples: list) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["x_usteps", "y_usteps", "distance_mm"])
        for x, y, d in samples:
            w.writerow([x, y, "" if d is None else d])


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
        "--port",
        default="COM6",
        help="serial port for real hardware (e.g. COM6); omit to use the fake transport",
    )
    parser.add_argument(
        "--config",
        default="src/config/robot.example.yaml",
        help="robot config YAML to load (transport/axis overrides + rear ultrasonic mount); "
        "pass an empty string for a bare robot with a default-configured sensor instead",
    )
    parser.add_argument("--x-min-steps", type=int, help="min X, motor microsteps; default 0")
    parser.add_argument(
        "--x-max-steps", type=int, help="max X, motor microsteps; default the X axis's endstop_limit"
    )
    parser.add_argument("--y-min-steps", type=int, help="min Y, motor microsteps; default 0")
    parser.add_argument(
        "--y-max-steps", type=int, help="max Y, motor microsteps; default the Y axis's endstop_limit"
    )
    parser.add_argument(
        "--row-step-microsteps",
        type=int,
        default=2000,
        help="Y increment between row sweeps, motor microsteps",
    )
    parser.add_argument(
        "--display-columns",
        type=int,
        default=60,
        help="X buckets per row for the ASCII/PNG heatmap only -- the CSV keeps every raw sample",
    )
    parser.add_argument(
        "--feed",
        type=int,
        help="row sweep speed, microsteps/sec; omit to use the axis's configured travel speed",
    )
    parser.add_argument(
        "--samples-per-row",
        type=int,
        default=10,
        help="ultrasonic (M412) queries per row, spaced by wall-clock time. M412 fully pauses "
        "motion for ~0.3s+ every time it's called (see module docstring) -- fewer samples means "
        "longer uninterrupted stretches of travel between pauses, more means denser data at the "
        "cost of a choppier sweep",
    )
    parser.add_argument("--out", default="scan_topography.csv", help="CSV output path")
    parser.add_argument("--png", help="optional PNG heatmap output path (needs matplotlib)")
    parser.add_argument(
        "--skip-home",
        action="store_true",
        help="skip homing before the scan (only if already homed)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the planned rows and exit without scanning"
    )
    args = parser.parse_args()

    robot, fake_transport = build_robot(args.port, args.config)
    if robot.rear() is None:
        raise SystemExit(
            "no ultrasonic sensor attached to the rear mount -- "
            "attach one via --config, or see build_robot()"
        )

    x_min = args.x_min_steps if args.x_min_steps is not None else 0
    x_max = args.x_max_steps if args.x_max_steps is not None else robot.axes[AxisId.X].config.endstop_limit
    y_min = args.y_min_steps if args.y_min_steps is not None else 0
    y_max = args.y_max_steps if args.y_max_steps is not None else robot.axes[AxisId.Y].config.endstop_limit

    ys = _irange(y_min, y_max, args.row_step_microsteps)
    feed_effective = args.feed or robot.axes[AxisId.X].config.travel_speed
    row_duration_s = (x_max - x_min) / feed_effective if feed_effective else 0.0
    print(
        f"Planned scan: {len(ys)} continuous row sweeps, X[{x_min}, {x_max}] each "
        f"(~{row_duration_s:.1f}s/row @ feed {feed_effective:g}), Y[{y_min}, {y_max}] "
        f"@ {args.row_step_microsteps} step, {args.samples_per_row} samples/row"
    )
    if row_duration_s < args.samples_per_row * _M412_MIN_INTERVAL_S:
        print(
            f"  note: a row only takes ~{row_duration_s:.1f}s but {args.samples_per_row} samples "
            f"need >={args.samples_per_row * _M412_MIN_INTERVAL_S:.1f}s of M412 time alone -- "
            "the sweep will be mostly pauses. Lower --samples-per-row or --feed to fix."
        )
    if args.dry_run:
        return

    def before_sample(x, y):
        if fake_transport is not None:
            fake_transport.ultrasonic_mm = synthetic_height_mm(x, y)

    def on_row_start(row_idx, n_rows, y, x_start, x_end):
        print(f"Row {row_idx + 1}/{n_rows}: sweeping X {x_start} -> {x_end} @ Y={y}")

    def on_sample(_row_idx, x, y, distance):
        label = "out-of-range" if distance is None else f"{distance:.1f} mm"
        print(f"  ({x}, {y}) -> {label}")

    with robot:
        if not args.skip_home:
            robot.home()  # leaves absolute mode -- required before any G0/G1

        samples = scan_topography(
            robot,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            row_step=args.row_step_microsteps,
            feed=args.feed,
            samples_per_row=args.samples_per_row,
            before_sample=before_sample,
            on_row_start=on_row_start,
            on_sample=on_sample,
        )

    write_csv(args.out, samples)
    print(f"\nWrote {args.out} ({len(samples)} samples)")
    print()
    grid, xs = bucket_grid(samples, x_min, x_max, ys, args.display_columns)
    print(render_ascii(grid, xs, ys))

    if args.png:
        if save_png(args.png, grid, xs, ys):
            print(f"\nWrote {args.png}")
        else:
            print("\nmatplotlib not installed -- skipped PNG output")


if __name__ == "__main__":
    main()
