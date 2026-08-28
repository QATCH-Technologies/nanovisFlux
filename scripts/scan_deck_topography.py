"""Raster-scans the rear ultrasonic sensor to build a top-down topographical map.

This script operates directly in raw motor microsteps across the gantry's full X/Y
travel limits, requiring no prior deck calibration. Coordinates are recorded based on
the raw gantry reference point rather than the exact sensor position, as the rear
sensor (`MountSide.REAR`) has a fixed 50mm Y offset.

Hardware and Firmware Handling:
    * Continuous Sweeps: Each row is a single, non-blocking G1 move. X and Y are
      never sent in the same G1 move to avoid a firmware zero-division bug that
      stalls axes.
    * Sensor Polling: The ultrasonic sensor command (M412) is synchronous and pauses
      motor motion for ~300ms. It is sampled sparingly based on `--samples-per-row`.
      Position tracking uses the non-blocking M114 command, throttled by `_POLL_INTERVAL_S`.
    * Move Completion: Rows end with a quick stop (M410), an input buffer flush, and
      a position resync to handle delayed firmware acknowledgments safely.

Outputs:
    * CSV: Raw, irregularly spaced `(x_usteps, y_usteps, distance_mm)` readings (`--out`).
    * ASCII Heatmap: Bucket-rasterized grid printed directly to the terminal.
    * PNG Heatmap: Generated if `matplotlib` is installed (`--png`).

Usage & Simulation:
    * Defaults to an in-memory `SimulatedTransport` with a synthetic surface for
      safe, hardware-free testing.
    * Pass `--port` to drive real hardware, or `--config` to load a full robot config
      for transport/axis-limit overrides.
"""

from __future__ import annotations

import argparse
import csv
import math
import time
from pathlib import Path

from loguru import logger

from src.config.loader import load_robot
from src.core import AxisId, MountSide
from src.geometry import default_axis_scale
from src.robot import Robot
from src.tools import UltrasonicSensor
from src.transport import SerialTransport, SimulatedTransport

_DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "configs" / "robot.yaml"

_ASCII_RAMP = " .:-=+*#%@"
_M412_MIN_INTERVAL_S = 0.3
_POLL_INTERVAL_S = 0.02
_MAX_POLLS_PER_ROW = 6000


def _irange(start: int, stop: int, step: int) -> list:
    """Compute evenly spaced integer points from `start` to `stop`.

    Both endpoints are always hit exactly; the interior points are spaced
    as close to `step` as an integer point count allows. Conceptually
    mirrors a float `_frange` helper, but rounds every point to a whole
    microstep since motor targets must be integers.

    Args:
        start: First point, always included exactly.
        stop: Last point, included exactly unless `stop <= start`.
        step: Target spacing between points. The actual spacing is
            recomputed from the resulting integer point count so both
            endpoints still land exactly.

    Returns:
        list: Ascending points from `start` to `stop` inclusive, or
        `[start]` alone if `stop <= start`.
    """
    if stop <= start:
        return [start]
    count = max(1, round((stop - start) / step)) + 1
    actual_step = (stop - start) / (count - 1)
    return [round(start + i * actual_step) for i in range(count)]


def synthetic_height_mm(x_usteps: float, y_usteps: float) -> float:
    """Compute a synthetic standoff height for the no-hardware demo.

    Produces a smooth rolling surface around a nominal standoff -- stand-in
    terrain for exercising the scan/heatmap pipeline end-to-end without
    real hardware (see module docstring). Raw motor microsteps are
    rescaled to mm internally via the firmware's default per-axis scale,
    not a real calibration, purely so the synthetic bumps stay visually
    smooth regardless of how many microsteps this deck's travel happens to
    span.

    Args:
        x_usteps: X position, raw motor microsteps.
        y_usteps: Y position, raw motor microsteps.

    Returns:
        float: Synthetic sensor-to-surface distance in mm at
        (`x_usteps`, `y_usteps`).
    """
    x_mm = default_axis_scale(AxisId.X).to_mm(x_usteps)
    y_mm = default_axis_scale(AxisId.Y).to_mm(y_usteps)
    base = 300.0
    bump = 40.0 * math.sin(x_mm / 60.0) * math.cos(y_mm / 45.0)
    return max(20.0, base - bump)


def _read_distance_mm(robot: Robot) -> float | None:
    """Query M412 and return the rear ultrasonic sensor's distance reading.

    The wire reply is a 3-tuple, `[RNG:<x_mm>,<y_mm>,<z_mm>]`. Z is the
    REAR mount's documented, physically-wired slot (see
    `tools/ultrasonic.py`'s `_MOUNT_RANGE_SLOT` and
    `firmware/docs/protocol.md`, which states X/Y "will always return -1"),
    so it's preferred. Querying and falling back across all three slots,
    rather than trusting Z alone, is a defensive read in case a given
    board actually answers on a different slot than documented.

    Args:
        robot: Robot instance whose controller issues the M412 query.

    Returns:
        float | None: Distance in mm from whichever slot returned a valid
        reading, preferring Z, or `None` if all three came back invalid.
    """
    result = robot.controller.measure_distance(AxisId.X, AxisId.Y, AxisId.Z)
    for value in (result.z_mm, result.x_mm, result.y_mm):
        if value is not None:
            return value
    return None


def _sweep_row(
    robot: Robot,
    x_end: int,
    y: int,
    feed: int | None,
    tolerance: int,
    sample_interval_s: float,
    before_sample=None,
    on_sample=None,
) -> list:
    """Continuously sweep X to `x_end` and sample the sensor along the way.

    The gantry is assumed to already be at the row's start X and at this
    row's Y. Position (M114) is polled back-to-back for the whole sweep --
    cheap, and it doesn't interrupt stepping -- but the sensor (M412) is
    only queried once every `sample_interval_s` of real elapsed time,
    since M412 itself pauses all motion for its own duration (see module
    docstring): querying it less often means fewer, shorter pauses instead
    of one almost every poll.

    The un-awaited G1's own "ok" isn't consumed here; a poll that lands
    exactly as that "ok" surfaces reads it instead of its own response, so
    `report_position` can come back missing X entirely -- that specific
    shape (a report with no X in it at all, never a wrong-but-present
    value) is treated as "we just arrived, stop", not an error, since
    that's exactly when it can happen. Once the sweep ends -- arrived,
    raced against that stray "ok", or cut off by the safety net -- the row
    is closed out the same way `JogController.end_jog` cleans up a
    continuous jog: `quick_stop` first (safe even if the move already
    finished on its own), then the stray reply that leaves behind is
    discarded, then position is resynced with a fresh `report_position`.

    Args:
        robot: Robot instance driving the sweep.
        x_end: Target X, raw motor microsteps, for this row's sweep.
        y: This row's Y, raw motor microsteps (used only to label
            samples; the gantry is not moved in Y here).
        feed: Feed rate in microsteps/sec, or `None` to use the X axis's
            configured travel speed.
        tolerance: Maximum absolute microstep distance from `x_end` at
            which the gantry is considered arrived.
        sample_interval_s: Minimum wall-clock time between M412 queries.
        before_sample: Optional callback invoked as `before_sample(x, y)`
            immediately before each sensor query.
        on_sample: Optional callback invoked as `on_sample(x, y,
            distance_mm)` immediately after each sensor query.

    Returns:
        list: This row's `(x_usteps, y_usteps, distance_mm)` samples, in
        collection order.
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
        time.sleep(_POLL_INTERVAL_S)
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
    """Raster-scan a raw motor microstep region in a boustrophedon pattern.

    Sweeps `[x_min, x_max]` x `[y_min, y_max]` microsteps in a snake
    (boustrophedon) pattern: each row is one continuous sweep (see
    `_sweep_row`), alternating sweep direction so the gantry never has to
    retrace a row, with Y stepped by `row_step` between rows. The sensor
    is sampled `samples_per_row` times per row, spaced out by wall-clock
    time rather than position -- see `_sweep_row` for why M412 can't be
    polled for free.

    The wall-clock spacing between samples is estimated from `feed` (or
    the X axis's configured travel speed) and the row's X span, so that
    `samples_per_row` spreads out over roughly the whole row instead of
    bunching at one end. The estimate is floored at `_M412_MIN_INTERVAL_S`
    since M412 can't return any faster than that regardless of the target
    spacing (see module docstring).

    Args:
        robot: Robot instance to scan with. Must have an ultrasonic
            sensor attached to :attr:`MountSide.REAR`.
        x_min: Minimum X, raw motor microsteps.
        x_max: Maximum X, raw motor microsteps.
        y_min: Minimum Y, raw motor microsteps.
        y_max: Maximum Y, raw motor microsteps.
        row_step: Y increment between row sweeps, raw motor microsteps.
        feed: Row sweep feed rate in microsteps/sec, or `None` to use the
            X axis's configured travel speed.
        samples_per_row: Number of M412 queries per row.
        before_sample: Optional callback invoked as `before_sample(x, y)`
            immediately before each sensor query, for every row.
        on_row_start: Optional callback invoked as
            `on_row_start(row_idx, n_rows, y, x_start, x_end)` when each
            row begins, before its sweep starts.
        on_sample: Optional callback invoked as `on_sample(row_idx, x, y,
            distance_mm)` immediately after each sensor query.

    Returns:
        list: Flat list of `(x_usteps, y_usteps, distance_mm_or_None)`
        samples in collection order -- irregularly spaced along X, since
        positions are read back mid-sweep rather than drawn from a
        predetermined grid. Use `bucket_grid` to rasterize this onto a
        regular grid for display.

    Raises:
        RuntimeError: If no ultrasonic sensor is attached to the rear
            mount.
    """
    sensor = robot.rear()
    if sensor is None:
        raise RuntimeError("no ultrasonic sensor attached to the rear mount (MountSide.REAR)")

    ys = _irange(y_min, y_max, row_step)
    tolerance = max(2, (x_max - x_min) // 500)

    # row-duration/sample-interval estimate; see docstring.
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

        samples.extend(
            _sweep_row(
                robot,
                x_end,
                y,
                feed,
                tolerance,
                sample_interval_s,
                before_sample=before,
                on_sample=sample,
            )
        )
        forward = not forward
    return samples


def bucket_grid(samples: list, x_min: int, x_max: int, ys: list, columns: int):
    """Rasterize irregularly X-spaced scan samples onto a regular grid.

    Each entry in `ys` becomes one grid row (already regularly spaced,
    from the row step used to collect them); `columns` evenly spaced X
    buckets per row are computed from `x_min`/`x_max`, each bucket taking
    the mean of every sample whose X lands closest to that bucket's
    center. This exists purely to produce a legible ASCII/PNG heatmap --
    the CSV export uses the raw, unbucketed samples untouched (see module
    docstring).

    Args:
        samples: Flat `(x_usteps, y_usteps, distance_mm_or_None)`
            samples, as returned by :func:`scan_topography`.
        x_min: Minimum X, raw motor microsteps, spanning the bucket
            range.
        x_max: Maximum X, raw motor microsteps, spanning the bucket
            range.
        ys: Row Y positions, raw motor microsteps, in the order they
            should appear as grid rows.
        columns: Number of evenly spaced X buckets per row.

    Returns:
        tuple[list, list]: `(grid, xs)`. `grid[row][col]` is a mean
        `distance_mm`, or `None` if that bucket collected no samples.
        `xs` are the bucket center X positions, aligned with `grid`'s
        columns.
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
    grid = [
        [(sums[r][c] / counts[r][c]) if counts[r][c] else None for c in range(len(xs))]
        for r in range(len(ys))
    ]
    return grid, xs


def write_csv(path: str, samples: list) -> None:
    """Write raw scan samples to a CSV file, one row per sample.

    Samples are written exactly as collected -- irregularly spaced along
    X, never bucketed or rasterized (see `bucket_grid`, which is used
    only for the ASCII/PNG heatmap output) -- so the CSV remains the
    authoritative, lossless record of a scan.

    Args:
        path: Destination CSV file path.
        samples: Flat `(x_usteps, y_usteps, distance_mm_or_None)`
            samples, as returned by :func:`scan_topography`. A `None`
            distance is written as an empty field.

    Returns:
        None
    """
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["x_usteps", "y_usteps", "distance_mm"])
        for x, y, d in samples:
            w.writerow([x, y, "" if d is None else d])


def render_ascii(grid: list, xs: list, ys: list) -> str:
    """Render a bucketed distance grid as an ASCII-art heatmap string.

    Values are scaled per-scan, from the grid's own min/max distance, onto
    `_ASCII_RAMP`'s density characters, so the picture stays legible
    without needing calibration to any known distance range. Rows are
    printed with Y increasing upward (reversed from `grid`'s row order) to
    match how a top-down map is normally read.

    Args:
        grid: Bucketed distance grid, as returned by `bucket_grid`, i.e.
            `grid[row][col]` is a `distance_mm` or `None`.
        xs: Bucket center X positions, as returned alongside `grid` by
            `bucket_grid`. Accepted for a call signature matching
            `save_png`, but not otherwise used by this renderer.
        ys: Row Y positions, aligned with `grid`'s rows. Accepted for the
            same reason as `xs`.

    Returns:
        str: Multi-line ASCII heatmap, or `"(no in-range readings)"` if
        every bucket in `grid` is `None`.
    """
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
    """Render a bucketed distance grid as a PNG heatmap, if matplotlib is available.

    matplotlib is an optional dependency for this script (see module
    docstring) -- most of the scan pipeline, including the ASCII heatmap
    and CSV output, works without it, so importing it eagerly at module
    load time would force it on every user of this script just to gate
    one optional output. Deferring the import to here, inside a
    try/except, keeps it truly optional.

    Args:
        path: Destination PNG file path.
        grid: Bucketed distance grid, as returned by `bucket_grid`, i.e.
            `grid[row][col]` is a `distance_mm` or `None`.
        xs: Bucket center X positions, used as the image's X extent.
        ys: Row Y positions, used as the image's Y extent.

    Returns:
        bool: `True` if the PNG was written. `False` if matplotlib isn't
        installed -- a real, meaningful outcome callers must check for
        rather than an exception, since it's the caller's call whether a
        missing optional dependency is worth warning about (see `main`).
    """
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
    """Construct the robot this script will scan with.

    No calibration is built or needed here -- this script only ever
    drives raw motor microsteps (see module docstring), so a bare `Robot`
    with just a transport and a rear ultrasonic sensor is enough when
    `config` isn't given. When `config` is given, the full config-loaded
    robot is used instead (its own transport/axis overrides apply); any
    calibration it happens to carry is simply unused by this script.

    Args:
        port: Serial port for real hardware (e.g. `"COM6"`), or `None`
            to use the in-memory `SimulatedTransport`. Ignored if
            `config` is given.
        config: Path to a robot config YAML to load instead of building
            a bare robot, or `None`/empty to build one from `port` alone.

    Returns:
        tuple[Robot, SimulatedTransport | None]: The robot to scan with,
        and the `SimulatedTransport` instance if one was built here (so
        `main` can feed it synthetic terrain for the no-hardware demo),
        or `None` when `config` was given or `port` selects real
        hardware.
    """
    if config:
        return load_robot(config), None

    transport = SerialTransport(port) if port else SimulatedTransport()
    robot = Robot(transport, travel_z_mm=120)
    robot.attach(MountSide.REAR, UltrasonicSensor())
    return robot, (transport if isinstance(transport, SimulatedTransport) else None)


def main() -> None:
    """Parse CLI args, run a raster scan, and write CSV/ASCII/PNG output.

    Builds and connects a robot (real hardware via `--port`, a full
    config via `--config`, or the simulated transport with synthetic
    terrain by default -- see module docstring and `build_robot`), homes
    it unless `--skip-home` is given, then runs `scan_topography` over
    the requested (or default, axis-limit-derived) bounds. Results are
    always written to `--out` as CSV and printed as an ASCII heatmap; a
    PNG heatmap is also written to `--png` if given and matplotlib is
    installed.
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--port",
        default="COM6",
        help="serial port for real hardware (e.g. COM6); omit to use the simulated transport",
    )
    parser.add_argument(
        "--config",
        default=str(_DEFAULT_CONFIG),
        help="robot config YAML to load (transport/axis overrides + rear ultrasonic mount); "
        "pass an empty string for a bare robot with a default-configured sensor instead",
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

    robot, simulated_transport = build_robot(args.port, args.config)
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

    ys = _irange(y_min, y_max, args.row_step_microsteps)
    feed_effective = args.feed or robot.axes[AxisId.X].config.travel_speed
    row_duration_s = (x_max - x_min) / feed_effective if feed_effective else 0.0
    logger.info(
        f"Planned scan: {len(ys)} continuous row sweeps, X[{x_min}, {x_max}] each "
        f"(~{row_duration_s:.1f}s/row @ feed {feed_effective:g}), Y[{y_min}, {y_max}] "
        f"@ {args.row_step_microsteps} step, {args.samples_per_row} samples/row"
    )
    if row_duration_s < args.samples_per_row * _M412_MIN_INTERVAL_S:
        logger.warning(
            f"a row only takes ~{row_duration_s:.1f}s but {args.samples_per_row} samples "
            f"need >={args.samples_per_row * _M412_MIN_INTERVAL_S:.1f}s of M412 time alone -- "
            "the sweep will be mostly pauses. Lower --samples-per-row or --feed to fix."
        )
    if args.dry_run:
        return

    def before_sample(x, y):
        if simulated_transport is not None:
            simulated_transport.ultrasonic_mm = synthetic_height_mm(x, y)

    def on_row_start(row_idx, n_rows, y, x_start, x_end):
        logger.info(f"Row {row_idx + 1}/{n_rows}: sweeping X {x_start} -> {x_end} @ Y={y}")

    def on_sample(_row_idx, x, y, distance):
        label = "out-of-range" if distance is None else f"{distance:.1f} mm"
        logger.debug(f"({x}, {y}) -> {label}")

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
    logger.info(f"Wrote {args.out} ({len(samples)} samples)")
    grid, xs = bucket_grid(samples, x_min, x_max, ys, args.display_columns)
    logger.info("\n" + render_ascii(grid, xs, ys))

    if args.png:
        if save_png(args.png, grid, xs, ys):
            logger.info(f"Wrote {args.png}")
        else:
            logger.warning("matplotlib not installed -- skipped PNG output")


if __name__ == "__main__":
    main()
