import sys
import time
from collections import deque

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QRect, QUrl
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QTableWidget, QTableWidgetItem, QComboBox, QLineEdit, QTextEdit,
    QFileDialog, QMessageBox, QSpinBox, QGroupBox, QStyleOptionSlider
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor
from PyQt5.QtWebEngineWidgets import QWebEngineView

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
        self.resize(1400, 900)

        # Buffers for plots
        self.max_points = 500
        self.t_buf = deque(maxlen=self.max_points)
        self.temp_buf = deque(maxlen=self.max_points)
        self.hum_buf = deque(maxlen=self.max_points)

        # ====== Layout ======
        root = QVBoxLayout()
        self.setLayout(root)
        top = QHBoxLayout()
        bottom = QHBoxLayout()
        root.addLayout(top)
        root.addLayout(bottom)
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

        conn_layout.addWidget(QLabel("Port:"))
        conn_layout.addWidget(self.port_combo, 1)
        conn_layout.addWidget(QLabel("Baud:"))
        conn_layout.addWidget(self.baud_combo)
        conn_layout.addWidget(self.refresh_btn)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addStretch(1)
        conn_layout.addWidget(self.status_dot)

        top.addWidget(conn_group)

        # --- Left: Plots + Slider ---
        left_col = QHBoxLayout()
        bottom.addLayout(left_col, 3)

        # Plots column
        plots_col = QVBoxLayout()
        left_col.addLayout(plots_col, 8)

        # 4 vertically stacked plot widgets
        self.plot_widgets = []
        for i in range(4):
            match i:
                case 0:
                    pw = pg.PlotWidget(title="Temperature")
                case 1:
                    pw = pg.PlotWidget(title="Humidity")
                case 2:
                    pw = pg.PlotWidget(title="Pressure")
                case 3:
                    pw = pg.PlotWidget(title="Acceleration")
            pw.showGrid(x=True, y=True)
            pw.setMinimumHeight(120)
            pw.setMaximumWidth(500)
            plots_col.addWidget(pw, 1)
            self.plot_widgets.append(pw)

        # Example: assign curves for first two plots
        self.temp_curve = self.plot_widgets[0].plot([], [], pen=pg.mkPen(width=2), name="Temp (°C)")
        self.hum_curve = self.plot_widgets[1].plot([], [], pen=pg.mkPen(width=2), name="Humidity (%)")

        # Altitude
        self.altitude_bar = AltitudeBar(min_alt=0, max_alt=1000)
        left_col.addWidget(self.altitude_bar, 1)

        # --- Left: 3 Boxes (2 up, 1 down) ---
        boxes_col = QVBoxLayout()
        bottom.addLayout(boxes_col, 2)

        # Top row
        top_row = QHBoxLayout()
        boxes_col.addLayout(top_row, 1)

        # Parachute button
        img_btn_group = QGroupBox("Image Button")
        img_btn_layout = QVBoxLayout()
        img_btn_group.setLayout(img_btn_layout)
        self.img_btn = QPushButton()
        self.img_btn.setIcon(QIcon("your_image.png"))  # Replace with your image path
        self.img_btn.setIconSize(QPixmap("your_image.png").size())
        img_btn_layout.addWidget(self.img_btn)
        top_row.addWidget(img_btn_group, 1)

        # Map GPS
        map_group = QGroupBox("Map")
        map_layout = QVBoxLayout()
        map_group.setLayout(map_layout)
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl("https://www.google.com/maps"))
        map_layout.addWidget(self.web_view)
        top_row.addWidget(map_group, 2)

        # Bottom: Gyro
        bottom_group = QGroupBox("Images")
        bottom_layout = QHBoxLayout()
        bottom_group.setLayout(bottom_layout)
        self.img1 = QLabel()
        self.img2 = QLabel()
        self.img1.setPixmap(QPixmap("rocket.png").scaled(180, 120, Qt.KeepAspectRatio))  # Replace with your image path
        self.img2.setPixmap(QPixmap("rocket.png").scaled(180, 120, Qt.KeepAspectRatio))  # Replace with your image path
        bottom_layout.addWidget(self.img1)
        bottom_layout.addWidget(self.img2)
        boxes_col.addWidget(bottom_group, 1)

        # Timer for plot updates (if needed)
        self.ui_timer = QTimer()
        self.ui_timer.timeout.connect(self.refresh_plots)
        self.ui_timer.start(80)


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

class AltitudeBar(QWidget):
    def __init__(self, min_alt=0, max_alt=1000, parent=None):
        super().__init__(parent)
        self.min_alt = min_alt
        self.max_alt = max_alt
        self.altitude = 300
        self.rocket_img = QPixmap("rocket.png")  # Use your image
        self.setMinimumWidth(100)  # Make a bit wider for scale
        self.setMinimumHeight(300)

    def set_altitude(self, value):
        self.altitude = max(self.min_alt, min(self.max_alt, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        w = self.width()
        h = self.height()
        margin = 20

        # Draw background bar
        bar_rect = QRect(w//2 - 20, margin, 20, h - 2*margin)
        painter.setBrush(QColor(220, 220, 220))
        painter.setPen(Qt.NoPen)
        painter.drawRect(bar_rect)

        # Draw filled progress (blue)
        frac = (self.altitude - self.min_alt) / (self.max_alt - self.min_alt)
        fill_height = int(frac * (h - 2*margin))
        fill_rect = QRect(bar_rect.left(), bar_rect.bottom() - fill_height, bar_rect.width(), fill_height)
        painter.setBrush(QColor("blue"))
        painter.drawRect(fill_rect)

        # Draw rocket image at correct height
        rocket_h = 180
        rocket_w = 100
        bar_center_x = bar_rect.left() + bar_rect.width() // 2
        x = bar_center_x - rocket_w // 2
        y = bar_rect.bottom() - fill_height - rocket_h // 2
        img = self.rocket_img.scaled(rocket_w, rocket_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        painter.drawPixmap(x, y, img)

        # --- Draw scale on the right ---
        num_ticks = 5  # Number of major ticks
        tick_length = 12
        label_offset = 8
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(Qt.black)

        for i in range(num_ticks + 1):
            frac_tick = i / num_ticks
            y_tick = margin + (h - 2*margin) - int(frac_tick * (h - 2*margin))
            alt_value = int(self.min_alt + frac_tick * (self.max_alt - self.min_alt))
            # Draw tick
            painter.drawLine(bar_rect.right() + 2, y_tick, bar_rect.right() + 2 + tick_length, y_tick)
            # Draw label
            painter.drawText(bar_rect.right() + 2 + tick_length + label_offset, y_tick + 4, f"{alt_value}")
# To update altitude:
# self.altitude_bar.set_altitude(current_altitude)


def main():
    app = QApplication(sys.argv)
    # Better looking antialiasing for pyqtgraph
    pg.setConfigOptions(antialias=True)
    w = ESP32Dashboard()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
