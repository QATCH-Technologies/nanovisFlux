"""Executes a Routine off the UI thread, so a slow (or real, physically
blocking) serial round-trip never freezes the window, and exposes both
single-step and continuous execution -- "simulating" a routine means
stepping through it one block at a time and watching each command/response
via the shared console; "running" means the same executor in continuous
mode with live per-step status.

Each run operates on a **deep copy** of whatever routine the builder holds
at the moment Run/Step is first pressed, so editing the routine afterward
can never race with the worker thread reading it mid-run.
"""
from __future__ import annotations
import copy
import threading
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QFileDialog)

from .routine_model import Routine

_STATUS_ICON = {"pending": "○", "running": "▶", "ok": "✓", "error": "✕"}


class RoutineRunner(QThread):
    step_started = pyqtSignal(int)
    step_finished = pyqtSignal(int, bool, str)
    log = pyqtSignal(str)
    finished_run = pyqtSignal(bool)   # True iff every step completed ok

    def __init__(self, robot, routine: Routine, parent=None):
        super().__init__(parent)
        self.robot = robot
        self.routine = routine
        self._mode = threading.Event()   # set = allowed to execute the step at _cursor
        self._continuous = False
        self._stop = threading.Event()
        self._cursor = 0

    # -- control, called from the GUI thread ---------------------------------
    def step_once(self) -> None:
        self._continuous = False
        self._mode.set()

    def run_continuous(self) -> None:
        self._continuous = True
        self._mode.set()

    def pause(self) -> None:
        self._continuous = False   # takes effect at the next step boundary

    def stop(self) -> None:
        self._stop.set()
        self._mode.set()

    # -- worker thread ----------------------------------------------------------
    def run(self) -> None:
        ok_all = True
        while self._cursor < len(self.routine.steps):
            self._mode.wait()
            self._mode.clear()
            if self._stop.is_set():
                ok_all = False
                break
            i = self._cursor
            self.step_started.emit(i)
            try:
                self.routine.steps[i].run(self.robot, self.log.emit)
                self.step_finished.emit(i, True, "")
            except Exception as exc:
                self.step_finished.emit(i, False, str(exc))
                ok_all = False
                break
            self._cursor += 1
            if self._continuous and not self._stop.is_set() and self._cursor < len(self.routine.steps):
                self._mode.set()
        self.finished_run.emit(ok_all and self._cursor >= len(self.routine.steps))


class RoutineRunnerWidget(QWidget):
    """One-way status mirror of whichever routine is loaded, plus
    step/run/pause/stop/reset transport controls."""
    run_state_changed = pyqtSignal(bool)   # True while a run/step session is active

    def __init__(self, get_source_routine, parent=None):
        super().__init__(parent)
        self._get_source_routine = get_source_routine
        self.robot = None
        self.tracer = None
        self.runner: RoutineRunner | None = None
        self._routine: Routine | None = None

        root = QVBoxLayout(self)
        header = QHBoxLayout()
        self.name_label = QLabel("no routine loaded")
        self.name_label.setProperty("class", "eyebrow")
        header.addWidget(self.name_label, 1)
        self.btn_use_builder = QPushButton("Use builder routine")
        self.btn_use_builder.clicked.connect(self._use_builder_routine)
        self.btn_load = QPushButton("Load…")
        self.btn_load.clicked.connect(self._load_routine)
        header.addWidget(self.btn_use_builder)
        header.addWidget(self.btn_load)
        root.addLayout(header)

        self.list = QListWidget()
        root.addWidget(self.list, 1)

        controls = QHBoxLayout()
        self.btn_step = QPushButton("Step ▸")
        self.btn_run = QPushButton("Run ▶")
        self.btn_stop = QPushButton("Stop ■")
        self.btn_reset = QPushButton("Reset ↺")
        self.btn_step.clicked.connect(self._on_step)
        self.btn_run.clicked.connect(self._on_run_pause)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_reset.clicked.connect(self._on_reset)
        for b in (self.btn_step, self.btn_run, self.btn_stop, self.btn_reset):
            controls.addWidget(b)
        root.addLayout(controls)

        self.status_label = QLabel("idle")
        self.status_label.setProperty("class", "mono")
        root.addWidget(self.status_label)

        self._use_builder_routine()
        self._refresh_buttons()

    # -- context --------------------------------------------------------------
    def set_context(self, robot, tracer) -> None:
        self._on_stop()   # any in-flight run belongs to the outgoing robot
        self.robot = robot
        self.tracer = tracer
        self._refresh_buttons()

    def stop_run(self) -> None:
        """Public alias for MainWindow's e-stop path."""
        self._on_stop()

    # -- routine source -----------------------------------------------------------
    def _use_builder_routine(self) -> None:
        self._load_from(copy.deepcopy(self._get_source_routine()))

    def _load_routine(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load routine", "", "Routine (*.json)")
        if path:
            self._load_from(Routine.from_json(Path(path).read_text(encoding="utf-8")))

    def _load_from(self, routine: Routine) -> None:
        self._on_stop()
        self._routine = routine
        self.name_label.setText(f"{routine.name}  ·  {len(routine.steps)} steps")
        self._populate_list()
        self._refresh_buttons()

    def _populate_list(self) -> None:
        self.list.clear()
        if not self._routine:
            return
        for i, step in enumerate(self._routine.steps):
            self.list.addItem(QListWidgetItem(f"{_STATUS_ICON['pending']}  {i + 1}. {step.summary()}"))

    def _set_row_status(self, row: int, status: str, message: str = "") -> None:
        if not (0 <= row < self.list.count()):
            return
        text = f"{_STATUS_ICON[status]}  {row + 1}. {self._routine.steps[row].summary()}"
        if message:
            text += f"   — {message}"
        self.list.item(row).setText(text)
        if status == "running":
            self.list.setCurrentRow(row)

    # -- run control --------------------------------------------------------------
    def _ensure_runner(self) -> bool:
        if self.robot is None or not self._routine or not self._routine.steps:
            return False
        if self.runner is None or not self.runner.isRunning():
            self.runner = RoutineRunner(self.robot, self._routine)
            self.runner.step_started.connect(lambda i: self._set_row_status(i, "running"))
            self.runner.step_finished.connect(self._on_step_finished)
            self.runner.log.connect(lambda msg: self.tracer.note(msg) if self.tracer else None)
            self.runner.finished_run.connect(self._on_finished_run)
            self.runner.finished.connect(self._refresh_buttons)
            self.runner.start()
            self.run_state_changed.emit(True)
        return True

    def _on_step_finished(self, i: int, ok: bool, message: str) -> None:
        self._set_row_status(i, "ok" if ok else "error", message)
        if not ok and self.tracer:
            self.tracer.note(f"step {i + 1} failed: {message}")

    def _on_step(self) -> None:
        if self._ensure_runner():
            self.status_label.setText("stepping…")
            self.runner.step_once()
        self._refresh_buttons()

    def _on_run_pause(self) -> None:
        if self.runner is not None and self.runner.isRunning() and self.runner._continuous:
            self.runner.pause()
            self.status_label.setText("paused")
        elif self._ensure_runner():
            self.status_label.setText("running…")
            self.runner.run_continuous()
        self._refresh_buttons()

    def _on_stop(self) -> None:
        if self.runner is not None:
            self.runner.stop()
            self.runner.wait(2000)
        self.status_label.setText("idle")
        self.run_state_changed.emit(False)
        self._refresh_buttons()

    def _on_reset(self) -> None:
        self._on_stop()
        self._populate_list()

    def _on_finished_run(self, completed_ok: bool) -> None:
        self.status_label.setText("completed" if completed_ok else "stopped")
        self.run_state_changed.emit(False)
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        running = self.runner is not None and self.runner.isRunning()
        continuous = running and self.runner._continuous
        has_routine = bool(self._routine and self._routine.steps)
        connected = self.robot is not None
        self.btn_step.setEnabled(connected and has_routine and not continuous)
        self.btn_run.setText("Pause ⏸" if continuous else "Run ▶")
        self.btn_run.setEnabled(connected and has_routine)
        self.btn_stop.setEnabled(running)
        self.btn_reset.setEnabled(not running)
        self.btn_use_builder.setEnabled(not running)
        self.btn_load.setEnabled(not running)
