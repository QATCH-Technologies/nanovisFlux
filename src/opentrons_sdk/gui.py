import asyncio
import json
import os
import sys
import time

# Import your existing controller
from flex_controller import FlexController
from PyQt5.QtCore import QLineF, QPointF, QRectF, Qt, QTimer  # <--- Added QLineF
from PyQt5.QtGui import (  # <--- Ensure this is imported
    QBrush,
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,  # <--- Added Import
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpacerItem,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,  # <--- Added QComboBox
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qasync import QEventLoop

# --- UTILITY WIDGETS ---


class StatusIndicator(QLabel):
    """Simple colored indicator for status (Connected, Estop, Door)."""

    def __init__(self, text, default_color="grey"):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background-color: {default_color}; color: white; padding: 5px; border-radius: 4px; font-weight: bold;"
        )

    def set_status(
        self,
        active: bool,
        active_color="green",
        inactive_color="grey",
        active_text=None,
        inactive_text=None,
    ):
        color = active_color if active else inactive_color
        text = (
            active_text
            if active and active_text
            else (inactive_text if not active and inactive_text else self.text())
        )
        self.setText(text)
        self.setStyleSheet(
            f"background-color: {color}; color: white; padding: 5px; border-radius: 4px; font-weight: bold;"
        )


# --- SECTIONS ---


class ConnectionHeader(QFrame):
    """
    Persistent Top Bar: Connection, Safety (Estop), Status (Door), and System Info.
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedHeight(100)  # Increased height slightly to fit info grid

        layout = QHBoxLayout()

        # 1. Connection Area
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        self.ip_input = QLineEdit("172.28.70.174")
        self.ip_input.setPlaceholderText("Robot IP")
        self.ip_input.setFixedWidth(120)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.handle_connect)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.handle_disconnect)
        self.disconnect_btn.setEnabled(False)

        conn_layout.addWidget(QLabel("IP:"))
        conn_layout.addWidget(self.ip_input)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addWidget(self.disconnect_btn)
        conn_group.setLayout(conn_layout)

        # 2. Status Indicators (Estop/Door)
        status_group = QGroupBox("Robot Status")
        status_layout = QHBoxLayout()

        self.estop_indicator = StatusIndicator("E-STOP: OK", default_color="green")
        self.door_indicator = StatusIndicator("DOOR: CLOSED", default_color="green")

        status_layout.addWidget(self.estop_indicator)
        status_layout.addWidget(self.door_indicator)
        status_group.setLayout(status_layout)

        # 3. System Info (NEW: Health Data)
        info_group = QGroupBox("System Info")
        info_layout = QGridLayout()
        info_layout.setContentsMargins(5, 5, 5, 5)
        info_layout.setVerticalSpacing(2)

        self.lbl_name = QLabel("Name: -")
        self.lbl_fw = QLabel("FW: -")
        self.lbl_api = QLabel("API: -")
        self.lbl_sys = QLabel("Sys: -")

        # Compact styling
        for lbl in [self.lbl_name, self.lbl_fw, self.lbl_api, self.lbl_sys]:
            lbl.setStyleSheet("font-size: 10pt; font-weight: bold; color: #444;")

        info_layout.addWidget(self.lbl_name, 0, 0)
        info_layout.addWidget(self.lbl_fw, 0, 1)
        info_layout.addWidget(self.lbl_api, 1, 0)
        info_layout.addWidget(self.lbl_sys, 1, 1)
        info_group.setLayout(info_layout)

        layout.addWidget(conn_group)
        layout.addWidget(status_group)
        layout.addWidget(info_group)
        layout.addStretch()

        self.setLayout(layout)

    @property
    def controller(self):
        try:
            return FlexController.get_instance()
        except RuntimeError:
            return None

    def handle_connect(self):
        ip = self.ip_input.text().strip()
        if not ip:
            self.log("Error: IP required")
            return

        try:
            FlexController(robot_ip=ip)
            asyncio.create_task(self._async_connect())
        except Exception as e:
            self.log(f"Init Error: {e}")

    async def _async_connect(self):
        self.log(f"Connecting to {self.ip_input.text()}...")
        self.connect_btn.setEnabled(False)
        self.ip_input.setEnabled(False)

        try:
            await self.controller.connect()
            self.log("Connected.")
            self.disconnect_btn.setEnabled(True)
            self.window().central_widget.setFocus()

            # --- Trigger Health Check AFTER Connection ---
            await self.update_health_status()

            # Here you would verify Estop/Door status via self.controller.robot
            # self.estop_indicator.set_status(...)

        except Exception as e:
            self.log(f"Connection Failed: {e}")
            self.connect_btn.setEnabled(True)
            self.ip_input.setEnabled(True)
            FlexController.reset_instance()

    async def update_health_status(self):
        """Fetches /health endpoint and updates UI labels."""
        try:
            #
            # Assumes health service returns a dict (as per previous fix)
            health_data = await self.controller.health.get_health()

            # Helper to handle Dict vs Pydantic Object safely
            def get_v(d, k):
                return (
                    d.get(k, "Unknown")
                    if isinstance(d, dict)
                    else getattr(d, k, "Unknown")
                )

            name = get_v(health_data, "name")
            fw = get_v(health_data, "fw_version")
            api = get_v(health_data, "api_version")
            sys_v = get_v(health_data, "system_version")

            self.lbl_name.setText(f"Name: {name}")
            self.lbl_fw.setText(f"FW: {fw}")
            self.lbl_api.setText(f"API: {api}")
            self.lbl_sys.setText(f"Sys: {sys_v}")

            self.log(f"System Info: {name} (FW {fw})")
        except Exception as e:
            self.log(f"Health Fetch Failed: {e}")

    def handle_disconnect(self):
        asyncio.create_task(self._async_disconnect())

    async def _async_disconnect(self):
        if self.controller:
            await self.controller.disconnect()
            FlexController.reset_instance()
            self.log("Disconnected.")

        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.ip_input.setEnabled(True)

        # Reset labels
        self.lbl_name.setText("Name: -")
        self.lbl_fw.setText("FW: -")
        self.lbl_api.setText("API: -")
        self.lbl_sys.setText("Sys: -")


# --- CUSTOM DISPLAY WIDGET (Fixed Rendering) ---
class CameraWidget(QWidget):
    """
    High-performance camera viewer.
    Polls the robot camera as fast as network/hardware permits.
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        self.is_streaming = False

        layout = QVBoxLayout()

        # 1. Standard Hardware-Accelerated Display
        self.image_label = QLabel("Camera Feed Off")
        self.image_label.setAlignment(Qt.AlignCenter)
        # Dark background provides better contrast
        self.image_label.setStyleSheet(
            "background: black; color: #555; border: 2px solid #333; font-weight: bold;"
        )
        self.image_label.setMinimumSize(400, 300)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 2. Controls
        btn_layout = QHBoxLayout()

        self.btn_toggle = QPushButton("Start Feed")
        self.btn_toggle.clicked.connect(self.toggle_stream)

        self.fps_combo = QComboBox()
        # "Max" now means literally 0ms delay between requests
        self.fps_combo.addItems(
            ["Low (2 FPS)", "Med (10 FPS)", "High (20 FPS)", "Max (Uncapped)"]
        )
        self.fps_combo.setCurrentIndex(3)  # Default to Max since you are on Ethernet

        btn_layout.addWidget(self.btn_toggle)
        btn_layout.addWidget(QLabel("Target FPS:"))
        btn_layout.addWidget(self.fps_combo)

        layout.addWidget(self.image_label)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def toggle_stream(self):
        if self.is_streaming:
            self.stop_stream()
        else:
            self.start_stream()

    def start_stream(self):
        self.is_streaming = True
        self.btn_toggle.setText("Stop Feed")
        self.btn_toggle.setStyleSheet("background-color: #ffcccb; color: black;")
        self.log("Camera stream started.")
        asyncio.create_task(self.stream_loop())

    def stop_stream(self):
        self.is_streaming = False
        self.btn_toggle.setText("Start Feed")
        self.btn_toggle.setStyleSheet("")
        self.image_label.setText("Camera Feed Off")
        self.image_label.clear()
        self.log("Camera stream stopped.")

    async def stream_loop(self):
        while self.is_streaming:
            start_time = time.time()

            try:
                ctl = FlexController.get_instance()
                img_bytes = await ctl.camera.take_picture()
                image = QImage.fromData(img_bytes)
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image)
                    w = self.image_label.width()
                    h = self.image_label.height()
                    if w > 0 and h > 0:
                        self.image_label.setPixmap(
                            pixmap.scaled(
                                w, h, Qt.KeepAspectRatio, Qt.FastTransformation
                            )
                        )

            except Exception as e:
                self.log(f"Cam Error: {e}")
                self.stop_stream()
                break
            fps_text = self.fps_combo.currentText()
            target_delay = 0.0

            if "2 FPS" in fps_text:
                target_delay = 0.5
            elif "10 FPS" in fps_text:
                target_delay = 0.1
            elif "20 FPS" in fps_text:
                target_delay = 0.05

            elapsed = time.time() - start_time
            sleep_time = max(0.0, target_delay - elapsed)
            if sleep_time == 0:
                await asyncio.sleep(0.001)
            else:
                await asyncio.sleep(sleep_time)


# --- UPDATED MANUAL CONTROL TAB ---
class ManualControlTab(QWidget):
    """
    Wrapper tab. FIX: Added handle_key_event and handle_key_release.
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        layout = QHBoxLayout()

        # Left: Movement
        self.movement_widget = MovementControlWidget(log_callback)

        # Center: Camera (Assuming CameraWidget exists in your file)
        # Re-using previous CameraWidget if you have it, otherwise standard placeholder
        self.camera_widget = CameraWidget(log_callback)

        # Right: Actions
        actions_group = QGroupBox("Robot Actions")
        actions_layout = QVBoxLayout()

        self.btn_home = QPushButton("Home Robot")
        self.btn_lights_on = QPushButton("Lights ON")
        self.btn_lights_off = QPushButton("Lights OFF")
        self.btn_identify = QPushButton("Identify (Blink)")

        self.btn_home.clicked.connect(lambda: self.safe_async(self.handle_home()))
        self.btn_lights_on.clicked.connect(
            lambda: self.safe_async(self.handle_lights(True))
        )
        self.btn_lights_off.clicked.connect(
            lambda: self.safe_async(self.handle_lights(False))
        )
        self.btn_identify.clicked.connect(
            lambda: self.safe_async(self.handle_identify())
        )

        actions_layout.addWidget(self.btn_home)
        actions_layout.addWidget(self.btn_lights_on)
        actions_layout.addWidget(self.btn_lights_off)
        actions_layout.addWidget(self.btn_identify)
        actions_layout.addStretch()
        actions_group.setLayout(actions_layout)

        layout.addWidget(self.movement_widget, stretch=1)
        layout.addWidget(self.camera_widget, stretch=3)
        layout.addWidget(actions_group, stretch=1)

        self.setLayout(layout)

    def handle_key_event(self, event):
        return self.movement_widget.handle_key_event(event)

    def handle_key_release(self, event):
        if hasattr(self.movement_widget, "handle_key_release"):
            self.movement_widget.handle_key_release(event)

    def safe_async(self, coroutine):
        asyncio.create_task(coroutine)

    async def handle_home(self):
        self.log("Homing Robot...")
        self.btn_home.setEnabled(False)
        try:
            ctl = FlexController.get_instance()
            await ctl.control.home({"target": "robot"})
            self.log("Home Complete.")
        except Exception as e:
            self.log(f"Home Failed: {e}")
        finally:
            self.btn_home.setEnabled(True)

    async def handle_lights(self, state: bool):
        try:
            ctl = FlexController.get_instance()
            await ctl.control.set_lights({"on": state})
        except Exception as e:
            self.log(f"Lights Error: {e}")

    async def handle_identify(self):
        self.btn_identify.setEnabled(False)
        try:
            ctl = FlexController.get_instance()
            await ctl.control.identify(seconds=5)
        except Exception as e:
            self.log(f"Identify Error: {e}")
        finally:
            await asyncio.sleep(1.0)
            self.btn_identify.setEnabled(True)


class XYMapWidget(QFrame):
    """
    Visual 2D representation of the Robot Deck (Top-Down).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background-color: #222; border: 2px solid #555;")
        self.setFocusPolicy(Qt.StrongFocus)
        self.MAX_X = 575.0
        self.MAX_Y = 450.0
        self.target_pos = QPointF(100.0, 100.0)
        self.current_pos = QPointF(0.0, 0.0)

    def set_current_pos(self, x, y):
        self.current_pos = QPointF(float(x), float(y))
        self.update()

    def move_target(self, dx, dy):
        new_x = max(0, min(self.MAX_X, self.target_pos.x() + dx))
        new_y = max(0, min(self.MAX_Y, self.target_pos.y() + dy))
        self.target_pos = QPointF(new_x, new_y)
        self.update()
        return new_x, new_y

    def mousePressEvent(self, event):
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return
        click_x = (event.x() / w) * self.MAX_X
        click_y = (1.0 - (event.y() / h)) * self.MAX_Y
        self.target_pos = QPointF(click_x, click_y)
        self.update()
        self.setFocus()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        def to_screen(pt):
            sx = (pt.x() / self.MAX_X) * w
            sy = (1.0 - (pt.y() / self.MAX_Y)) * h
            return QPointF(sx, sy)

        painter.setPen(QPen(QColor(60, 60, 60), 1, Qt.DotLine))
        for i in range(1, 10):
            x = (i / 10.0) * w
            y = (i / 10.0) * h
            painter.drawLine(QLineF(x, 0, x, h))
            painter.drawLine(QLineF(0, y, w, y))

        cur_scr = to_screen(self.current_pos)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 150, 255, 150)))
        painter.drawEllipse(cur_scr, 8, 8)

        tgt_scr = to_screen(self.target_pos)
        painter.setPen(QPen(QColor(255, 50, 50), 2))
        tx, ty = tgt_scr.x(), tgt_scr.y()
        painter.drawLine(QLineF(tx - 10, ty, tx + 10, ty))
        painter.drawLine(QLineF(tx, ty - 10, tx, ty + 10))

        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont("Arial", 10))
        info = f"Target: X{self.target_pos.x():.1f} Y{self.target_pos.y():.1f}"
        painter.drawText(10, h - 10, info)
        painter.end()


# --- MAIN CONTROL WIDGET (Fixed Pipette Loading) ---
class MovementControlWidget(QWidget):
    """
    Map-Based Control using 'moveToCoordinates'.
    Robustly handles Pydantic models for Pipette data.
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        self.target_mount = "left"

        # Layouts
        main_layout = QHBoxLayout()
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()

        # --- LEFT: MAP ---
        self.map_widget = XYMapWidget()
        guide = QLabel(
            "<b>WASD / Click:</b> Set X/Y Target<br><b>Q/E / Slider:</b> Set Z Target<br><b>ENTER:</b> Execute Move"
        )
        guide.setStyleSheet("color: #AAA; font-size: 10pt; margin-bottom: 5px;")

        left_layout.addWidget(guide)
        left_layout.addWidget(self.map_widget, stretch=1)

        # --- RIGHT: CONTROLS ---
        z_grp = QGroupBox("Active Mount / Pipette")
        z_layout = QHBoxLayout()
        self.rb_left = QRadioButton("Left")
        self.rb_right = QRadioButton("Right")
        self.rb_left.setChecked(True)
        self.rb_left.toggled.connect(self.update_mount)
        bg = QButtonGroup(self)
        bg.addButton(self.rb_left)
        bg.addButton(self.rb_right)
        z_layout.addWidget(self.rb_left)
        z_layout.addWidget(self.rb_right)
        z_grp.setLayout(z_layout)

        self.z_slider = QSlider(Qt.Vertical)
        self.z_slider.setRange(0, 220)
        self.z_slider.setValue(150)
        self.z_slider.setTickPosition(QSlider.TicksRight)
        self.z_slider.setTickInterval(10)
        self.z_slider.valueChanged.connect(self.update_z_label)

        self.z_label = QLabel("Z: 150mm")
        self.z_label.setAlignment(Qt.AlignCenter)
        self.z_label.setStyleSheet(
            "font-weight: bold; font-size: 12pt; color: #111;"
        )  # Fixed Color

        self.btn_execute = QPushButton("GO TO TARGET")
        self.btn_execute.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 15px;"
        )
        self.btn_execute.clicked.connect(self.execute_move)

        right_layout.addWidget(z_grp)
        right_layout.addWidget(self.z_label)
        right_layout.addWidget(self.z_slider, stretch=1)
        right_layout.addWidget(self.btn_execute)

        main_layout.addLayout(left_layout, stretch=3)
        main_layout.addLayout(right_layout, stretch=1)
        self.setLayout(main_layout)

    def update_mount(self):
        self.target_mount = "left" if self.rb_left.isChecked() else "right"

    def update_z_label(self):
        val = self.z_slider.value()
        self.z_label.setText(f"Z: {val}mm")

    # --- INPUT ---
    def handle_key_event(self, event):
        key = event.key()
        step = 10.0
        if event.modifiers() & Qt.ShiftModifier:
            step = 50.0

        if key == Qt.Key_W:
            self.map_widget.move_target(0, step)
        elif key == Qt.Key_S:
            self.map_widget.move_target(0, -step)
        elif key == Qt.Key_A:
            self.map_widget.move_target(-step, 0)
        elif key == Qt.Key_D:
            self.map_widget.move_target(step, 0)
        elif key == Qt.Key_Q:
            self.z_slider.setValue(self.z_slider.value() + int(step))
        elif key == Qt.Key_E:
            self.z_slider.setValue(self.z_slider.value() - int(step))
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            self.execute_move()
        return True

    def handle_key_release(self, event):
        pass

    # --- HELPERS ---
    def _extract_data(self, response):
        # Unwrap 'data' if present
        if isinstance(response, dict):
            return response.get("data", response)
        if hasattr(response, "data"):
            return response.data
        return response

    async def ensure_pipette_loaded(self, run_id):
        """
        Finds a pipette ID for the target mount.
        Supports both Dict and Pydantic Model responses.
        """
        ctl = FlexController.get_instance()

        # 1. Check existing run
        try:
            resp = await ctl.maintenance_run_management.get_maintenance_run(run_id)
            run_data = self._extract_data(resp)

            # run_data might be a Pydantic model or Dict
            pipettes_list = []
            if isinstance(run_data, dict):
                pipettes_list = run_data.get("pipettes", [])
            elif hasattr(run_data, "pipettes"):
                pipettes_list = run_data.pipettes

            for pip in pipettes_list:
                # Handle List Item (Model or Dict)
                p_mount = (
                    pip.get("mount")
                    if isinstance(pip, dict)
                    else getattr(pip, "mount", None)
                )
                p_id = (
                    pip.get("id") if isinstance(pip, dict) else getattr(pip, "id", None)
                )

                if p_mount == self.target_mount and p_id:
                    return p_id
        except Exception:
            pass

        # 2. Check Hardware
        try:
            hw_resp = await ctl.pipettes.get_pipettes(refresh=True)

            # --- FIX: Handle Pydantic Model 'PipettesByMount' vs Dict ---
            mount_obj = None
            if hasattr(hw_resp, self.target_mount):
                # Access via attribute (e.g. hw_resp.left)
                mount_obj = getattr(hw_resp, self.target_mount)
            elif isinstance(hw_resp, dict):
                # Access via key (e.g. hw_resp['left'])
                mount_obj = hw_resp.get(self.target_mount)

            if not mount_obj:
                self.log(f"No hardware data for '{self.target_mount}' mount.")
                return None

            # Extract Name (Model or Dict)
            name = None
            if hasattr(mount_obj, "name"):
                name = mount_obj.name  # Pydantic
            elif isinstance(mount_obj, dict):
                name = mount_obj.get("name") or mount_obj.get("pipetteName")  # Dict

            if not name:
                self.log(f"No pipette attached/detected on {self.target_mount}")
                return None

            self.log(f"Loading {name}...")

            # 3. Load it
            cmd = {
                "commandType": "loadPipette",
                "intent": "setup",
                "params": {"pipetteName": name, "mount": self.target_mount},
            }
            res = await ctl.maintenance_run_management.enqueue_maintenance_command(
                run_id, cmd, wait_until_complete=True
            )
            r_data = self._extract_data(res)

            # Check Result
            # Result could be model or dict
            result = (
                r_data.get("result")
                if isinstance(r_data, dict)
                else getattr(r_data, "result", None)
            )

            # Result could be model or dict
            pip_id = None
            if isinstance(result, dict):
                pip_id = result.get("pipetteId")
            elif hasattr(result, "pipetteId"):
                pip_id = result.pipetteId

            if pip_id:
                return pip_id
            else:
                self.log(f"Load Failed. Response: {r_data}")

        except Exception as e:
            self.log(f"Pipette Init Error: {e}")

        return None

    def execute_move(self):
        tgt_x = self.map_widget.target_pos.x()
        tgt_y = self.map_widget.target_pos.y()
        tgt_z = float(self.z_slider.value())

        self.log(f"Executing Move: X{tgt_x:.1f} Y{tgt_y:.1f} Z{tgt_z:.1f}")
        asyncio.create_task(self.async_execute(tgt_x, tgt_y, tgt_z))

    async def async_execute(self, x, y, z):
        self.btn_execute.setEnabled(False)
        self.btn_execute.setText("MOVING...")
        self.btn_execute.setStyleSheet("background-color: #e6b800; color: black;")

        try:
            ctl = FlexController.get_instance()

            # 1. Get/Create Run
            run_resp = (
                await ctl.maintenance_run_management.get_current_maintenance_run()
            )
            run_data = self._extract_data(run_resp)

            run_id = None
            if isinstance(run_data, dict):
                run_id = run_data.get("id")
            elif hasattr(run_data, "id"):
                run_id = run_data.id

            if not run_id:
                create_resp = (
                    await ctl.maintenance_run_management.create_maintenance_run({})
                )
                c_data = self._extract_data(create_resp)
                if isinstance(c_data, dict):
                    run_id = c_data.get("id")
                elif hasattr(c_data, "id"):
                    run_id = c_data.id

            if not run_id:
                raise Exception("No Run ID available")

            # 2. Get Pipette ID
            pipette_id = await self.ensure_pipette_loaded(run_id)
            if not pipette_id:
                raise Exception(f"No pipette found/loaded on {self.target_mount}")

            # 3. Send 'moveToCoordinates'
            cmd = {
                "commandType": "moveToCoordinates",
                "intent": "setup",
                "params": {
                    "pipetteId": pipette_id,
                    "coordinates": {"x": float(x), "y": float(y), "z": float(z)},
                    "speed": 400.0,
                    "forceDirect": True,
                    "minimumZHeight": 5.0,
                },
            }

            resp = await ctl.maintenance_run_management.enqueue_maintenance_command(
                run_id, cmd, wait_until_complete=True
            )

            r_data = self._extract_data(resp)
            # Check Status (Model or Dict)
            status = (
                r_data.get("status")
                if isinstance(r_data, dict)
                else getattr(r_data, "status", None)
            )

            if status == "succeeded":
                self.log("Move Complete.")
                self.map_widget.set_current_pos(x, y)
            else:
                err = (
                    r_data.get("error")
                    if isinstance(r_data, dict)
                    else getattr(r_data, "error", None)
                )
                self.log(f"Move Failed: {err}")

        except Exception as e:
            self.log(f"Exec Error: {e}")

        finally:
            self.btn_execute.setEnabled(True)
            self.btn_execute.setText("GO TO TARGET")
            self.btn_execute.setStyleSheet(
                "background-color: #4CAF50; color: white; font-weight: bold; padding: 15px;"
            )


class DataFilesWidget(QWidget):
    """
    Manages Data Files (CSV/JSON inputs) using DataFilesManagamentService.
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback

        layout = QVBoxLayout()

        # List of Files
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(QLabel("Available Data Files (IDs):"))
        layout.addWidget(self.file_list)

        # Buttons
        btn_layout = QGridLayout()

        self.btn_refresh = QPushButton("Refresh List")
        self.btn_upload = QPushButton("Upload New File")
        self.btn_download = QPushButton("Download Selected")
        self.btn_delete = QPushButton("Delete Selected")

        self.btn_refresh.clicked.connect(self.handle_refresh)
        self.btn_upload.clicked.connect(self.handle_upload)
        self.btn_download.clicked.connect(self.handle_download)
        self.btn_delete.clicked.connect(self.handle_delete)

        btn_layout.addWidget(self.btn_refresh, 0, 0)
        btn_layout.addWidget(self.btn_upload, 0, 1)
        btn_layout.addWidget(self.btn_download, 1, 0)
        btn_layout.addWidget(self.btn_delete, 1, 1)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

    def _get_selected_id(self):
        items = self.file_list.selectedItems()
        if not items:
            self.log("Error: No file selected.")
            return None
        # FIX: Retrieve the hidden ID stored in UserRole, not the display text
        return items[0].data(Qt.UserRole)

    def handle_refresh(self):
        asyncio.create_task(self.async_refresh())

    def handle_upload(self):
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Data File",
            "",
            "Data Files (*.csv *.json *.txt);;All Files (*)",
        )
        if fpath:
            asyncio.create_task(self.async_upload(fpath))

    def handle_download(self):
        file_id = self._get_selected_id()
        if file_id:
            # Ask user where to save
            save_path, _ = QFileDialog.getSaveFileName(self, "Save File As...", file_id)
            if save_path:
                asyncio.create_task(self.async_download(file_id, save_path))

    def handle_delete(self):
        file_id = self._get_selected_id()
        if file_id:
            asyncio.create_task(self.async_delete(file_id))

    # --- ASYNC WORKERS ---

    async def async_refresh(self):
        self.log("Fetching Data Files...")
        self.file_list.clear()
        try:
            ctl = FlexController.get_instance()
            # Returns raw dict (from previous fix)
            response = await ctl.data_files_management.get_all_data_files()

            files = response.get("data", [])

            for item in files:
                if isinstance(item, dict):
                    f_id = item.get("id", "Unknown")
                    f_name = item.get("name", "")
                    # Display Text: "UUID (filename.csv)"
                    display_text = f"{f_id} ({f_name})" if f_name else f_id

                    # FIX: Create item and store ID in hidden UserRole
                    list_item = QListWidgetItem(display_text)
                    list_item.setData(Qt.UserRole, f_id)
                    self.file_list.addItem(list_item)
                else:
                    # Fallback for strings
                    list_item = QListWidgetItem(str(item))
                    list_item.setData(Qt.UserRole, str(item))
                    self.file_list.addItem(list_item)

            self.log(f"Found {len(files)} data files.")
        except Exception as e:
            self.log(f"Refresh Failed: {e}")

    async def async_upload(self, file_path):
        self.log(f"Uploading {os.path.basename(file_path)}...")
        try:
            ctl = FlexController.get_instance()
            res = await ctl.data_files_management.upload_data_file(file_path)

            new_id = "Unknown"
            if hasattr(res, "data"):
                new_id = getattr(res.data, "id", "Unknown")

            self.log(f"Upload Success. ID: {new_id}")
            await self.async_refresh()
        except Exception as e:
            self.log(f"Upload Failed: {e}")

    async def async_download(self, file_id, save_path):
        self.log(f"Downloading {file_id}...")
        try:
            ctl = FlexController.get_instance()
            content_bytes = await ctl.data_files_management.download_data_file(file_id)

            with open(save_path, "wb") as f:
                f.write(content_bytes)

            self.log(f"Saved to {os.path.basename(save_path)}")
        except Exception as e:
            self.log(f"Download Failed: {e}")

    async def async_delete(self, file_id):
        self.log(f"Deleting {file_id}...")
        try:
            ctl = FlexController.get_instance()
            await ctl.data_files_management.delete_data_file(file_id)
            self.log("Delete Success.")
            await self.async_refresh()
        except Exception as e:
            self.log(f"Delete Failed: {e}")


class ProtocolsTab(QWidget):
    """
    Combines Protocol Management (Runs) and Data File Management.
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        main_layout = QVBoxLayout()

        # 1. Active Run Status (Top Bar)
        run_group = QGroupBox("Active Run Control")
        run_layout = QHBoxLayout()
        self.lbl_run_status = QLabel("State: IDLE")

        # Run Controls
        btn_play = QPushButton("Play")
        btn_pause = QPushButton("Pause")
        btn_stop = QPushButton("Stop")

        # Connect dummy actions for now
        btn_play.clicked.connect(lambda: self.log("Run: Play"))
        btn_pause.clicked.connect(lambda: self.log("Run: Pause"))
        btn_stop.clicked.connect(lambda: self.log("Run: Stop"))

        run_layout.addWidget(self.lbl_run_status)
        run_layout.addStretch()
        run_layout.addWidget(btn_play)
        run_layout.addWidget(btn_pause)
        run_layout.addWidget(btn_stop)
        run_group.setLayout(run_layout)

        main_layout.addWidget(run_group)

        # 2. Content Splitter (Protocols vs Data Files)
        splitter = QSplitter(Qt.Horizontal)

        # LEFT: Protocol List
        proto_group = QGroupBox("Protocols")
        proto_layout = QVBoxLayout()
        self.proto_list = QTextEdit()  # Placeholder for now
        self.proto_list.setReadOnly(True)
        self.proto_list.setText(
            "1. PCR_Prep_v2.py\n2. Test_Transfers.py\n(Placeholder List)"
        )

        p_btn_layout = QHBoxLayout()
        btn_p_upload = QPushButton("Upload Protocol")
        btn_p_create = QPushButton("Create Run")
        p_btn_layout.addWidget(btn_p_upload)
        p_btn_layout.addWidget(btn_p_create)

        proto_layout.addWidget(self.proto_list)
        proto_layout.addLayout(p_btn_layout)
        proto_group.setLayout(proto_layout)

        # RIGHT: Data Files (New Widget)
        data_group = QGroupBox("Data Files (CSV/JSON)")
        data_layout = QVBoxLayout()
        self.data_files_widget = DataFilesWidget(self.log)
        data_layout.addWidget(self.data_files_widget)
        data_group.setLayout(data_layout)

        splitter.addWidget(proto_group)
        splitter.addWidget(data_group)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)


class HardwareTab(QWidget):
    """
    Corresponds to 'AttachedInstruments', 'AttachedModules', 'FlexSubsystemManagement'.
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        layout = QGridLayout()

        # --- 1. Instruments (Pipettes/Gripper) ---
        inst_group = QGroupBox("Instruments")
        inst_main_layout = QVBoxLayout()

        self.inst_list_layout = QVBoxLayout()
        self.inst_list_widget = QWidget()
        self.inst_list_widget.setLayout(self.inst_list_layout)

        inst_scroll = QScrollArea()
        inst_scroll.setWidgetResizable(True)
        inst_scroll.setWidget(self.inst_list_widget)
        inst_scroll.setFixedHeight(150)

        inst_main_layout.addWidget(inst_scroll)

        self.btn_refresh_inst = QPushButton("Refresh Instruments")
        self.btn_refresh_inst.clicked.connect(
            lambda: self.handle_refresh("instruments")
        )
        inst_main_layout.addWidget(self.btn_refresh_inst)
        inst_group.setLayout(inst_main_layout)

        # --- 2. Modules ---
        mod_group = QGroupBox("Modules")
        mod_main_layout = QVBoxLayout()

        self.mod_list_layout = QVBoxLayout()
        self.mod_list_widget = QWidget()
        self.mod_list_widget.setLayout(self.mod_list_layout)

        mod_scroll = QScrollArea()
        mod_scroll.setWidgetResizable(True)
        mod_scroll.setWidget(self.mod_list_widget)
        mod_scroll.setFixedHeight(150)

        mod_main_layout.addWidget(mod_scroll)

        self.btn_refresh_mod = QPushButton("Refresh Modules")
        self.btn_refresh_mod.clicked.connect(lambda: self.handle_refresh("modules"))
        mod_main_layout.addWidget(self.btn_refresh_mod)
        mod_group.setLayout(mod_main_layout)

        # --- 3. Subsystems & Firmware (Updated) ---
        sub_group = QGroupBox("Subsystems & Firmware")
        sub_main_layout = QVBoxLayout()

        # Table with Selection Column
        self.sub_table = QTableWidget()
        self.sub_table.setColumnCount(5)
        self.sub_table.setHorizontalHeaderLabels(
            ["Select", "Subsystem", "Status", "FW Version", "Update Info"]
        )

        # Adjust Header Sizing
        header = self.sub_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Checkbox col
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Name col
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Status
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # FW
        header.setSectionResizeMode(4, QHeaderView.Stretch)  # Info

        self.sub_table.setAlternatingRowColors(True)

        # Buttons Layout
        btn_layout = QHBoxLayout()
        self.btn_check_updates = QPushButton("Check for Updates")
        self.btn_do_updates = QPushButton("Update Selected")

        self.btn_check_updates.clicked.connect(
            lambda: self.handle_refresh("subsystems")
        )
        self.btn_do_updates.clicked.connect(self.handle_batch_update)

        # Disable update button initially
        self.btn_do_updates.setEnabled(False)

        btn_layout.addWidget(self.btn_check_updates)
        btn_layout.addWidget(self.btn_do_updates)

        sub_main_layout.addWidget(self.sub_table)
        sub_main_layout.addLayout(btn_layout)
        sub_group.setLayout(sub_main_layout)

        # Layout Assembly
        layout.addWidget(inst_group, 0, 0)
        layout.addWidget(mod_group, 0, 1)
        layout.addWidget(sub_group, 1, 0, 1, 2)
        self.setLayout(layout)

        # Initial placeholders
        self.populate_list(self.inst_list_layout, ["Please Connect to Robot..."])
        self.populate_list(self.mod_list_layout, ["Please Connect to Robot..."])

    def handle_refresh(self, category):
        if category == "instruments":
            asyncio.create_task(self.refresh_instruments())
        elif category == "modules":
            asyncio.create_task(self.refresh_modules())
        elif category == "subsystems":
            asyncio.create_task(self.refresh_subsystems())

    def clear_layout(self, layout):
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def populate_list(self, layout, items, color="black"):
        self.clear_layout(layout)
        if not items:
            layout.addWidget(QLabel("No items found."))
            return
        for item in items:
            lbl = QLabel(str(item))
            if color != "black":
                lbl.setStyleSheet(f"color: {color}")
            layout.addWidget(lbl)
        layout.addStretch()

    # --- HELPERS ---
    def _get_val(self, item, attr, default=None):
        if isinstance(item, dict):
            return item.get(attr, default)
        return getattr(item, attr, default)

    # --- WORKERS ---

    async def refresh_instruments(self):
        self.log("Fetching Instruments...")
        self.btn_refresh_inst.setEnabled(False)
        try:
            ctl = FlexController.get_instance()
            response = await ctl.attached_instruments.get_instruments()
            data_list = self._get_val(response, "data", [])

            instruments = []
            for inst in data_list:
                mount = self._get_val(inst, "mount", "Unknown")
                name = self._get_val(inst, "instrumentName", "Unknown Device")
                model = self._get_val(inst, "instrumentModel", "")
                instruments.append(f"[{mount.upper()}] {name} ({model})")

            if not instruments:
                instruments = ["No instruments attached."]
            self.populate_list(self.inst_list_layout, instruments)
            self.log(f"Found {len(data_list)} instruments.")
        except Exception as e:
            self.log(f"Inst Error: {e}")
            self.populate_list(
                self.inst_list_layout, ["Error fetching instruments"], "red"
            )
        finally:
            self.btn_refresh_inst.setEnabled(True)

    async def refresh_modules(self):
        self.log("Fetching Modules...")
        self.btn_refresh_mod.setEnabled(False)
        try:
            ctl = FlexController.get_instance()
            response = await ctl.attached_modules.get_modules()
            data_list = self._get_val(response, "data", [])

            display_list = []
            for mod in data_list:
                mod_type = self._get_val(mod, "moduleType", "Unknown")
                model = self._get_val(mod, "model", "")
                status = self._get_val(mod, "status", "ready")
                serial = self._get_val(mod, "serialNumber", "N/A")
                display_list.append(
                    f"{mod_type} ({model})\n  Status: {status} | SN: {serial}"
                )

            if not display_list:
                display_list = ["No modules attached."]
            self.populate_list(self.mod_list_layout, display_list)
            self.log(f"Found {len(data_list)} modules.")
        except Exception as e:
            self.log(f"Mod Error: {e}")
            self.populate_list(self.mod_list_layout, ["Error fetching modules"], "red")
        finally:
            self.btn_refresh_mod.setEnabled(True)

    async def refresh_subsystems(self):
        self.log("Fetching Subsystems & Updates...")
        self.btn_check_updates.setEnabled(False)
        self.sub_table.setRowCount(0)
        updates_found = False

        try:
            ctl = FlexController.get_instance()
            #
            response = await ctl.flex_subsystem_management.get_subsystems_status()

            data_list = self._get_val(response, "data", [])
            self.sub_table.setRowCount(len(data_list))

            for i, sub in enumerate(data_list):
                # 1. Parsing Data
                raw_name = self._get_val(sub, "name", "Unknown")
                # Determine string name for ID
                if hasattr(raw_name, "value"):
                    name_str = raw_name.value
                elif isinstance(raw_name, dict):
                    name_str = raw_name.get("name", str(raw_name))
                else:
                    name_str = str(raw_name)

                is_ok = self._get_val(sub, "ok", False)
                fw = self._get_val(sub, "current_fw_version", "?")
                update_needed = self._get_val(sub, "fw_update_needed", False)

                # 2. Setup Checkbox Item (Column 0)
                check_item = QTableWidgetItem()
                check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                check_item.setCheckState(Qt.Unchecked)
                # Store the subsystem ID in the checkbox item for retrieval
                check_item.setData(Qt.UserRole, name_str)

                if update_needed:
                    check_item.setFlags(
                        Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
                    )
                    info_text = "Update Available"
                    updates_found = True
                else:
                    # Disable checking if no update needed
                    check_item.setFlags(Qt.NoItemFlags)
                    info_text = "Up to date"

                self.sub_table.setItem(i, 0, check_item)

                # 3. Setup Other Columns
                self.sub_table.setItem(i, 1, QTableWidgetItem(name_str))

                status_item = QTableWidgetItem("OK" if is_ok else "ERROR")
                if not is_ok:
                    status_item.setForeground(Qt.red)
                else:
                    status_item.setForeground(Qt.green)
                self.sub_table.setItem(i, 2, status_item)

                self.sub_table.setItem(i, 3, QTableWidgetItem(str(fw)))

                info_item = QTableWidgetItem(info_text)
                if update_needed:
                    info_item.setForeground(Qt.blue)
                else:
                    info_item.setForeground(Qt.gray)
                self.sub_table.setItem(i, 4, info_item)

            self.log(f"Loaded {len(data_list)} subsystems.")

            # Enable update button only if updates are actually possible
            self.btn_do_updates.setEnabled(updates_found)

        except Exception as e:
            self.log(f"Subsys Error: {e}")
            self.btn_do_updates.setEnabled(False)
        finally:
            self.btn_check_updates.setEnabled(True)

    def handle_batch_update(self):
        """Iterates through checked rows and triggers updates."""
        selected_subsystems = []
        rowCount = self.sub_table.rowCount()

        for i in range(rowCount):
            item = self.sub_table.item(i, 0)  # Checkbox column
            if item.checkState() == Qt.Checked:
                # Retrieve the ID we stored in UserRole
                sub_id = item.data(Qt.UserRole)
                selected_subsystems.append(sub_id)

        if not selected_subsystems:
            self.log("No subsystems selected.")
            return

        self.log(f"Processing updates for: {', '.join(selected_subsystems)}")
        asyncio.create_task(self.async_process_batch_update(selected_subsystems))

    async def async_process_batch_update(self, subsystems):
        self.btn_do_updates.setEnabled(False)
        self.btn_check_updates.setEnabled(False)
        try:
            ctl = FlexController.get_instance()

            for sub_name in subsystems:
                self.log(f"Sending update command for: {sub_name}...")
                #
                await ctl.flex_subsystem_management.update_subsystem(sub_name)
                # Small delay to prevent flooding if multiple selected
                await asyncio.sleep(0.5)

            self.log("All update commands sent. Please wait for completion.")
            self.log("Ideally, wait 30-60s then click 'Check for Updates'.")

        except Exception as e:
            self.log(f"Batch Update Failed: {e}")
        finally:
            self.btn_check_updates.setEnabled(True)
            # Leave update button disabled until next check re-enables it
            self.btn_do_updates.setEnabled(False)


# --- UTILITY: DECK CONFIG DIALOG ---


class DeckConfigDialog(QDialog):
    """
    Dialog to select cutout configurations.
    """

    # Flex Cutouts (A-D, 1-3)
    CUTOUT_OPTIONS = [
        "cutoutA1",
        "cutoutA2",
        "cutoutA3",
        "cutoutB1",
        "cutoutB2",
        "cutoutB3",
        "cutoutC1",
        "cutoutC2",
        "cutoutC3",
        "cutoutD1",
        "cutoutD2",
        "cutoutD3",
    ]

    # Valid Fixtures for Flex
    FIXTURE_OPTIONS = [
        # --- Standard Slots (Match Column!) ---
        "singleLeftSlot",  # For Col 1
        "singleCenterSlot",  # For Col 2
        "singleRightSlot",  # For Col 3
        # --- Staging Areas (Col 3 only) ---
        "stagingAreaRightSlot",
        # --- Trash & Waste (Col 3 only usually) ---
        "trashBinAdapter",
        "wasteChuteRightAdapterCovered",
        "wasteChuteRightAdapterNoCover",
        "stagingAreaSlotWithWasteChuteRightAdapterCovered",
        "stagingAreaSlotWithWasteChuteRightAdapterNoCover",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Deck Configuration")
        self.resize(550, 400)
        self.rows = []

        layout = QVBoxLayout()

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Cutout ID</b> (Location)"))
        header.addWidget(QLabel("<b>Fixture ID</b> (Device)"))
        header.addSpacing(40)
        layout.addLayout(header)

        # Scroll Area
        self.scroll_widget = QWidget()
        self.row_layout = QVBoxLayout()
        self.row_layout.addStretch()
        self.scroll_widget.setLayout(self.row_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.scroll_widget)
        layout.addWidget(scroll)

        # Helper Text
        help_lbl = QLabel(
            "Note: Col 1=Left, Col 2=Center, Col 3=Right.\n"
            "Ensure Fixture matches Column (e.g. A3 -> Right)."
        )
        help_lbl.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(help_lbl)

        # Buttons
        btn_add = QPushButton("+ Add Override")
        btn_add.clicked.connect(self.add_row)

        btn_box = QHBoxLayout()
        self.btn_save = QPushButton("Apply Changes")
        self.btn_cancel = QPushButton("Cancel")

        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_cancel)

        layout.addWidget(btn_add)
        layout.addLayout(btn_box)
        self.setLayout(layout)

        self.add_row()

    def add_row(self):
        row_widget = QFrame()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)

        cutout_combo = QComboBox()
        cutout_combo.addItems(self.CUTOUT_OPTIONS)

        fixture_combo = QComboBox()
        fixture_combo.addItems(self.FIXTURE_OPTIONS)

        btn_del = QPushButton("X")
        btn_del.setFixedWidth(25)
        btn_del.setStyleSheet("color: red; font-weight: bold;")
        btn_del.clicked.connect(lambda: self.remove_row(row_widget))

        row_layout.addWidget(cutout_combo, stretch=1)
        row_layout.addWidget(fixture_combo, stretch=2)
        row_layout.addWidget(btn_del)
        row_widget.setLayout(row_layout)

        self.row_layout.insertWidget(self.row_layout.count() - 1, row_widget)
        self.rows.append((row_widget, cutout_combo, fixture_combo))

    def remove_row(self, widget):
        for i, (w, c, f) in enumerate(self.rows):
            if w == widget:
                w.deleteLater()
                self.rows.pop(i)
                break

    def get_data(self):
        result = []
        for _, c_combo, f_combo in self.rows:
            result.append(
                {
                    "cutoutId": c_combo.currentText(),
                    "cutoutFixtureId": f_combo.currentText(),
                }
            )
        return result


class CalibrationTab(QWidget):
    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        layout = QVBoxLayout()

        # --- 1. Status ---
        status_group = QGroupBox("Calibration Health")
        status_layout = QVBoxLayout()
        self.lbl_cal_status = QLabel("UNKNOWN")
        self.lbl_cal_status.setAlignment(Qt.AlignCenter)
        self.lbl_cal_status.setStyleSheet(
            "font-size: 18pt; font-weight: bold; color: gray;"
        )

        self.lbl_cal_summary = QLabel("Last Modified: N/A")
        self.lbl_cal_summary.setAlignment(Qt.AlignCenter)

        self.txt_cal_details = QTextEdit()
        self.txt_cal_details.setReadOnly(True)
        self.txt_cal_details.setAcceptRichText(True)
        self.txt_cal_details.setMaximumHeight(150)

        btn_refresh_cal = QPushButton("Check Calibration Status")
        btn_refresh_cal.clicked.connect(self.handle_refresh_status)

        status_layout.addWidget(self.lbl_cal_status)
        status_layout.addWidget(self.lbl_cal_summary)
        status_layout.addWidget(self.txt_cal_details)
        status_layout.addWidget(btn_refresh_cal)
        status_group.setLayout(status_layout)

        # --- 2. Deck Configuration ---
        deck_group = QGroupBox("Deck Configuration")
        deck_layout = QVBoxLayout()

        self.deck_table = QTableWidget()
        self.deck_table.setColumnCount(2)
        self.deck_table.setHorizontalHeaderLabels(["Cutout ID", "Fixture ID"])
        self.deck_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.deck_table.setAlternatingRowColors(True)
        self.deck_table.setMaximumHeight(200)

        btn_layout = QHBoxLayout()
        btn_refresh_deck = QPushButton("Refresh")
        btn_set_deck = QPushButton("Modify Configuration...")

        btn_refresh_deck.clicked.connect(self.handle_refresh_deck)
        btn_set_deck.clicked.connect(self.handle_set_deck_config)

        btn_layout.addWidget(btn_refresh_deck)
        btn_layout.addWidget(btn_set_deck)

        deck_layout.addWidget(self.deck_table)
        deck_layout.addLayout(btn_layout)
        deck_group.setLayout(deck_layout)

        # --- 3. Wizards ---
        wiz_group = QGroupBox("Wizards (Disabled)")
        wiz_layout = QHBoxLayout()
        wiz_layout.addWidget(QPushButton("Deck Calibration", enabled=False))
        wiz_layout.addWidget(QPushButton("Pipette Offset", enabled=False))
        wiz_layout.addWidget(QPushButton("Tip Length", enabled=False))
        wiz_group.setLayout(wiz_layout)

        layout.addWidget(status_group)
        layout.addWidget(deck_group)
        layout.addWidget(wiz_group)
        layout.addStretch()
        self.setLayout(layout)

    # --- HELPERS ---
    def _get_val(self, item, attr, default=None):
        if isinstance(item, dict):
            return item.get(attr, default)
        return getattr(item, attr, default)

    # --- HANDLERS ---
    def handle_refresh_status(self):
        asyncio.create_task(self.async_refresh_status())

    def handle_refresh_deck(self):
        asyncio.create_task(self.async_refresh_deck())

    def handle_set_deck_config(self):
        dlg = DeckConfigDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            changes = dlg.get_data()
            if changes:
                # Trigger the FETCH -> MERGE -> PUSH workflow
                asyncio.create_task(self.async_merge_and_set_deck(changes))

    async def async_refresh_status(self):
        self.log("Checking Calibration Status...")
        try:
            ctl = FlexController.get_instance()
            #
            full_data = await ctl.deck_calibration.get_calibration_status()

            # 1. Parse Deck Data
            deck_cal = full_data.get("deckCalibration", {})

            # Status
            status_val = deck_cal.get("status", "UNKNOWN")
            status_str = (
                status_val.get("status", "UNKNOWN")
                if isinstance(status_val, dict)
                else str(status_val)
            )

            # Metadata
            cal_data = deck_cal.get("data", {})
            last_mod = cal_data.get("lastModified", "N/A")
            pipette_id = cal_data.get("pipetteCalibratedWith", "N/A")
            matrix = cal_data.get("matrix", [])

            # 2. Update Header UI
            self.lbl_cal_status.setText(status_str.upper())
            self.lbl_cal_summary.setText(
                f"Last Modified: {last_mod}\nCalibrated With: {pipette_id}"
            )

            if "OK" in status_str.upper():
                self.lbl_cal_status.setStyleSheet(
                    "color: green; font-size: 18pt; font-weight: bold;"
                )
            elif "BAD" in status_str.upper():
                self.lbl_cal_status.setStyleSheet(
                    "color: red; font-size: 18pt; font-weight: bold;"
                )
            else:
                self.lbl_cal_status.setStyleSheet(
                    "color: orange; font-size: 18pt; font-weight: bold;"
                )

            # 3. BUILD HTML OUTPUT
            html = """
            <style>
                th { text-align: left; background-color: #f2f2f2; padding: 4px; }
                td { padding: 4px; border-bottom: 1px solid #ddd; }
                h3 { margin-bottom: 5px; color: #333; }
            </style>
            """

            # --- Deck Matrix Table ---
            html += "<h3>Deck Calibration Matrix</h3>"
            if matrix:
                html += "<table width='100%' cellspacing='0'>"
                for row in matrix:
                    html += "<tr>"
                    for val in row:
                        # Format to 4 decimal places for cleanliness
                        html += f"<td width='33%'>{float(val):.4f}</td>"
                    html += "</tr>"
                html += "</table>"
            else:
                html += "<p>No matrix data available.</p>"

            # --- Instrument Offsets Table ---
            html += "<br><h3>Instrument Offsets</h3>"
            inst_cal = full_data.get("instrumentCalibration", {})

            if inst_cal:
                html += "<table width='100%' cellspacing='0'>"
                html += "<tr><th>Mount</th><th>Type</th><th>Vector (x, y, z)</th></tr>"

                for mount, mount_data in inst_cal.items():
                    # mount is 'left' or 'right'
                    for pip_type, vector in mount_data.items():
                        # pip_type is 'single' or 'multi'
                        # Format vector: [0.0, 0.0, 0.0] -> "(0.00, 0.00, 0.00)"
                        vec_str = (
                            ", ".join([f"{v:.2f}" for v in vector])
                            if vector
                            else "None"
                        )

                        html += f"<tr><td><b>{mount.title()}</b></td>"
                        html += f"<td>{pip_type.title()}</td>"
                        html += f"<td>({vec_str})</td></tr>"
                html += "</table>"
            else:
                html += "<p>No instrument calibration data found.</p>"

            self.txt_cal_details.setHtml(html)
            self.log(f"Calibration Status: {status_str}")

        except Exception as e:
            self.log(f"Cal Check Failed: {e}")
            self.lbl_cal_status.setText("ERROR")
            self.lbl_cal_status.setStyleSheet(
                "color: red; font-size: 18pt; font-weight: bold;"
            )
            self.txt_cal_details.setText(str(e))

    async def async_refresh_deck(self):
        self.log("Fetching Deck Configuration...")
        self.deck_table.setRowCount(0)
        try:
            ctl = FlexController.get_instance()
            #
            response = await ctl.flex_deck_configuration.get_deck_configuration()

            # Extract list from response
            data_obj = self._get_val(response, "data", {})
            fixtures_list = self._get_val(data_obj, "cutoutFixtures", [])

            # Populate Table
            self.deck_table.setRowCount(len(fixtures_list))
            for i, fixture in enumerate(fixtures_list):
                c_id = self._get_val(fixture, "cutoutId", "Unknown")
                f_id = self._get_val(fixture, "cutoutFixtureId", "None")
                self.deck_table.setItem(i, 0, QTableWidgetItem(str(c_id)))
                self.deck_table.setItem(i, 1, QTableWidgetItem(str(f_id)))

            self.log(f"Loaded {len(fixtures_list)} deck items.")

            # --- CRITICAL FIX: Return the list so it can be used for merging ---
            return fixtures_list

        except Exception as e:
            self.log(f"Deck Refresh Failed: {e}")
            return []

    async def async_merge_and_set_deck(self, user_changes):
        """
        1. Fetches current config (all slots).
        2. Merges user changes (only specific slots).
        3. Pushes the combined full list.
        """
        self.log("Merging deck configuration...")
        try:
            # 1. Fetch current list
            current_fixtures = await self.async_refresh_deck()

            if current_fixtures is None:
                current_fixtures = []

            # 2. Map current config for easy updating: { 'cutoutA1': 'singleStandardSlot', ... }
            config_map = {}
            for item in current_fixtures:
                c_id = self._get_val(item, "cutoutId")
                f_id = self._get_val(item, "cutoutFixtureId")
                if c_id:
                    config_map[c_id] = f_id

            # 3. Apply User Overrides
            for change in user_changes:
                c_id = change["cutoutId"]
                f_id = change["cutoutFixtureId"]
                config_map[c_id] = f_id  # Update specific slot

            # 4. Rebuild the Full List
            final_payload = []
            for c_id, f_id in config_map.items():
                final_payload.append({"cutoutId": c_id, "cutoutFixtureId": f_id})

            # 5. Push Full List
            self.log(f"Pushing {len(final_payload)} items to robot...")
            ctl = FlexController.get_instance()
            #
            await ctl.flex_deck_configuration.set_deck_configuration(final_payload)

            self.log("Deck configuration update SUCCESS.")
            await self.async_refresh_deck()

        except Exception as e:
            self.log(f"Update Failed: {e}")


class SystemTab(QWidget):
    """
    Corresponds to 'Logs', 'SystemSettings', 'ClientData', 'ErrorRecovery'.
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        layout = QVBoxLayout()

        # --- 1. System Logs (NEW) ---
        log_group = QGroupBox("System Logs")
        log_layout = QVBoxLayout()

        # Controls Row
        ctrl_layout = QHBoxLayout()

        self.log_selector = QComboBox()
        self.log_selector.addItems(
            [
                "api.log",
                "serial.log",
                "can_bus.log",
                "server.log",
                "combined_api_server.log",
                "update_server.log",
                "touchscreen.log",
            ]
        )

        self.record_count = QSpinBox()
        self.record_count.setRange(100, 50000)
        self.record_count.setValue(2000)
        self.record_count.setSingleStep(500)
        self.record_count.setSuffix(" lines")

        self.btn_fetch_log = QPushButton("Fetch Log")
        self.btn_fetch_log.clicked.connect(self.handle_fetch_log)

        ctrl_layout.addWidget(QLabel("File:"))
        ctrl_layout.addWidget(self.log_selector)
        ctrl_layout.addWidget(QLabel("Limit:"))
        ctrl_layout.addWidget(self.record_count)
        ctrl_layout.addWidget(self.btn_fetch_log)

        # Display Area
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText(
            "Select a log file and click 'Fetch Log' to view contents..."
        )
        self.log_display.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 10pt;"
        )

        log_layout.addLayout(ctrl_layout)
        log_layout.addWidget(self.log_display)
        log_group.setLayout(log_layout)

        # --- 2. Error Recovery ---
        rec_group = QGroupBox("Error Recovery Settings")
        rec_layout = QHBoxLayout()

        self.lbl_recovery_status = QLabel("Status: UNKNOWN")
        self.lbl_recovery_status.setStyleSheet("font-weight: bold; color: gray;")

        btn_rec_enable = QPushButton("Enable")
        btn_rec_disable = QPushButton("Disable")
        btn_rec_reset = QPushButton("Reset Defaults")

        btn_rec_enable.clicked.connect(lambda: self.handle_set_recovery(True))
        btn_rec_disable.clicked.connect(lambda: self.handle_set_recovery(False))
        btn_rec_reset.clicked.connect(self.handle_reset_recovery)

        btn_rec_refresh = QPushButton("Refresh Status")
        btn_rec_refresh.clicked.connect(self.handle_get_recovery)

        rec_layout.addWidget(self.lbl_recovery_status)
        rec_layout.addStretch()
        rec_layout.addWidget(btn_rec_enable)
        rec_layout.addWidget(btn_rec_disable)
        rec_layout.addWidget(btn_rec_reset)
        rec_layout.addWidget(btn_rec_refresh)
        rec_group.setLayout(rec_layout)

        # --- 3. Client Data ---
        data_group = QGroupBox("Client Data (Ephemeral)")
        data_layout = QVBoxLayout()

        key_layout = QHBoxLayout()
        self.data_key_input = QLineEdit()
        self.data_key_input.setPlaceholderText("Key (e.g. 'offset')")
        key_layout.addWidget(QLabel("Key:"))
        key_layout.addWidget(self.data_key_input)

        self.data_val_input = QTextEdit()
        self.data_val_input.setPlaceholderText('{"x": 10} - JSON Value')
        self.data_val_input.setMaximumHeight(50)

        btn_layout = QHBoxLayout()
        self.btn_get_data = QPushButton("GET")
        self.btn_set_data = QPushButton("SET")
        self.btn_del_data = QPushButton("DEL")
        self.btn_clr_data = QPushButton("CLR ALL")

        self.btn_get_data.clicked.connect(self.handle_get_data)
        self.btn_set_data.clicked.connect(self.handle_set_data)
        self.btn_del_data.clicked.connect(self.handle_delete_data)
        self.btn_clr_data.clicked.connect(self.handle_clear_all)

        btn_layout.addWidget(self.btn_get_data)
        btn_layout.addWidget(self.btn_set_data)
        btn_layout.addWidget(self.btn_del_data)
        btn_layout.addWidget(self.btn_clr_data)

        data_layout.addLayout(key_layout)
        data_layout.addWidget(self.data_val_input)
        data_layout.addLayout(btn_layout)
        data_group.setLayout(data_layout)

        # Layout
        layout.addWidget(log_group, stretch=2)  # Give logs more space
        layout.addWidget(rec_group)
        layout.addWidget(data_group)
        self.setLayout(layout)

        # Initial Refresh
        QTimer.singleShot(1000, self.handle_get_recovery)

    # --- HELPERS ---
    def _get_val(self, item, attr, default=None):
        if isinstance(item, dict):
            return item.get(attr, default)
        return getattr(item, attr, default)

    # --- LOG HANDLERS ---
    def handle_fetch_log(self):
        filename = self.log_selector.currentText()
        count = self.record_count.value()
        asyncio.create_task(self.async_fetch_logs(filename, count))

    async def async_fetch_logs(self, filename, count):
        self.log(f"Fetching {count} lines from {filename}...")
        self.log_display.setText("Loading...")
        self.btn_fetch_log.setEnabled(False)
        try:
            ctl = FlexController.get_instance()
            #
            # Calls GET /logs/{identifier}
            log_content = await ctl.logs.get_logs(
                log_identifier=filename, format="text", records=count
            )

            # The API might return a huge string or a JSON object depending on the client parser.
            # We assume text for now.
            if isinstance(log_content, dict):
                self.log_display.setText(json.dumps(log_content, indent=2))
            else:
                self.log_display.setText(str(log_content))

            self.log(f"Loaded {len(str(log_content))} bytes.")

        except Exception as e:
            self.log_display.setText(f"Error fetching logs:\n{e}")
            self.log(f"Log Fetch Error: {e}")
        finally:
            self.btn_fetch_log.setEnabled(True)

    # --- ERROR RECOVERY HANDLERS ---

    def handle_get_recovery(self):
        # Wraps the async call safely
        asyncio.create_task(self.async_get_recovery())

    def handle_set_recovery(self, enabled):
        asyncio.create_task(self.async_set_recovery(enabled))

    def handle_reset_recovery(self):
        asyncio.create_task(self.async_reset_recovery())

    async def async_get_recovery(self):
        try:
            ctl = FlexController.get_instance()
            #
            resp = await ctl.error_recovery_settings.get_error_recovery_settings()

            data_obj = self._get_val(resp, "data", {})
            is_enabled = self._get_val(data_obj, "enabled", False)

            self._update_rec_label(is_enabled)
            self.log(f"Recovery Settings: Enabled={is_enabled}")
        except RuntimeError:
            # Squelch error if robot not connected yet on startup
            self.lbl_recovery_status.setText("Status: Not Connected")
        except Exception as e:
            self.log(f"Get Recovery Error: {e}")
            self.lbl_recovery_status.setText("Status: ERROR")

    async def async_set_recovery(self, enabled):
        action = "Enabling" if enabled else "Disabling"
        self.log(f"{action} Error Recovery...")
        try:
            ctl = FlexController.get_instance()
            resp = await ctl.error_recovery_settings.patch_error_recovery_settings(
                enabled
            )

            data_obj = self._get_val(resp, "data", {})
            is_enabled = self._get_val(data_obj, "enabled", False)

            self._update_rec_label(is_enabled)
            self.log(f"Recovery is now {'ENABLED' if is_enabled else 'DISABLED'}")
        except Exception as e:
            self.log(f"Set Recovery Error: {e}")

    async def async_reset_recovery(self):
        self.log("Resetting Recovery Settings...")
        try:
            ctl = FlexController.get_instance()
            resp = await ctl.error_recovery_settings.reset_error_recovery_settings()

            data_obj = self._get_val(resp, "data", {})
            is_enabled = self._get_val(data_obj, "enabled", False)

            self._update_rec_label(is_enabled)
            self.log("Recovery settings reset to default.")
        except Exception as e:
            self.log(f"Reset Error: {e}")

    def _update_rec_label(self, enabled):
        if enabled:
            self.lbl_recovery_status.setText("Status: ENABLED")
            self.lbl_recovery_status.setStyleSheet("font-weight: bold; color: green;")
        else:
            self.lbl_recovery_status.setText("Status: DISABLED")
            self.lbl_recovery_status.setStyleSheet("font-weight: bold; color: red;")

    # --- CLIENT DATA HANDLERS ---

    def _get_key(self):
        key = self.data_key_input.text().strip()
        if not key:
            self.log("Error: Key is required.")
            return None
        return key

    def handle_get_data(self):
        key = self._get_key()
        if key:
            asyncio.create_task(self.async_get_data(key))

    def handle_set_data(self):
        key = self._get_key()
        if not key:
            return
        raw_json = self.data_val_input.toPlainText()
        try:
            val_dict = json.loads(raw_json)
            if not isinstance(val_dict, dict):
                raise ValueError("Input must be a JSON dictionary {}")
            asyncio.create_task(self.async_set_data(key, val_dict))
        except json.JSONDecodeError:
            self.log("Error: Invalid JSON format.")
        except ValueError as e:
            self.log(f"Error: {e}")

    def handle_delete_data(self):
        key = self._get_key()
        if key:
            asyncio.create_task(self.async_delete_data(key))

    def handle_clear_all(self):
        asyncio.create_task(self.async_clear_all())

    async def async_get_data(self, key):
        try:
            ctl = FlexController.get_instance()
            data = await ctl.client_data.get_client_data(key)
            self.log(f"GET '{key}': {json.dumps(data)}")
            self.data_val_input.setText(json.dumps(data, indent=2))
        except Exception as e:
            self.log(f"GET Failed: {e}")

    async def async_set_data(self, key, val_dict):
        try:
            ctl = FlexController.get_instance()
            await ctl.client_data.update_client_data(key, val_dict)
            self.log(f"SET '{key}' success.")
        except Exception as e:
            self.log(f"SET Failed: {e}")

    async def async_delete_data(self, key):
        try:
            ctl = FlexController.get_instance()
            await ctl.client_data.delete_client_data(key)
            self.log(f"DELETE '{key}' success.")
            self.data_val_input.clear()
        except Exception as e:
            self.log(f"DELETE Failed: {e}")

    async def async_clear_all(self):
        try:
            ctl = FlexController.get_instance()
            await ctl.client_data.delete_all_client_data()
            self.log("All client data cleared.")
            self.data_key_input.clear()
            self.data_val_input.clear()
        except Exception as e:
            self.log(f"CLEAR Failed: {e}")


# --- DIALOGS ---

# ... (imports remain the same) ...


class AddOffsetDialog(QDialog):
    """Dialog to create a new Labware Offset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Labware Offset")
        self.resize(400, 300)

        layout = QVBoxLayout()
        form = QFormLayout()

        # 1. Definition URI
        self.uri_input = QLineEdit()
        self.uri_input.setPlaceholderText("opentrons/tip_rack_1000ul/1")
        form.addRow("Definition URI:", self.uri_input)

        # 2. Slot / Addressable Area
        self.slot_input = QComboBox()
        # Flex Addressable Areas (Just the coordinates, not 'cutoutA1')
        slots = [
            "A1",
            "A2",
            "A3",
            "A4",
            "B1",
            "B2",
            "B3",
            "B4",
            "C1",
            "C2",
            "C3",
            "C4",
            "D1",
            "D2",
            "D3",
            "D4",
        ]
        self.slot_input.addItems(slots)
        form.addRow("Slot (Addressable Area):", self.slot_input)

        # 3. Vector (X, Y, Z)
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-100.0, 100.0)
        self.spin_x.setDecimals(2)

        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-100.0, 100.0)
        self.spin_y.setDecimals(2)

        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(-100.0, 100.0)
        self.spin_z.setDecimals(2)

        vec_layout = QHBoxLayout()
        vec_layout.addWidget(QLabel("X:"))
        vec_layout.addWidget(self.spin_x)
        vec_layout.addWidget(QLabel("Y:"))
        vec_layout.addWidget(self.spin_y)
        vec_layout.addWidget(QLabel("Z:"))
        vec_layout.addWidget(self.spin_z)

        form.addRow("Vector (mm):", vec_layout)

        layout.addLayout(form)

        # Buttons
        btn_box = QHBoxLayout()
        self.btn_save = QPushButton("Add Offset")
        self.btn_cancel = QPushButton("Cancel")

        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        btn_box.addWidget(self.btn_save)
        btn_box.addWidget(self.btn_cancel)

        layout.addStretch()
        layout.addLayout(btn_box)
        self.setLayout(layout)

    def get_data(self):
        """Constructs the offset payload dictionary."""
        uri = self.uri_input.text().strip()
        slot = self.slot_input.currentText()
        x = self.spin_x.value()
        y = self.spin_y.value()
        z = self.spin_z.value()

        if not uri:
            return None

        # --- FIX: Use 'onAddressableArea' instead of 'onCutout' ---
        return {
            "definitionUri": uri,
            "locationSequence": [
                {
                    "kind": "onAddressableArea",  # Correct Tag
                    "addressableAreaName": slot,  # e.g., "A1" (not "cutoutA1")
                }
            ],
            "vector": {"x": x, "y": y, "z": z},
        }


# --- MAIN TAB ---


class LabwareTab(QWidget):
    """
    Corresponds to 'LabwareOffsetManagementService'.
    Displays stored Labware Offsets (LPC results).
    """

    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        layout = QVBoxLayout()

        # --- 1. Labware Offsets (Modern) ---
        offset_group = QGroupBox("Stored Labware Offsets")
        offset_layout = QVBoxLayout()

        # Search Bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by Labware URI...")
        self.btn_search = QPushButton("Search")
        self.btn_clear_search = QPushButton("Clear")

        self.btn_search.clicked.connect(self.handle_search)
        self.btn_clear_search.clicked.connect(self.handle_clear_search)

        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.btn_search)
        search_layout.addWidget(self.btn_clear_search)

        # Table
        self.offset_table = QTableWidget()
        self.offset_table.setColumnCount(5)
        self.offset_table.setHorizontalHeaderLabels(
            ["ID", "Definition URI", "Slot", "Vector (x,y,z)", "Created At"]
        )
        self.offset_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.offset_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.offset_table.setSelectionMode(QTableWidget.SingleSelection)
        self.offset_table.setAlternatingRowColors(True)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("+ Add Offset")  # New
        self.btn_refresh = QPushButton("Refresh List")
        self.btn_del_sel = QPushButton("Delete Selected")
        self.btn_del_all = QPushButton("Delete ALL")

        self.btn_add.clicked.connect(self.handle_add_offset)
        self.btn_refresh.clicked.connect(self.handle_refresh)
        self.btn_del_sel.clicked.connect(self.handle_delete_selected)
        self.btn_del_all.clicked.connect(self.handle_delete_all)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_del_sel)
        btn_layout.addWidget(self.btn_del_all)

        offset_layout.addLayout(search_layout)
        offset_layout.addWidget(self.offset_table)
        offset_layout.addLayout(btn_layout)
        offset_group.setLayout(offset_layout)

        # --- 2. Legacy Info ---
        legacy_group = QGroupBox("Legacy Calibration")
        legacy_layout = QHBoxLayout()
        legacy_lbl = QLabel(
            "Note: Use 'Labware Offsets' for Flex (generated via LPC). Legacy calibration endpoints are deprecated."
        )
        legacy_lbl.setStyleSheet("color: gray; font-style: italic;")
        legacy_layout.addWidget(legacy_lbl)
        legacy_group.setLayout(legacy_layout)

        layout.addWidget(offset_group)
        layout.addWidget(legacy_group)
        self.setLayout(layout)

    # --- HANDLERS ---

    def handle_refresh(self):
        asyncio.create_task(self.async_refresh_offsets())

    def handle_search(self):
        query = self.search_input.text().strip()
        if not query:
            self.handle_refresh()
            return
        asyncio.create_task(self.async_search_offsets(query))

    def handle_clear_search(self):
        self.search_input.clear()
        self.handle_refresh()

    def handle_add_offset(self):
        dlg = AddOffsetDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            if data:
                asyncio.create_task(self.async_add_offset(data))
            else:
                self.log("Add Offset: URI is required.")

    def handle_delete_selected(self):
        rows = self.offset_table.selectionModel().selectedRows()
        if not rows:
            self.log("No offset selected.")
            return
        row_idx = rows[0].row()
        offset_id = self.offset_table.item(row_idx, 0).text()
        asyncio.create_task(self.async_delete_offset(offset_id))

    def handle_delete_all(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText("Are you sure you want to delete ALL labware offsets?")
        msg.setInformativeText("This cannot be undone.")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        if msg.exec_() == QMessageBox.Yes:
            asyncio.create_task(self.async_delete_all())

    # --- HELPERS ---
    def _get_val(self, item, attr, default=None):
        if isinstance(item, dict):
            return item.get(attr, default)
        return getattr(item, attr, default)

    def _populate_table(self, data_list):
        self.offset_table.setRowCount(0)
        self.offset_table.setRowCount(len(data_list))
        for i, item in enumerate(data_list):
            o_id = self._get_val(item, "id", "Unknown")
            uri = self._get_val(item, "definitionUri", "Unknown")
            created = self._get_val(item, "createdAt", "Unknown")

            # Location
            loc_data = self._get_val(item, "location", {})
            slot = self._get_val(loc_data, "slotName", "N/A")

            # Vector
            vec_data = self._get_val(item, "vector", {})
            x = self._get_val(vec_data, "x", 0)
            y = self._get_val(vec_data, "y", 0)
            z = self._get_val(vec_data, "z", 0)
            vec_str = f"({x:.2f}, {y:.2f}, {z:.2f})"

            self.offset_table.setItem(i, 0, QTableWidgetItem(str(o_id)))
            self.offset_table.setItem(i, 1, QTableWidgetItem(str(uri)))
            self.offset_table.setItem(i, 2, QTableWidgetItem(str(slot)))
            self.offset_table.setItem(i, 3, QTableWidgetItem(vec_str))
            self.offset_table.setItem(i, 4, QTableWidgetItem(str(created)))
        self.log(f"Loaded {len(data_list)} offsets.")

    # --- WORKERS ---

    async def async_refresh_offsets(self):
        self.log("Fetching Labware Offsets...")
        try:
            ctl = FlexController.get_instance()
            #
            response = await ctl.labware_offset_management.get_labware_offsets()
            data_list = self._get_val(response, "data", [])
            self._populate_table(data_list)
        except Exception as e:
            self.log(f"Offset Refresh Failed: {e}")

    async def async_search_offsets(self, query):
        self.log(f"Searching offsets for '{query}'...")
        try:
            ctl = FlexController.get_instance()
            # Construct search payload
            #
            search_payload = {"filters": [{"definitionUri": query}]}
            response = await ctl.labware_offset_management.search_labware_offsets(
                search_payload
            )
            data_list = self._get_val(response, "data", [])
            self._populate_table(data_list)
        except Exception as e:
            self.log(f"Search Failed: {e}")

    async def async_add_offset(self, offset_data):
        self.log("Adding new offset...")
        try:
            ctl = FlexController.get_instance()
            #
            # API supports adding a single offset or list
            await ctl.labware_offset_management.add_labware_offsets(offset_data)
            self.log("Offset added successfully.")
            await self.async_refresh_offsets()
        except Exception as e:
            self.log(f"Add Offset Failed: {e}")

    async def async_delete_offset(self, offset_id):
        self.log(f"Deleting offset {offset_id}...")
        try:
            ctl = FlexController.get_instance()
            await ctl.labware_offset_management.delete_labware_offset(offset_id)
            self.log("Deleted.")
            await self.async_refresh_offsets()
        except Exception as e:
            self.log(f"Delete Failed: {e}")

    async def async_delete_all(self):
        self.log("Deleting ALL offsets...")
        try:
            ctl = FlexController.get_instance()
            await ctl.labware_offset_management.delete_all_labware_offsets()
            self.log("All offsets deleted.")
            await self.async_refresh_offsets()
        except Exception as e:
            self.log(f"Delete All Failed: {e}")


# --- MAIN WINDOW ---


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Opentrons Flex Control Center")
        self.resize(1000, 700)

        # Central Container
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        # 1. Global Logging Area (Bottom)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(120)

        # 2. Header (Top)
        self.header = ConnectionHeader(self.log_message)
        main_layout.addWidget(self.header)

        # 3. Main Tabs
        self.tabs = QTabWidget()

        # Init Tab Widgets
        self.tab_manual = ManualControlTab(self.log_message)
        self.tab_protocols = ProtocolsTab(self.log_message)
        self.tab_hardware = HardwareTab(self.log_message)
        self.tab_calibration = CalibrationTab(self.log_message)
        self.tab_system = SystemTab(self.log_message)
        self.tab_labware = LabwareTab(self.log_message)  #

        self.tabs.addTab(self.tab_manual, "Manual Control")
        self.tabs.addTab(self.tab_protocols, "Protocols & Runs")
        self.tabs.addTab(self.tab_hardware, "Hardware/FW")
        self.tabs.addTab(self.tab_labware, "Labware Offsets")
        self.tabs.addTab(self.tab_calibration, "Calibration/Deck")
        self.tabs.addTab(self.tab_system, "System Tools")

        main_layout.addWidget(self.tabs)
        main_layout.addWidget(QLabel("Application Logs:"))
        main_layout.addWidget(self.log_area)

    def log_message(self, message):
        self.log_area.append(message)
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def keyPressEvent(self, event):
        """
        Route keyboard events to Manual Control tab if active.
        """
        if self.tabs.currentWidget() == self.tab_manual:
            handled = self.tab_manual.handle_key_event(event)
            if handled:
                return
        super().keyPressEvent(event)


def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
