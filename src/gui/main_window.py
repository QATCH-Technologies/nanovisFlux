"""Main window: the connection bar, deck view, manual/routine/info tabs and
the shared console assembled into one "everything visible at once"
workspace -- deck-centric, with the e-stop and connection controls pinned
at the top regardless of which right-hand tab is active."""
from __future__ import annotations

import time
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QSplitter, QTabWidget,
                             QLabel, QPushButton, QFrame, QMessageBox, QListWidget)

from ..core import AxisId, MountSide
from ..transport import FakeTransport, SerialTransport
from ..control.jog import JogController
from ..motion.axis import HOMING_ORDER
from ..geometry.coordinates import DeckPoint
from .connection_bar import ConnectionBar
from .deck_view import DeckView
from .manual_control import ManualControlPanel
from .routine_model import Routine
from .routine_builder import RoutineBuilderWidget
from .routine_runner import RoutineRunnerWidget
from .console_log import ConsoleLog
from .trace import CommandTracer
from .robot_factory import build_robot
from .calibration_dialog import CalibrationDialog
from .mounts_dialog import MountsDialog

#: Fixed mechanical offsets between the gantry's single X/Y reference point
#: and each mount, in deck mm -- left/right are two separate carriages
#: 32.5 mm apart astride the reference point; the rear (ultrasonic) mount
#: sits 50 mm behind them, centered. Applied directly in deck space (not
#: motor space), which assumes the deck calibration's XY transform has
#: negligible rotation -- fine for visualization, see DeckCalibration if
#: this ever needs to be exact for a rotated calibration.
_LR_HALF_SPACING_MM = 32.5 / 2
_REAR_BEHIND_MM = 50.0

_HOMING_ANIM_INTERVAL_MS = 40  # 25 Hz -- smooth enough for a multi-second sweep


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("nanovisFlux control")
        self.resize(1320, 840)

        self.robot = None
        self.jog: JogController | None = None
        self.tracer: CommandTracer | None = None
        self.routine = Routine(name="untitled routine")

        central = QWidget()
        central.setObjectName("centralRoot")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.conn_bar = ConnectionBar()
        self.conn_bar.connect_requested.connect(self._on_connect_requested)
        self.conn_bar.disconnect_requested.connect(self._on_disconnect_requested)
        self.conn_bar.home_requested.connect(self._on_home_requested)
        self.conn_bar.estop_requested.connect(self._on_estop_requested)
        outer.addWidget(self.conn_bar)

        body_split = QSplitter(Qt.Horizontal)
        body_split.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(body_split, 1)

        # -- left: deck & labware / mounts / calibration ---------------------
        left_panel = QFrame()
        left_panel.setProperty("class", "panel")
        left_layout = QVBoxLayout(left_panel)
        deck_label = QLabel("DECK · LABWARE")
        deck_label.setProperty("class", "eyebrow")
        left_layout.addWidget(deck_label)
        self.labware_list = QListWidget()
        left_layout.addWidget(self.labware_list, 1)
        mounts_label = QLabel("MOUNTS")
        mounts_label.setProperty("class", "eyebrow")
        left_layout.addWidget(mounts_label)
        self.mounts_list = QListWidget()
        self.mounts_list.setMaximumHeight(90)
        left_layout.addWidget(self.mounts_list)
        self.btn_mounts = QPushButton("Configure Mounts…")
        self.btn_mounts.clicked.connect(self._open_mounts_dialog)
        self.btn_mounts.setEnabled(False)
        left_layout.addWidget(self.btn_mounts)
        self.btn_calibrate = QPushButton("⚙ Calibrate Deck…")
        self.btn_calibrate.clicked.connect(self._open_calibration_dialog)
        self.btn_calibrate.setEnabled(False)
        left_layout.addWidget(self.btn_calibrate)
        body_split.addWidget(left_panel)

        # -- center: deck view --------------------------------------------------
        center_panel = QFrame()
        center_panel.setProperty("class", "panel")
        center_layout = QVBoxLayout(center_panel)
        self.deck_view = DeckView()
        self.deck_view.labware_changed.connect(self._refresh_labware_list)
        center_layout.addWidget(self.deck_view, 1)
        body_split.addWidget(center_panel)

        # -- right: manual / routine / info tabs -------------------------------
        right_panel = QFrame()
        right_panel.setProperty("class", "panel")
        right_layout = QVBoxLayout(right_panel)
        self.tabs = QTabWidget()

        self.manual_panel = ManualControlPanel()
        self.manual_panel.home_requested.connect(self._on_home_requested)
        self.manual_panel.estop_requested.connect(self._on_estop_requested)
        self.tabs.addTab(self.manual_panel, "Manual")

        routine_tabs = QTabWidget()
        self.routine_builder = RoutineBuilderWidget(self.routine)
        self.routine_runner_widget = RoutineRunnerWidget(lambda: self.routine)
        self.routine_runner_widget.run_state_changed.connect(self._on_routine_run_state_changed)
        self.routine_runner_widget.step_motion.connect(self._on_routine_step_motion)
        self.routine_runner_widget.step_home.connect(self._on_routine_step_home)
        routine_tabs.addTab(self.routine_builder, "Build")
        routine_tabs.addTab(self.routine_runner_widget, "Run")
        self.tabs.addTab(routine_tabs, "Routine")

        self.info_label = QLabel("not connected")
        self.info_label.setWordWrap(True)
        self.info_label.setProperty("class", "mono")
        info_panel = QWidget()
        info_layout = QVBoxLayout(info_panel)
        info_layout.addWidget(self.info_label)
        info_layout.addStretch(1)
        self.tabs.addTab(info_panel, "Info")

        right_layout.addWidget(self.tabs)
        body_split.addWidget(right_panel)
        body_split.setSizes([220, 640, 420])

        # -- bottom: shared console ---------------------------------------------
        console_wrap = QFrame()
        console_wrap.setProperty("class", "panel")
        console_layout = QVBoxLayout(console_wrap)
        console_label = QLabel("CONSOLE")
        console_label.setProperty("class", "eyebrow")
        console_layout.addWidget(console_label)
        self.console = ConsoleLog()
        self.console.setFixedHeight(140)
        console_layout.addWidget(self.console)
        outer.addWidget(console_wrap)

        self._position_timer = QTimer(self)
        # 200ms (5 Hz): a full-length X move (60,000 microsteps at the
        # default 16,000 microsteps/s travel speed) takes ~3.75s, so 1 Hz
        # only gave ~4 marker updates across a full traverse -- visibly
        # choppy. 5 Hz keeps the deck marker tracking smoothly without
        # over-polling the transport.
        self._position_timer.setInterval(200)
        self._position_timer.timeout.connect(self._poll_position)

        # Post-home sweep: robot.home() is a single blocking call (the
        # firmware doesn't ack G28 until every requested axis has fully
        # homed), so there is no real position to poll *during* it -- this
        # timer instead replays the known homing order/speed as an
        # animation once the call returns, so the operator still sees the
        # gantry "arrive" home axis by axis rather than snapping instantly.
        self._homing_anim_timer = QTimer(self)
        self._homing_anim_timer.setInterval(_HOMING_ANIM_INTERVAL_MS)
        self._homing_anim_timer.timeout.connect(self._tick_homing_animation)
        self._homing_schedule: list = []
        self._homing_t0 = 0.0
        self._homing_display: dict = {}

        # Routine motion sweep: a routine step's G0/G1 acks long before (or,
        # in simulation, entirely unrelated to) the real move actually
        # finishing -- see FakeTransport and RoutineRunner.step_motion's
        # docstrings -- so there's no honest position to poll mid-step.
        # Same idea as the homing sweep above, but timed per move from the
        # distance it was actually commanded to cover (tracked from one
        # fresh poll at run start, then advanced by each move's own target
        # -- see _on_routine_step_motion) and its own feed rate, queued so
        # a burst of near-instant simulated steps still plays back one at a
        # time instead of overlapping.
        self._routine_anim_timer = QTimer(self)
        self._routine_anim_timer.setInterval(_HOMING_ANIM_INTERVAL_MS)
        self._routine_anim_timer.timeout.connect(self._tick_routine_animation)
        self._routine_anim_queue: list = []   # pending (before, after, duration) legs
        self._routine_anim_leg = None         # currently-playing (before, after, duration, t0)
        self._routine_display_pos: dict = {}  # last-known position, advanced leg by leg
        self._routine_run_active = False      # True while a routine Run/Step session is active

        self.setFocusPolicy(Qt.StrongFocus)
        self.conn_bar.set_status("disconnected")

    # -- connect / disconnect ---------------------------------------------------
    def _on_connect_requested(self, opts: dict) -> None:
        self.conn_bar.set_status("connecting")
        try:
            cfg = None
            if opts.get("config_path"):
                import yaml
                with open(opts["config_path"], "r") as fh:
                    cfg = yaml.safe_load(fh)

            if opts["mode"] == "real":
                if not opts["port"]:
                    raise RuntimeError("choose a serial port first")
                transport = SerialTransport(opts["port"], opts["baud"])
            else:
                transport = FakeTransport()

            robot = build_robot(cfg, transport)
            robot.connect()
        except Exception as exc:
            self.conn_bar.set_status("error", f"connect failed: {exc}")
            QMessageBox.warning(self, "Connect failed", str(exc))
            return

        self.robot = robot
        self.tracer = CommandTracer(robot)
        self.tracer.bus.event.connect(self.console.append_trace)
        self.jog = JogController(robot)
        self.jog.__enter__()   # relative-mode session for the whole connection

        mode_label = "simulated" if opts["mode"] == "sim" else f"{opts['port']} @ {opts['baud']}"
        self.conn_bar.set_status("connected", f"connected · {mode_label}")
        self.tracer.note(f"connected ({mode_label})" +
                        (f" · config: {opts['config_path']}" if opts.get("config_path") else ""))
        if robot.controller.banner:
            self.tracer.note("banner: " + " | ".join(robot.controller.banner))

        self.deck_view.set_robot(robot)
        self.manual_panel.set_context(robot, self.jog, self.tracer)
        self.routine_runner_widget.set_context(robot, self.tracer)
        self.routine_builder.set_robot(robot)
        self.btn_mounts.setEnabled(True)
        self.btn_calibrate.setEnabled(True)
        self._refresh_labware_list()
        self._refresh_mounts_list()
        self._refresh_info_panel(mode_label, opts)
        self._position_timer.start()

    def _on_disconnect_requested(self) -> None:
        self._teardown_connection()
        self.conn_bar.set_status("disconnected")

    def _teardown_connection(self) -> None:
        self._position_timer.stop()
        self._homing_anim_timer.stop()
        self.routine_runner_widget.set_context(None, None)
        self.manual_panel.set_context(None, None, None)
        self.routine_builder.set_robot(None)
        if self.jog is not None:
            try:
                self.jog.__exit__(None, None, None)
            except Exception:
                pass
        if self.tracer is not None:
            self.tracer.detach()
        if self.robot is not None:
            try:
                self.robot.disconnect()
            except Exception:
                pass
        self.robot = None
        self.jog = None
        self.tracer = None
        self.deck_view.set_robot(None)
        self.btn_mounts.setEnabled(False)
        self.btn_calibrate.setEnabled(False)
        self.labware_list.clear()
        self.mounts_list.clear()
        self.info_label.setText("not connected")

    def _on_home_requested(self) -> None:
        if self.robot is None:
            return
        try:
            start_pos = self.robot.controller.report_position()
        except Exception:
            start_pos = {}
        try:
            self.robot.home()
            self.robot.controller.set_relative()   # home() leaves G90; restore ambient jog mode
            if self.tracer:
                self.tracer.note("homed")
        except Exception as exc:
            if self.tracer:
                self.tracer.note(f"home failed: {exc}")
            return
        self._start_homing_animation(start_pos)

    # -- homing animation --------------------------------------------------
    def _build_home_schedule(self, start_pos: dict, axes) -> list:
        """Sequential per-axis sweep back to zero, in HOMING_ORDER (matching
        real firmware behavior -- a G28 homes axes one at a time, not all
        together), each timed by its own configured homing speed. Shared by
        the manual Home button's sweep (all axes) and a routine-embedded
        Home step's (whichever axes it actually asked for)."""
        want = set(axes)
        schedule = []
        t = 0.0
        for axis in HOMING_ORDER:
            if axis not in want:
                continue
            axis_obj = self.robot.axes.get(axis) if self.robot else None
            if axis_obj is None:
                continue
            start_val = start_pos.get(axis, 0) or 0
            speed = axis_obj.config.homing_speed or 0
            duration = abs(start_val) / speed if speed > 0 else 0.0
            schedule.append((axis, start_val, t, t + duration))
            t += duration
        return schedule

    def _start_homing_animation(self, start_pos: dict) -> None:
        """Replay the known homing order/speed as a sweep back to zero, axis
        by axis, once ``robot.home()`` (a single blocking G28) has returned.
        Pure GUI polish -- doesn't talk to the robot -- so it can't race the
        real position poll; that timer is paused for the duration and
        restarted (with an immediate poll) once the sweep finishes."""
        schedule = self._build_home_schedule(start_pos, tuple(AxisId))
        self._position_timer.stop()
        if not schedule:
            self._position_timer.start()
            return
        self._homing_schedule = schedule
        self._homing_display = dict(start_pos)
        self._homing_t0 = time.monotonic()
        self._homing_anim_timer.start()

    def _tick_homing_animation(self) -> None:
        elapsed = time.monotonic() - self._homing_t0
        total = self._homing_schedule[-1][3]
        for axis, start_val, t_start, t_end in self._homing_schedule:
            if elapsed >= t_end:
                self._homing_display[axis] = 0
            elif elapsed <= t_start:
                self._homing_display[axis] = start_val
            else:
                frac = (elapsed - t_start) / (t_end - t_start)
                self._homing_display[axis] = int(round(start_val * (1.0 - frac)))
        self.manual_panel.update_positions(self._homing_display)
        self._update_deck_markers(self._homing_display)
        if elapsed >= total:
            self._homing_anim_timer.stop()
            self._position_timer.start()
            self._poll_position()   # reconcile the display with the real (homed) position

    def _on_estop_requested(self) -> None:
        if self.robot is None:
            return
        self.routine_runner_widget.stop_run()
        self.manual_panel.stop_all_jog()
        try:
            self.robot.emergency_stop()
            if self.tracer:
                self.tracer.note("EMERGENCY STOP")
            QMessageBox.critical(self, "Emergency stop",
                                "Emergency stop sent. Home all axes before resuming motion.")
        except Exception as exc:
            if self.tracer:
                self.tracer.note(f"EMERGENCY STOP FAILED: {exc}")
            QMessageBox.critical(self, "Emergency stop failed", f"Could not send emergency stop: {exc}")

    # -- routine run <-> manual lock -------------------------------------------
    def _on_routine_run_state_changed(self, active: bool) -> None:
        self.manual_panel.set_routine_active(active)
        self.routine_builder.set_locked(active)
        self._routine_run_active = active
        if active:
            # A routine step's controller calls share the CommandTracer lock
            # with this timer's own M114 poll -- left running, a poll landing
            # mid-step would just block the whole GUI thread until the step's
            # commands release the lock. Pause it for the run; the per-step
            # motion sweep (see _on_routine_step_motion) covers the display
            # in the meantime, starting from one fresh poll (each leg after
            # that is derived from the step's own commanded targets, not
            # polled -- see RoutineRunner.step_motion).
            self._position_timer.stop()
            try:
                self._routine_display_pos = self.robot.controller.report_position()
            except Exception:
                self._routine_display_pos = {}
            self._routine_anim_timer.stop()
            self._routine_anim_queue = []
            self._routine_anim_leg = None
        elif not self._routine_anim_queue and self._routine_anim_leg is None:
            # Nothing left to sweep -- resume real polling right away.
            # Otherwise leave it paused: the routine itself can finish (in
            # simulation, near-instantly) well before the sweep timed to its
            # real feed rate has finished playing -- _advance_routine_animation
            # resumes polling once the queue actually drains, so a live poll
            # never fights the sweep over the same display.
            self._position_timer.start()
            self._poll_position()

    # -- routine motion sweep ---------------------------------------------------
    #: Axes with real deck-space travel -- the ones the deck view actually
    #: draws from (see _update_deck_markers/_mount_deck_z). Plunger axes
    #: (B/C) are excluded: they move during Aspirate/Dispense too, but
    #: animating them would just make e.g. a slow, feed-less aspirate hold
    #: the sweep open long after the marker itself has already arrived.
    _SPATIAL_AXES = (AxisId.X, AxisId.Y, AxisId.Z, AxisId.A)

    def _routine_leg_duration(self, before: dict, after: dict, feed) -> float:
        """How long this one G0/G1 would really take, from the distance it
        actually covers and its feed rate: the command's own explicit feed
        if it had one (a G1 with F given), else the relevant axis's
        configured travel speed (a bare G0 rapid move, or a feed-less G1,
        both leave the firmware to use its own default). Distance and rate
        are both already in microsteps/<time>, so the ratio comes out in
        real seconds without a separate mm/s conversion -- steps_per_mm
        only matters if you want to *display* the rate, not time the sweep.
        """
        durations = []
        for axis in self._SPATIAL_AXES:
            start, end = before.get(axis), after.get(axis)
            if start is None or end is None:
                continue
            distance = abs(end - start)
            if distance == 0:
                continue
            axis_obj = self.robot.axes.get(axis) if self.robot else None
            rate = feed or (axis_obj.config.travel_speed if axis_obj is not None else None)
            if rate:
                durations.append(distance / rate)
        return max(durations) if durations else 0.0

    def _on_routine_step_motion(self, legs: list) -> None:
        if not legs:
            # Nothing to sweep (Wait, a raw line, ...) -- resync so the next
            # real leg's "before" reflects what actually happened.
            try:
                self._routine_display_pos = self.robot.controller.report_position()
            except Exception:
                pass
            return
        for targets, feed in legs:
            before = dict(self._routine_display_pos)
            after = {**before, **targets}
            duration = self._routine_leg_duration(before, after, feed)
            self._routine_anim_queue.append(("move", before, after, duration))
            self._routine_display_pos = after
        if self._routine_anim_leg is None:
            self._advance_routine_animation()

    def _on_routine_step_home(self, axes: tuple) -> None:
        """A routine-embedded Home step homed ``axes`` -- queue the same
        sequential, per-axis sweep the manual Home button uses (see
        _build_home_schedule), filtered to whichever axes this step
        actually asked for. Starts from the tracked display position, not
        a live poll: a live poll here would race a still-settling
        preceding move exactly like step_motion's legs do (see its
        docstring), and G28 is instant in FakeTransport, so by the time
        one could be taken it'd already show the post-home result."""
        before = dict(self._routine_display_pos)
        schedule = self._build_home_schedule(before, axes)
        if not schedule:
            return
        for axis, *_rest in schedule:
            self._routine_display_pos[axis] = 0
        self._routine_anim_queue.append(("home", schedule))
        if self._routine_anim_leg is None:
            self._advance_routine_animation()

    def _advance_routine_animation(self) -> None:
        if not self._routine_anim_queue:
            self._routine_anim_leg = None
            self._routine_anim_timer.stop()
            if not self._routine_run_active:
                # The routine session already ended while this last leg was
                # still sweeping -- resume real polling now that it's done.
                self._position_timer.start()
                self._poll_position()
            return
        leg = self._routine_anim_queue.pop(0)
        if leg[0] == "move":
            _, before, after, duration = leg
            if duration <= 0:
                # No rate to time a sweep against (or no real distance) --
                # just show where it ended up and move on to the next leg.
                self.manual_panel.update_positions(after)
                self._update_deck_markers(after)
                self._advance_routine_animation()
                return
            self._routine_anim_leg = ("move", before, after, duration, time.monotonic())
        else:   # "home"
            _, schedule = leg
            if schedule[-1][3] <= 0:
                display = {**self._routine_display_pos, **{axis: 0 for axis, *_ in schedule}}
                self.manual_panel.update_positions(display)
                self._update_deck_markers(display)
                self._advance_routine_animation()
                return
            self._routine_anim_leg = ("home", schedule, time.monotonic())
        if not self._routine_anim_timer.isActive():
            self._routine_anim_timer.start()

    def _tick_routine_animation(self) -> None:
        if self._routine_anim_leg is None:
            return
        if self._routine_anim_leg[0] == "move":
            _, before, after, duration, t0 = self._routine_anim_leg
            frac = min(1.0, (time.monotonic() - t0) / duration)
            display = {}
            for axis in set(before) | set(after):
                start = before.get(axis, after.get(axis))
                end = after.get(axis, start)
                display[axis] = int(round(start + (end - start) * frac))
            finished = frac >= 1.0
        else:   # "home"
            _, schedule, t0 = self._routine_anim_leg
            elapsed = time.monotonic() - t0
            total = schedule[-1][3]
            display = dict(self._routine_display_pos)
            for axis, start_val, t_start, t_end in schedule:
                if elapsed >= t_end:
                    display[axis] = 0
                elif elapsed <= t_start:
                    display[axis] = start_val
                else:
                    frac = (elapsed - t_start) / (t_end - t_start)
                    display[axis] = int(round(start_val * (1.0 - frac)))
            finished = elapsed >= total
        self.manual_panel.update_positions(display)
        self._update_deck_markers(display)
        if finished:
            self._advance_routine_animation()

    # -- dialogs ------------------------------------------------------------------
    def _open_calibration_dialog(self) -> None:
        if self.robot is None:
            return
        CalibrationDialog(self.robot, self).exec_()

    def _open_mounts_dialog(self) -> None:
        if self.robot is None:
            return
        if MountsDialog(self.robot, self).exec_():
            self._refresh_mounts_list()

    # -- polling / refresh ------------------------------------------------------------
    def _poll_position(self) -> None:
        if self.robot is None:
            return
        jog = self.manual_panel.jog
        if jog is not None and jog.is_jogging:
            # A continuous jog's move is in flight with its 'ok' left
            # deliberately unread (see JogController's docstring) -- an
            # M114 sent now would read that stray reply instead of its own
            # and come back empty/wrong. Skip this tick; end_jog() already
            # re-syncs position itself the moment the jog actually stops.
            return
        try:
            pos = self.robot.controller.report_position()
        except Exception:
            return
        self.manual_panel.update_positions(pos)
        self._update_deck_markers(pos)

    def _mount_deck_z(self, side: MountSide, pos: dict) -> float:
        """Real deck-mm height of ``side``'s mount, from its vertical axis's
        raw position and the Z calibration (inverting DeckCalibration.
        deck_to_motor's z math) -- 0.0 (the DeckPoint default, which the
        deck view then falls back to _GANTRY_HEIGHT_MM for, same as before)
        wherever there's no vertical axis, no z_zero calibrated for this
        side, or no live reading yet. At home (raw 0), this correctly comes
        out near the top of travel -- home is up, see DeckCalibration's own
        docstring -- rather than the previous hardcoded ~40cm guess."""
        cal = self.robot.calibration
        axis = cal.vertical_axis(side)
        if axis is None or side not in cal.z_zero:
            return 0.0
        mz = pos.get(axis)
        if mz is None:
            return 0.0
        try:
            return cal.z_scale.to_mm(cal.z_zero[side] - mz) - self.robot.tip_offset(side)
        except Exception:
            return 0.0

    def _update_deck_markers(self, pos: dict) -> None:
        if self.robot.calibration is None:
            self.deck_view.update_positions({})
            return
        try:
            gx, gy = self.robot.calibration.motor_to_deck_xy(pos.get(AxisId.X, 0), pos.get(AxisId.Y, 0))
        except Exception:
            self.deck_view.update_positions({})
            return
        markers = {
            MountSide.LEFT: DeckPoint(gx - _LR_HALF_SPACING_MM, gy,
                                      self._mount_deck_z(MountSide.LEFT, pos)),
            MountSide.RIGHT: DeckPoint(gx + _LR_HALF_SPACING_MM, gy,
                                       self._mount_deck_z(MountSide.RIGHT, pos)),
            MountSide.REAR: DeckPoint(gx, gy + _REAR_BEHIND_MM),
        }
        self.deck_view.update_positions(markers)

    def _refresh_labware_list(self) -> None:
        self.labware_list.clear()
        if self.robot is None:
            return
        for name, lw in self.robot.labware.items():
            slot = lw.slot.name if lw.slot else "?"
            self.labware_list.addItem(f"S{slot} · {name} ({len(lw.wells)} wells)")
        self.routine_builder.set_robot(self.robot)   # refresh labware/well choices

    def _refresh_mounts_list(self) -> None:
        self.mounts_list.clear()
        if self.robot is None:
            return
        for side in (MountSide.LEFT, MountSide.RIGHT, MountSide.REAR):
            tool = self.robot.mounts[side].tool
            desc = tool.name if tool is not None else "(empty)"
            self.mounts_list.addItem(f"{side.value}: {desc}")

    def _refresh_info_panel(self, mode_label: str, opts: dict) -> None:
        lines = [
            f"transport: {mode_label}",
            f"config: {opts.get('config_path') or '(none)'}",
            f"calibrated: {'yes' if self.robot.calibration else 'no'}",
            f"deck: {'yes' if self.robot.deck else 'no'}",
            f"travel Z clearance: {self.robot.travel_z_mm} mm",
        ]
        self.info_label.setText("\n".join(lines))

    # -- keyboard jog -----------------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        if self.manual_panel.handle_key_press(event.key(), event.isAutoRepeat()):
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if self.manual_panel.handle_key_release(event.key(), event.isAutoRepeat()):
            return
        super().keyReleaseEvent(event)

    def closeEvent(self, event) -> None:
        self._teardown_connection()
        super().closeEvent(event)
