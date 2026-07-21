"""Main window: the connection bar, deck view, manual/routine/info tabs and
the shared console assembled into one "everything visible at once"
workspace -- deck-centric, with the e-stop and connection controls pinned
at the top regardless of which right-hand tab is active."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QSplitter, QTabWidget,
                             QLabel, QPushButton, QFrame, QMessageBox, QListWidget)

from ..core import AxisId, MountSide
from ..transport import FakeTransport, SerialTransport
from ..control.jog import JogController
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
        self._position_timer.setInterval(1000)
        self._position_timer.timeout.connect(self._poll_position)

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
        self.routine_runner_widget.set_context(None, None)
        self.manual_panel.set_context(None, None, None)
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
            self.robot.home()
            self.robot.controller.set_relative()   # home() leaves G90; restore ambient jog mode
            if self.tracer:
                self.tracer.note("homed")
        except Exception as exc:
            if self.tracer:
                self.tracer.note(f"home failed: {exc}")

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
        try:
            pos = self.robot.controller.report_position()
        except Exception:
            return
        self.manual_panel.update_positions(pos)
        self._update_deck_markers(pos)

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
            MountSide.LEFT: DeckPoint(gx - _LR_HALF_SPACING_MM, gy),
            MountSide.RIGHT: DeckPoint(gx + _LR_HALF_SPACING_MM, gy),
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
