from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QMimeData, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import icon_utils
from .routine_model import REGISTRY, Routine
from .tokens import TOKENS

_INK = QColor(*TOKENS["flat_text"][:3])

_SIDE_CHOICES = ("left", "right", "rear")
_REF_CHOICES = ("clearance", "top", "bottom")
_HOME_AXES = ("X", "Y", "Z", "A", "B", "C")


class BlockPalette(QListWidget):
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

        self.btn_delete = QPushButton()
        self.btn_delete.setIcon(icon_utils.icon("minus_circle", _INK, size=16))
        self.btn_delete.setIconSize(QSize(16, 16))
        self.btn_delete.setFixedWidth(24)
        self.btn_delete.setToolTip("remove this step")
        layout.addWidget(self.btn_delete)

    def refresh_summary(self, step) -> None:
        self.subtitle.setText(step.summary())


class StepListWidget(QListWidget):
    block_dropped = pyqtSignal(str, int)
    steps_changed = pyqtSignal()

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
        new_order = [
            by_id[self.item(i).data(Qt.UserRole)]
            for i in range(self.count())
            if self.item(i).data(Qt.UserRole) in by_id
        ]
        if len(new_order) != len(self.routine.steps):
            return
        self.routine.steps[:] = new_order
        self._rows = [self.itemWidget(self.item(i)) for i in range(self.count())]
        self.steps_changed.emit()


class HomeAxesWidget(QWidget):
    changed = pyqtSignal()

    def __init__(self, value: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._syncing = False

        self.all_box = QCheckBox("ALL")
        layout.addWidget(self.all_box)

        selected = set(value.split())
        all_by_default = not selected
        self.axis_boxes: dict = {}
        for letter in _HOME_AXES:
            box = QCheckBox(letter)
            box.setChecked(all_by_default or letter in selected)
            box.stateChanged.connect(self._on_axis_toggled)
            layout.addWidget(box)
            self.axis_boxes[letter] = box
        layout.addStretch(1)

        self.all_box.setChecked(all(b.isChecked() for b in self.axis_boxes.values()))
        self.all_box.stateChanged.connect(self._on_all_toggled)

    def _on_all_toggled(self, _state: int) -> None:
        if self._syncing:
            return
        checked = self.all_box.isChecked()
        self._syncing = True
        for box in self.axis_boxes.values():
            box.setChecked(checked)
        self._syncing = False
        self.changed.emit()

    def _on_axis_toggled(self, _state: int) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.all_box.setChecked(all(b.isChecked() for b in self.axis_boxes.values()))
        self._syncing = False
        self.changed.emit()

    def value(self) -> str:
        return " ".join(letter for letter in _HOME_AXES if self.axis_boxes[letter].isChecked())


class ParamEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step = None
        self._robot = None
        self._widgets: dict = {}
        outer = QVBoxLayout(self)
        self.title = QLabel("no step selected")
        self.title.setProperty("class", "eyebrow")
        outer.addWidget(self.title)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        outer.addWidget(self.form_host)
        outer.addStretch(1)

    def set_robot(self, robot) -> None:
        self._robot = robot
        if self.step is not None:
            self.set_step(self.step)

    def _labware_names(self) -> list:
        return sorted(self._robot.labware.keys()) if self._robot else []

    def _well_names_for(self, labware_name: str) -> list:
        if not self._robot or labware_name not in self._robot.labware:
            return []
        return list(self._robot.labware[labware_name].wells.keys())

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
        if kind == "ref":
            w = QComboBox()
            w.addItems(_REF_CHOICES)
            w.setCurrentText(value or "clearance")
            w.currentTextChanged.connect(lambda _t: self._commit())
            return w
        if kind == "float":
            w = QDoubleSpinBox()
            w.setRange(-1_000_000, 1_000_000)
            w.setDecimals(2)
            w.setValue(float(value) if value is not None else 0.0)
            w.valueChanged.connect(lambda _v: self._commit())
            return w
        if kind == "int":
            w = QSpinBox()
            w.setRange(1, 1_000_000)
            w.setValue(int(value) if value else 1)
            w.valueChanged.connect(lambda _v: self._commit())
            return w
        if kind == "labware":
            w = QComboBox()
            w.setEditable(True)
            w.addItem("")
            w.addItems(self._labware_names())
            w.setCurrentText(value or "")
            w.currentTextChanged.connect(lambda _t: self._on_labware_changed())
            return w
        if kind == "well":
            w = QComboBox()
            w.setEditable(True)
            w.addItem("")
            w.addItems(self._well_names_for(getattr(self.step, "labware", "")))
            w.setCurrentText(value or "")
            w.currentTextChanged.connect(lambda _t: self._commit())
            return w
        if kind == "axes":
            w = HomeAxesWidget(value or "")
            w.changed.connect(self._commit)
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
            elif kind in ("side", "ref", "labware", "well"):
                setattr(self.step, name, widget.currentText())
            elif kind in ("float", "int"):
                setattr(self.step, name, widget.value())
            elif kind == "float_opt":
                text = widget.text().strip()
                setattr(self.step, name, float(text) if text else None)
            elif kind == "int_opt":
                text = widget.text().strip()
                setattr(self.step, name, int(float(text)) if text else None)
            elif kind == "axes":
                setattr(self.step, name, widget.value())
            else:
                setattr(self.step, name, widget.text())
        self.changed.emit()

    def _on_labware_changed(self) -> None:
        self._commit()
        entry = self._widgets.get("well")
        if entry is None:
            return
        _kind, well_widget = entry
        current = well_widget.currentText()
        well_widget.blockSignals(True)
        well_widget.clear()
        well_widget.addItem("")
        well_widget.addItems(self._well_names_for(getattr(self.step, "labware", "")))
        well_widget.setCurrentText(current)
        well_widget.blockSignals(False)


class RoutineBuilderWidget(QWidget):
    routine_changed = pyqtSignal()

    def __init__(self, routine: Routine, parent=None):
        super().__init__(parent)
        self.routine = routine
        self._robot = None

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
        right_col.addWidget(self.param_editor)
        self.nested_label = QLabel("REPEAT BODY  ·  double-click or drag to add")
        self.nested_label.setProperty("class", "eyebrow")
        self.nested_label.setVisible(False)
        right_col.addWidget(self.nested_label)
        self.nested_host = QVBoxLayout()
        right_col.addLayout(self.nested_host, 1)
        root.addLayout(right_col, 1)

        self.refresh()

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

    def _on_selection_changed(self, row: int) -> None:
        step = self.routine.steps[row] if 0 <= row < len(self.routine.steps) else None
        self.param_editor.set_step(step)
        self._set_nested_step(step)

    def _set_nested_step(self, step) -> None:
        while self.nested_host.count():
            item = self.nested_host.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        body = getattr(step, "body", None)
        self.nested_label.setVisible(body is not None)
        if body is None:
            return
        nested = RoutineBuilderWidget(body)
        nested.set_robot(self._robot)
        nested.routine_changed.connect(self._on_nested_changed)
        self.nested_host.addWidget(nested)

    def _on_nested_changed(self) -> None:
        row = self.step_list.currentRow()
        if row >= 0:
            self.step_list.refresh_row_summary(row)
        self.routine_changed.emit()

    def set_robot(self, robot) -> None:
        self._robot = robot
        self.param_editor.set_robot(robot)
        nested = self.nested_host.itemAt(0)
        if nested is not None and nested.widget() is not None:
            nested.widget().set_robot(robot)

    def _on_param_changed(self) -> None:
        row = self.step_list.currentRow()
        if row >= 0:
            self.step_list.refresh_row_summary(row)
        self.routine_changed.emit()

    def _on_name_changed(self) -> None:
        self.routine.name = self.name_edit.text().strip() or "untitled routine"
        self.routine_changed.emit()

    def _new_routine(self) -> None:
        self.routine.name = "untitled routine"
        self.routine.steps = []
        self.name_edit.setText(self.routine.name)
        self.refresh()

    def _save_routine(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save routine", f"{self.routine.name}.json", "Routine (*.json)"
        )
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
