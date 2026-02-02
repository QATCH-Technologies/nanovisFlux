import asyncio
import sys

# Import your existing controller
from flex_controller import FlexController
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
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
        self.setStyleSheet(f"background-color: {default_color}; color: white; padding: 5px; border-radius: 4px; font-weight: bold;")
    
    def set_status(self, active: bool, active_color="green", inactive_color="grey", active_text=None, inactive_text=None):
        color = active_color if active else inactive_color
        text = active_text if active and active_text else (inactive_text if not active and inactive_text else self.text())
        self.setText(text)
        self.setStyleSheet(f"background-color: {color}; color: white; padding: 5px; border-radius: 4px; font-weight: bold;")

# --- SECTIONS ---

class ConnectionHeader(QFrame):
    """
    Persistent Top Bar: Connection, Safety (Estop), and Physical Status (Door).
    """
    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedHeight(80)
        
        layout = QHBoxLayout()
        
        # 1. Connection Area
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        self.ip_input = QLineEdit("192.168.1.105")
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
        
        # 2. Status Indicators
        status_group = QGroupBox("Robot Status")
        status_layout = QHBoxLayout()
        
        self.estop_indicator = StatusIndicator("E-STOP: OK", default_color="green")
        self.door_indicator = StatusIndicator("DOOR: CLOSED", default_color="green")
        
        status_layout.addWidget(self.estop_indicator)
        status_layout.addWidget(self.door_indicator)
        status_group.setLayout(status_layout)
        
        layout.addWidget(conn_group)
        layout.addWidget(status_group)
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
            self.window().central_widget.setFocus() # Focus main window for keys
            
            # Here you would verify Estop/Door status via self.controller.robot
            # self.estop_indicator.set_status(...)
            
        except Exception as e:
            self.log(f"Connection Failed: {e}")
            self.connect_btn.setEnabled(True)
            self.ip_input.setEnabled(True)
            FlexController.reset_instance()

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


class ManualControlTab(QWidget):
    """
    Corresponds to 'RobotControl' endpoints (Move, Home, Lights, Motors).
    """
    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        layout = QHBoxLayout()
        
        # Left Col: Movement (Existing logic)
        self.movement_widget = MovementControlWidget(log_callback)
        layout.addWidget(self.movement_widget, stretch=2)
        
        # Right Col: Actions
        actions_group = QGroupBox("Robot Actions")
        actions_layout = QVBoxLayout()
        
        self.btn_home = QPushButton("Home Robot")
        self.btn_lights_on = QPushButton("Lights ON")
        self.btn_lights_off = QPushButton("Lights OFF")
        self.btn_disengage = QPushButton("Disengage Motors")
        
        # Connect mocks
        self.btn_home.clicked.connect(lambda: self.log("Action: Homing Robot..."))
        self.btn_lights_on.clicked.connect(lambda: self.log("Action: Lights ON"))
        self.btn_lights_off.clicked.connect(lambda: self.log("Action: Lights OFF"))
        self.btn_disengage.clicked.connect(lambda: self.log("Action: Motors Disengaged"))

        actions_layout.addWidget(self.btn_home)
        actions_layout.addWidget(self.btn_lights_on)
        actions_layout.addWidget(self.btn_lights_off)
        actions_layout.addWidget(self.btn_disengage)
        actions_layout.addStretch()
        actions_group.setLayout(actions_layout)
        
        layout.addWidget(actions_group, stretch=1)
        self.setLayout(layout)

    def handle_key_event(self, event):
        return self.movement_widget.handle_key_event(event)


class MovementControlWidget(QWidget):
    """
    Handles WASD (XY) and QE (Z) input. (Preserved from original)
    """
    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        self.step_size = 10.0
        
        layout = QVBoxLayout()
        
        # Visual Aid
        guide = QLabel(
            "Controls:\n"
            "W/S: Y-Axis | A/D: X-Axis | Q/E: Z-Axis"
        )
        guide.setAlignment(Qt.AlignCenter)
        guide.setStyleSheet("background: #eee; padding: 10px; border-radius: 5px;")
        layout.addWidget(guide)
        
        # Controls
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(QLabel("Step (mm):"))
        self.step_input = QComboBox()
        self.step_input.addItems(["0.1", "1.0", "10.0", "50.0", "100.0"])
        self.step_input.setCurrentIndex(2)
        self.step_input.currentTextChanged.connect(self.update_step_size)
        controls_layout.addWidget(self.step_input)
        layout.addLayout(controls_layout)

        self.status_label = QLabel("Status: Idle")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        self.setLayout(layout)

    def update_step_size(self, text):
        try:
            self.step_size = float(text)
        except ValueError:
            pass

    def handle_key_event(self, event):
        key = event.key()
        axis = None
        distance = 0
        if key == Qt.Key_W: axis, distance = "y", self.step_size
        elif key == Qt.Key_S: axis, distance = "y", -self.step_size
        elif key == Qt.Key_A: axis, distance = "x", -self.step_size
        elif key == Qt.Key_D: axis, distance = "x", self.step_size
        elif key == Qt.Key_Q: axis, distance = "z", self.step_size
        elif key == Qt.Key_E: axis, distance = "z", -self.step_size

        if axis:
            asyncio.create_task(self.trigger_move(axis, distance))
            return True
        return False

    async def trigger_move(self, axis, distance):
        try:
            ctl = FlexController.get_instance()
            self.status_label.setText(f"Moving {axis.upper()} {distance}mm")
            # await ctl.motors.move_relative(axis=axis, distance=distance) # MOCK
            self.log(f"CMD: Move {axis} {distance}")
            self.status_label.setText("Idle")
        except RuntimeError:
            self.log("Error: Not Connected")
        except Exception as e:
            self.log(f"Error: {e}")

class ProtocolsTab(QWidget):
    """
    Corresponds to 'Protocols' and 'Runs' endpoints.
    """
    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        layout = QVBoxLayout()
        
        # 1. Active Run Status
        run_group = QGroupBox("Active Run Control")
        run_layout = QHBoxLayout()
        self.lbl_run_status = QLabel("State: IDLE")
        
        btn_play = QPushButton("Play")
        btn_pause = QPushButton("Pause")
        btn_stop = QPushButton("Stop")
        
        run_layout.addWidget(self.lbl_run_status)
        run_layout.addStretch()
        run_layout.addWidget(btn_play)
        run_layout.addWidget(btn_pause)
        run_layout.addWidget(btn_stop)
        run_group.setLayout(run_layout)
        
        # 2. Protocol List
        proto_group = QGroupBox("Protocol Management")
        proto_layout = QVBoxLayout()
        
        # Mock List
        self.proto_list = QTextEdit()
        self.proto_list.setReadOnly(True)
        self.proto_list.setText("1. PCR_Prep_v2.py\n2. DNA_Extract.json\n3. Test_Transfers.py")
        
        btn_layout = QHBoxLayout()
        btn_upload = QPushButton("Upload Protocol")
        btn_analyze = QPushButton("Analyze Selection")
        btn_create_run = QPushButton("Create Run from Selection")
        
        btn_layout.addWidget(btn_upload)
        btn_layout.addWidget(btn_analyze)
        btn_layout.addWidget(btn_create_run)
        
        proto_layout.addWidget(self.proto_list)
        proto_layout.addLayout(btn_layout)
        proto_group.setLayout(proto_layout)
        
        layout.addWidget(run_group)
        layout.addWidget(proto_group)
        self.setLayout(layout)


class HardwareTab(QWidget):
    """
    Corresponds to 'AttachedInstruments', 'AttachedModules', 'FlexSubsystemManagement'.
    """
    def __init__(self, log_callback):
        super().__init__()
        self.log = log_callback
        layout = QGridLayout()
        
        # Instruments (Pipettes/Gripper)
        inst_group = QGroupBox("Instruments")
        inst_layout = QVBoxLayout()
        inst_layout.addWidget(QLabel("Left: P1000 Single Gen3"))
        inst_layout.addWidget(QLabel("Right: P50 Multi Gen3"))
        inst_layout.addWidget(QLabel("Ext: Gripper Gen1"))
        inst_layout.addStretch()
        btn_refresh_inst = QPushButton("Refresh Instruments")
        inst_layout.addWidget(btn_refresh_inst)
        inst_group.setLayout(inst_layout)
        
        # Modules
        mod_group = QGroupBox("Modules")
        mod_layout = QVBoxLayout()
        mod_layout.addWidget(QLabel("Slot 1: Thermocycler"))
        mod_layout.addWidget(QLabel("Slot 3: HeaterShaker"))
        mod_layout.addStretch()
        btn_refresh_mod = QPushButton("Refresh Modules")
        mod_layout.addWidget(btn_refresh_mod)
        mod_group.setLayout(mod_layout)
        
        # Subsystems (Firmware)
        sub_group = QGroupBox("Subsystems & Firmware")
        sub_layout = QVBoxLayout()
        sub_layout.addWidget(QLabel("Gantry X: OK (FW v1.2)"))
        sub_layout.addWidget(QLabel("Gantry Y: OK (FW v1.2)"))
        sub_layout.addWidget(QLabel("Rear Panel: OK"))
        sub_layout.addStretch()
        btn_check_updates = QPushButton("Check Updates")
        sub_layout.addWidget(btn_check_updates)
        sub_group.setLayout(sub_layout)
        
        layout.addWidget(inst_group, 0, 0)
        layout.addWidget(mod_group, 0, 1)
        layout.addWidget(sub_group, 1, 0, 1, 2)
        self.setLayout(layout)


class CalibrationTab(QWidget):
    """
    Corresponds to 'Calibration', 'DeckConfig', 'Labware/Pipette Offsets'.
    """
    def __init__(self, log_callback):
        super().__init__()
        layout = QVBoxLayout()
        
        btn_deck = QPushButton("Deck Calibration")
        btn_pipette_offset = QPushButton("Pipette Offset Calibration")
        btn_tip_length = QPushButton("Tip Length Calibration")
        
        layout.addWidget(QLabel("Calibration Sessions"))
        layout.addWidget(btn_deck)
        layout.addWidget(btn_pipette_offset)
        layout.addWidget(btn_tip_length)
        
        layout.addWidget(QLabel("Deck Configuration"))
        deck_config = QTextEdit()
        deck_config.setText("Slot A1: Trash\nSlot C3: Staging Area...")
        deck_config.setMaximumHeight(100)
        layout.addWidget(deck_config)
        
        layout.addStretch()
        self.setLayout(layout)


class SystemTab(QWidget):
    """
    Corresponds to 'Networking', 'Logs', 'SystemSettings'.
    """
    def __init__(self, log_callback):
        super().__init__()
        layout = QVBoxLayout()
        
        # Network
        net_group = QGroupBox("Networking")
        net_layout = QHBoxLayout()
        net_layout.addWidget(QLabel("WiFi SSID: QATCH_Guest"))
        net_layout.addWidget(QLabel("Signal: 85%"))
        btn_net_cfg = QPushButton("Configure WiFi")
        net_layout.addWidget(btn_net_cfg)
        net_group.setLayout(net_layout)
        
        # Logs
        log_group = QGroupBox("System Logs")
        log_layout = QVBoxLayout()
        btn_download_logs = QPushButton("Download Robot Logs")
        log_layout.addWidget(btn_download_logs)
        log_group.setLayout(log_layout)
        
        # Settings
        set_group = QGroupBox("Settings")
        set_layout = QVBoxLayout()
        btn_update = QPushButton("System Update")
        btn_reset = QPushButton("Factory Reset")
        set_layout.addWidget(btn_update)
        set_layout.addWidget(btn_reset)
        set_group.setLayout(set_layout)
        
        layout.addWidget(net_group)
        layout.addWidget(log_group)
        layout.addWidget(set_group)
        layout.addStretch()
        self.setLayout(layout)


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
        
        self.tabs.addTab(self.tab_manual, "Manual Control")
        self.tabs.addTab(self.tab_protocols, "Protocols & Runs")
        self.tabs.addTab(self.tab_hardware, "Hardware")
        self.tabs.addTab(self.tab_calibration, "Calibration")
        self.tabs.addTab(self.tab_system, "System")
        
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