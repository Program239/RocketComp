
import sys
import time
from collections import deque

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QTableWidget, QTableWidgetItem, QComboBox, QLineEdit, QTextEdit,
    QFileDialog, QMessageBox, QSpinBox, QGroupBox
)

import pyqtgraph as pg
import serial
import serial.tools.list_ports


# -----------------------
# Serial Worker (Thread)
# -----------------------
class SerialWorker(QThread):
    line_received = pyqtSignal(str)
    connected = pyqtSignal(str)
    disconnected = pyqtSignal(str)

    def __init__(self, port_name, baudrate=115200, autoreconnect=True):
        super().__init__()
        self.port_name = port_name
        self.baudrate = baudrate
        self.autoreconnect = autoreconnect
        self._running = True
        self._ser = None
        self._outbox = deque()  # bytes to write

    def run(self):
        while self._running:
            # Ensure port is open
            if self._ser is None:
                try:
                    self._ser = serial.Serial(self.port_name, self.baudrate, timeout=0.1)
                    self.connected.emit(self.port_name)
                    # small warm-up
                    time.sleep(0.2)
                except Exception as e:
                    self.disconnected.emit(str(e))
                    # Backoff before retry
                    time.sleep(1.0)
                    continue

            try:
                # Write any pending commands
                while self._outbox:
                    payload = self._outbox.popleft()
                    self._ser.write(payload)

                # Read available lines
                line = self._ser.readline()
                if line:
                    try:
                        text = line.decode(errors='ignore').strip()
                        if text:
                            self.line_received.emit(text)
                    except Exception:
                        pass
                else:
                    # brief sleep to yield
                    time.sleep(0.02)

            except (serial.SerialException, OSError) as e:
                self.disconnected.emit(str(e))
                try:
                    if self._ser and self._ser.is_open:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None
                # loop will retry if autoreconnect
                if not self.autoreconnect:
                    break
                time.sleep(0.5)
            except Exception as e:
                # Unexpected, keep going
                self.disconnected.emit(str(e))
                time.sleep(0.2)

        # cleanup
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass

    def send(self, data: bytes):
        self._outbox.append(data)

    def stop(self):
        self._running = False


# -----------------------
# Main Dashboard UI
# -----------------------
class ESP32Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ESP32 Modern Dashboard")
        self.resize(1150, 720)

        self.serial_thread = None
        self.rx_log_lines = 0

        # Buffers for plots
        self.max_points = 500
        self.t_buf = deque(maxlen=self.max_points)
        self.temp_buf = deque(maxlen=self.max_points)
        self.hum_buf = deque(maxlen=self.max_points)

        # ====== Layout ======
        root = QHBoxLayout()
        left = QVBoxLayout()
        right = QVBoxLayout()
        root.addLayout(left, 3)
        root.addLayout(right, 2)
        self.setLayout(root)

        # --- Top controls (port + baud + connect) ---
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        conn_group.setLayout(conn_layout)

        self.port_combo = QComboBox()
        self.refresh_ports()
        self.baud_combo = QComboBox()
        self.baud_combo.addItems([
            "115200","921600","460800","230400","128000","57600","38400","19200","9600"
        ])
        self.baud_combo.setCurrentText("115200")

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_ports)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)

        self.status_dot = QLabel("● Disconnected")
        self.set_status(False)

        conn_layout.addWidget(QLabel("Port:"))
        conn_layout.addWidget(self.port_combo, 1)
        conn_layout.addWidget(QLabel("Baud:"))
        conn_layout.addWidget(self.baud_combo)
        conn_layout.addWidget(self.refresh_btn)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addStretch(1)
        conn_layout.addWidget(self.status_dot)

        left.addWidget(conn_group)

        # --- Live plots ---
        self.plot_widget = pg.PlotWidget(title="Live Sensors")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.addLegend()
        self.temp_curve = self.plot_widget.plot([], [], pen=pg.mkPen(width=2), name="Temp (°C)")
        self.hum_curve = self.plot_widget.plot([], [], pen=pg.mkPen(width=2), name="Humidity (%)")
        left.addWidget(self.plot_widget, 3)

        # --- Scatter example ---
        self.scatter_plot = pg.PlotWidget(title="Scatter (demo)")
        self.scatter_item = pg.ScatterPlotItem(size=8, pen=pg.mkPen(width=1))
        self.scatter_plot.addItem(self.scatter_item)
        left.addWidget(self.scatter_plot, 2)

        # Timer to keep UI updating (plot redraws etc.); data comes from serial thread signals
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.refresh_plots)
        self.ui_timer.start(80)

        # --- Right panel: controls & info ---
        ctrl_group = QGroupBox("Controls")
        ctrl_layout = QVBoxLayout()
        ctrl_group.setLayout(ctrl_layout)

        self.send_line = QLineEdit()
        self.send_line.setPlaceholderText("Type a command (e.g., LED:1) and press Send")
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_command)

        pwm_row = QHBoxLayout()
        pwm_row.addWidget(QLabel("PWM:"))
        self.pwm_slider = QSlider(Qt.Horizontal)
        self.pwm_slider.setRange(0, 255)
        self.pwm_slider.valueChanged.connect(self.on_pwm_change)
        self.pwm_val = QLabel("0")
        pwm_row.addWidget(self.pwm_slider, 1)
        pwm_row.addWidget(self.pwm_val)

        ctrl_layout.addWidget(self.send_line)
        ctrl_layout.addWidget(self.send_btn)
        ctrl_layout.addLayout(pwm_row)

        # Sampling controls
        sample_row = QHBoxLayout()
        sample_row.addWidget(QLabel("Sample every (ms):"))
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(50, 5000)
        self.sample_spin.setValue(200)
        sample_row.addWidget(self.sample_spin)
        self.poll_btn = QPushButton("Start Polling")
        self.poll_btn.setCheckable(True)
        self.poll_btn.toggled.connect(self.toggle_polling)
        sample_row.addWidget(self.poll_btn)
        sample_row.addStretch(1)
        ctrl_layout.addLayout(sample_row)

        right.addWidget(ctrl_group)

        # --- Data table ---
        self.table = QTableWidget(3, 2)
        self.table.setHorizontalHeaderLabels(["Key", "Value"])
        self.table.setItem(0, 0, QTableWidgetItem("Temp"))
        self.table.setItem(1, 0, QTableWidgetItem("Humidity"))
        self.table.setItem(2, 0, QTableWidgetItem("Status"))
        right.addWidget(self.table)

        # --- Log ---
        log_group = QGroupBox("Serial Log")
        log_layout = QVBoxLayout()
        log_group.setLayout(log_layout)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        log_layout.addWidget(self.log)

        btn_row = QHBoxLayout()
        self.clear_log_btn = QPushButton("Clear Log")
        self.clear_log_btn.clicked.connect(lambda: self.log.clear())
        self.save_log_btn = QPushButton("Save Log...")
        self.save_log_btn.clicked.connect(self.save_log)
        btn_row.addWidget(self.clear_log_btn)
        btn_row.addWidget(self.save_log_btn)
        btn_row.addStretch(1)
        log_layout.addLayout(btn_row)

        right.addWidget(log_group, 1)

        # Scatter demo timer (not from ESP32, just shows available widget)
        self.scatter_timer = QTimer()
        self.scatter_timer.timeout.connect(self.update_scatter_demo)
        self.scatter_timer.start(500)

    # ----------- Connection helpers -----------
    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.port_combo.addItem(p.device)

    def set_status(self, connected: bool):
        if connected:
            self.status_dot.setText("● Connected")
            self.status_dot.setStyleSheet("color: green; font-weight: bold;")
            self.table.setItem(2, 1, QTableWidgetItem("Connected"))
        else:
            self.status_dot.setText("● Disconnected")
            self.status_dot.setStyleSheet("color: red; font-weight: bold;")
            self.table.setItem(2, 1, QTableWidgetItem("Disconnected"))

    def toggle_connection(self):
        if self.serial_thread and self.serial_thread.isRunning():
            self.disconnect_serial()
        else:
            self.connect_serial()

    def connect_serial(self):
        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "No Port", "Please select a serial port.")
            return
        baud = int(self.baud_combo.currentText())
        self.serial_thread = SerialWorker(port, baud, autoreconnect=True)
        self.serial_thread.line_received.connect(self.handle_line)
        self.serial_thread.connected.connect(lambda _: self.set_status(True))
        self.serial_thread.disconnected.connect(lambda _: self.set_status(False))
        self.serial_thread.start()
        self.connect_btn.setText("Disconnect")

    def disconnect_serial(self):
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread.wait(1000)
            self.serial_thread = None
        self.set_status(False)
        self.connect_btn.setText("Connect")

    # ----------- Data handling -----------
    def handle_line(self, text: str):
        # Expected formats (examples):
        #   CSV:  28.42,61.1
        #   LBL:  TEMP:28.42,HUM:61.1
        #   JSON: {"temp":28.42,"hum":61.1}
        self.append_log(text)

        t = time.time()
        temp = None
        hum = None

        try:
            if text.startswith('{') and text.endswith('}'):
                # naive JSON parse without importing json for speed (optional)
                import json
                d = json.loads(text)
                temp = float(d.get("temp"))
                hum = float(d.get("hum"))
            elif "TEMP:" in text.upper() or "HUM" in text.upper():
                # label-based
                parts = text.replace(" ", "").split(",")
                for p in parts:
                    if ":" in p:
                        k, v = p.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if k.startswith("temp"):
                            temp = float(v)
                        elif k.startswith("hum"):
                            hum = float(v)
            else:
                # assume CSV
                parts = text.split(",")
                if len(parts) >= 2:
                    temp = float(parts[0])
                    hum = float(parts[1])
        except Exception:
            # Not a sensor line; ignore for plotting
            return

        if temp is not None and hum is not None:
            self.t_buf.append(t)
            self.temp_buf.append(temp)
            self.hum_buf.append(hum)
            self.table.setItem(0, 1, QTableWidgetItem(f"{temp:.2f} °C"))
            self.table.setItem(1, 1, QTableWidgetItem(f"{hum:.2f} %"))

    def refresh_plots(self):
        if len(self.t_buf) > 1:
            # Normalize time to start at 0 (seconds)
            t0 = self.t_buf[0]
            xs = [tt - t0 for tt in self.t_buf]
            self.temp_curve.setData(xs, list(self.temp_buf))
            self.hum_curve.setData(xs, list(self.hum_buf))

    # ----------- Controls -> ESP32 -----------
    def send_command(self):
        cmd = self.send_line.text().strip()
        if not cmd:
            return
        self._send_line_to_serial(cmd + "\n")

    def on_pwm_change(self, val):
        self.pwm_val.setText(str(val))
        # Example protocol: PWM:<0-255>
        self._send_line_to_serial(f"PWM:{val}\n")

    def toggle_polling(self, enabled: bool):
        # App will periodically send "READ" at the chosen interval
        if enabled:
            self.poll_btn.setText("Stop Polling")
            interval_ms = self.sample_spin.value()
            self.poll_timer = QTimer()
            self.poll_timer.timeout.connect(lambda: self._send_line_to_serial("READ\n"))
            self.poll_timer.start(interval_ms)
        else:
            self.poll_btn.setText("Start Polling")
            if hasattr(self, 'poll_timer') and self.poll_timer is not None:
                self.poll_timer.stop()
                self.poll_timer = None

    def _send_line_to_serial(self, line: str):
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.send(line.encode('utf-8'))
            self.append_log(f"> {line.strip()}")
        else:
            self.append_log("! Not connected")

    # ----------- Scatter demo (unrelated to serial) -----------
    def update_scatter_demo(self):
        import random
        xs = [random.uniform(0, 10) for _ in range(15)]
        ys = [random.uniform(0, 10) for _ in range(15)]
        self.scatter_item.setData(xs, ys)

    # ----------- Logging helpers -----------
    def append_log(self, msg: str):
        self.rx_log_lines += 1
        if self.rx_log_lines > 2000:
            # keep log manageable
            self.log.clear()
            self.rx_log_lines = 0
        self.log.append(msg)

    def save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Log", "serial_log.txt", "Text Files (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.log.toPlainText())
            except Exception as e:
                QMessageBox.critical(self, "Save Failed", str(e))


def main():
    app = QApplication(sys.argv)
    # Better looking antialiasing for pyqtgraph
    pg.setConfigOptions(antialias=True)
    w = ESP32Dashboard()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
