"""Visual routine builder: a palette of step "blocks" that can be
double-clicked or dragged into a reorderable step list, with a param form
for whichever step is selected.

The QListWidget of steps is treated as a *view* of ``routine.steps``, never
the source of truth -- every structural change (add/remove/drop) mutates
the Routine's step list first and then rebuilds the widget from it. A pure
drag-reorder is the one exception: Qt's own internal move already updates
the visual rows, so that path just reads the resulting order back (by each
item's stored ``id(step)``) into ``routine.steps`` rather than rebuilding.
"""
from __future__ import annotations
from pathlib import Path

from PyQt5.QtCore import Qt, QMimeData, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit,
                             QPushButton, QListWidget, QListWidgetItem, QAbstractItemView,
                             QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame)

from .routine_model import REGISTRY, Routine

_SIDE_CHOICES = ("left", "right", "rear")


class BlockPalette(QListWidget):
    """Available step kinds -- double-click to append, or drag onto the
    step list to insert at a specific position."""
    MIME_TYPE = "application/x-nanovisflux-step"
    add_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        for kind, cls in REGISTRY.items():
            item = QListWidgetItem(cls.label)
            item.setData(Qt.UserRole, kind)
            item.setToolTip("double-click or drag to add")
            self.addItem(item)
        self.itemDoubleClicked.connect(lambda item: self.add_requested.emit(item.data(Qt.UserRole)))

    def mimeData(self, items):
        mime = QMimeData()
        mime.setData(self.MIME_TYPE, items[0].data(Qt.UserRole).encode("utf-8"))
        return mime


class StepRow(QWidget):
    """One card in the step list: a color stripe for the step kind, its
    label + live summary, and a delete button."""

    def __init__(self, step, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        stripe = QFrame()
        stripe.setFixedWidth(4)
        stripe.setStyleSheet(f"background: {step.color}; border-radius: 2px;")
        layout.addWidget(stripe)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        title = QLabel(step.label)
        title.setStyleSheet("font-weight: 600;")
        self.subtitle = QLabel(step.summary())
        self.subtitle.setWordWrap(True)
        self.subtitle.setProperty("class", "eyebrow")
        text_col.addWidget(title)
        text_col.addWidget(self.subtitle)
        layout.addLayout(text_col, 1)

        self.btn_delete = QPushButton("✕")
        self.btn_delete.setFixedWidth(24)
        self.btn_delete.setToolTip("remove this step")
        layout.addWidget(self.btn_delete)

    def refresh_summary(self, step) -> None:
        self.subtitle.setText(step.summary())


class StepListWidget(QListWidget):
    block_dropped = pyqtSignal(str, int)   # kind, insertion row (from the palette)
    steps_changed = pyqtSignal()           # structure changed (add/remove/reorder)

    def __init__(self, routine: Routine, parent=None):
        super().__init__(parent)
        self.routine = routine
        self._rows: list = []
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)

    def rebuild(self, on_delete) -> None:
        self.clear()
        self._rows = []
        for step in self.routine.steps:
            item = QListWidgetItem(self)
            item.setData(Qt.UserRole, id(step))
            row = StepRow(step)
            row.btn_delete.clicked.connect(lambda _checked=False, s=step: on_delete(s))
            item.setSizeHint(row.sizeHint())
            self.addItem(item)
            self.setItemWidget(item, row)
            self._rows.append(row)

    def refresh_row_summary(self, row: int) -> None:
        if 0 <= row < len(self._rows):
            self._rows[row].refresh_summary(self.routine.steps[row])
            self.item(row).setSizeHint(self._rows[row].sizeHint())

    # -- drag/drop ----------------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.source() is self or event.mimeData().hasFormat(BlockPalette.MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        if event.source() is self:
            super().dropEvent(event)
            self._sync_order_from_items()
            return
        if event.mimeData().hasFormat(BlockPalette.MIME_TYPE):
            kind = bytes(event.mimeData().data(BlockPalette.MIME_TYPE)).decode("utf-8")
            row = self.indexAt(event.pos()).row()
            self.block_dropped.emit(kind, row if row >= 0 else self.count())
            event.acceptProposedAction()
            return
        event.ignore()

    def _sync_order_from_items(self) -> None:
        by_id = {id(s): s for s in self.routine.steps}
        new_order = [by_id[self.item(i).data(Qt.UserRole)] for i in range(self.count())
                    if self.item(i).data(Qt.UserRole) in by_id]
        if len(new_order) != len(self.routine.steps):
            return   # something didn't line up -- leave the model untouched
        self.routine.steps[:] = new_order
        self._rows = [self.itemWidget(self.item(i)) for i in range(self.count())]
        self.steps_changed.emit()


class ParamEditor(QWidget):
    """Dynamic param form for whichever step is currently selected, driven
    by that step class's ``param_fields``."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step = None
        self._widgets: dict = {}
        outer = QVBoxLayout(self)
        self.title = QLabel("no step selected")
        self.title.setProperty("class", "eyebrow")
        outer.addWidget(self.title)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        outer.addWidget(self.form_host)
        outer.addStretch(1)

    def set_step(self, step) -> None:
        self.step = step
        while self.form.rowCount():
            self.form.removeRow(0)
        self._widgets = {}
        if step is None:
            self.title.setText("no step selected")
            return
        self.title.setText(step.label.upper())
        if not step.param_fields:
            self.form.addRow(QLabel("(no parameters)"))
        for name, kind, _default in step.param_fields:
            widget = self._make_widget(kind, getattr(step, name))
            self.form.addRow(name.replace("_", " "), widget)
            self._widgets[name] = (kind, widget)

    def _make_widget(self, kind: str, value):
        if kind == "bool":
            w = QCheckBox()
            w.setChecked(bool(value))
            w.stateChanged.connect(lambda _s: self._commit())
            return w
        if kind == "side":
            w = QComboBox()
            w.addItems(_SIDE_CHOICES)
            w.setCurrentText(value or "left")
            w.currentTextChanged.connect(lambda _t: self._commit())
            return w
        if kind == "float":
            w = QDoubleSpinBox()
            w.setRange(-1_000_000, 1_000_000)
            w.setDecimals(2)
            w.setValue(float(value) if value is not None else 0.0)
            w.valueChanged.connect(lambda _v: self._commit())
            return w
        if kind in ("float_opt", "int_opt"):
            w = QLineEdit("" if value is None else str(value))
            w.setPlaceholderText("(none)")
            w.editingFinished.connect(self._commit)
            return w
        w = QLineEdit("" if value is None else str(value))
        w.editingFinished.connect(self._commit)
        return w

    def _commit(self) -> None:
        if self.step is None:
            return
        for name, (kind, widget) in self._widgets.items():
            if kind == "bool":
                setattr(self.step, name, widget.isChecked())
            elif kind == "side":
                setattr(self.step, name, widget.currentText())
            elif kind == "float":
                setattr(self.step, name, widget.value())
            elif kind == "float_opt":
                text = widget.text().strip()
                setattr(self.step, name, float(text) if text else None)
            elif kind == "int_opt":
                text = widget.text().strip()
                setattr(self.step, name, int(float(text)) if text else None)
            else:
                setattr(self.step, name, widget.text())
        self.changed.emit()


class RoutineBuilderWidget(QWidget):
    routine_changed = pyqtSignal()

    def __init__(self, routine: Routine, parent=None):
        super().__init__(parent)
        self.routine = routine

        root = QHBoxLayout(self)

        left_col = QVBoxLayout()
        name_row = QHBoxLayout()
        name_label = QLabel("NAME")
        name_label.setProperty("class", "eyebrow")
        self.name_edit = QLineEdit(routine.name)
        self.name_edit.editingFinished.connect(self._on_name_changed)
        name_row.addWidget(name_label)
        name_row.addWidget(self.name_edit, 1)
        left_col.addLayout(name_row)

        palette_label = QLabel("BLOCKS  ·  double-click or drag to add")
        palette_label.setProperty("class", "eyebrow")
        left_col.addWidget(palette_label)
        self.palette = BlockPalette()
        self.palette.add_requested.connect(self._append_step)
        left_col.addWidget(self.palette, 1)

        file_row = QHBoxLayout()
        self.btn_new = QPushButton("New")
        self.btn_save = QPushButton("Save…")
        self.btn_load = QPushButton("Load…")
        self.btn_new.clicked.connect(self._new_routine)
        self.btn_save.clicked.connect(self._save_routine)
        self.btn_load.clicked.connect(self._load_routine)
        for b in (self.btn_new, self.btn_save, self.btn_load):
            file_row.addWidget(b)
        left_col.addLayout(file_row)
        root.addLayout(left_col, 1)

        mid_col = QVBoxLayout()
        steps_label = QLabel("ROUTINE STEPS")
        steps_label.setProperty("class", "eyebrow")
        mid_col.addWidget(steps_label)
        self.step_list = StepListWidget(routine)
        self.step_list.block_dropped.connect(self._insert_step)
        self.step_list.currentRowChanged.connect(self._on_selection_changed)
        self.step_list.steps_changed.connect(self.routine_changed.emit)
        mid_col.addWidget(self.step_list, 1)
        root.addLayout(mid_col, 2)

        right_col = QVBoxLayout()
        self.param_editor = ParamEditor()
        self.param_editor.changed.connect(self._on_param_changed)
        right_col.addWidget(self.param_editor, 1)
        root.addLayout(right_col, 1)

        self.refresh()

    # -- structural edits ---------------------------------------------------
    def _append_step(self, kind: str) -> None:
        self.routine.steps.append(REGISTRY[kind]())
        self.refresh()
        self.step_list.setCurrentRow(self.step_list.count() - 1)

    def _insert_step(self, kind: str, row: int) -> None:
        row = max(0, min(row, len(self.routine.steps)))
        self.routine.steps.insert(row, REGISTRY[kind]())
        self.refresh()
        self.step_list.setCurrentRow(row)

    def _delete_step(self, step) -> None:
        try:
            idx = next(i for i, s in enumerate(self.routine.steps) if s is step)
        except StopIteration:
            return
        del self.routine.steps[idx]
        self.refresh()

    def refresh(self) -> None:
        self.step_list.rebuild(self._delete_step)
        self.routine_changed.emit()

    # -- selection / param edits --------------------------------------------
    def _on_selection_changed(self, row: int) -> None:
        step = self.routine.steps[row] if 0 <= row < len(self.routine.steps) else None
        self.param_editor.set_step(step)

    def _on_param_changed(self) -> None:
        row = self.step_list.currentRow()
        if row >= 0:
            self.step_list.refresh_row_summary(row)
        self.routine_changed.emit()

    # -- name / file ---------------------------------------------------------
    def _on_name_changed(self) -> None:
        self.routine.name = self.name_edit.text().strip() or "untitled routine"
        self.routine_changed.emit()

    def _new_routine(self) -> None:
        self.routine.name = "untitled routine"
        self.routine.steps = []
        self.name_edit.setText(self.routine.name)
        self.refresh()

    def _save_routine(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save routine", f"{self.routine.name}.json",
                                              "Routine (*.json)")
        if path:
            Path(path).write_text(self.routine.to_json(), encoding="utf-8")

    def _load_routine(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load routine", "", "Routine (*.json)")
        if path:
            loaded = Routine.from_json(Path(path).read_text(encoding="utf-8"))
            self.routine.name = loaded.name
            self.routine.steps = loaded.steps
            self.name_edit.setText(self.routine.name)
            self.refresh()

    def set_locked(self, locked: bool) -> None:
        self.setEnabled(not locked)
