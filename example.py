import sys
import random
import serial
import pyqtgraph as pg
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QTableWidget, QTableWidgetItem
)
from PyQt5.QtCore import Qt, QTimer


class ESP32Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ESP32 Modern Dashboard")
        self.resize(900, 600)

        main_layout = QHBoxLayout()
        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()
        main_layout.addLayout(left_panel, 2)
        main_layout.addLayout(right_panel, 1)

        # === Graph (Real-time Line) ===
        self.plot_widget = pg.PlotWidget(title="Sensor Data")
        self.plot_data = []
        self.plot_curve = self.plot_widget.plot(pen='y')
        left_panel.addWidget(self.plot_widget)

        # === Scatter Plot ===
        self.scatter_plot = pg.PlotWidget(title="Scatter Plot Example")
        self.scatter_data = pg.ScatterPlotItem()
        self.scatter_plot.addItem(self.scatter_data)
        left_panel.addWidget(self.scatter_plot)

        # === Bar Chart (using plot with stepMode) ===
        self.bar_chart = pg.PlotWidget(title="Bar Chart Example")
        self.bar_x = list(range(5))
        self.bar_y = [0, 0, 0, 0, 0]
        self.bar_item = pg.BarGraphItem(x=self.bar_x, height=self.bar_y, width=0.6, brush='r')
        self.bar_chart.addItem(self.bar_item)
        left_panel.addWidget(self.bar_chart)

        # === Buttons ===
        self.send_button = QPushButton("Send Command")
        self.send_button.clicked.connect(self.send_command)
        right_panel.addWidget(self.send_button)

        # === Slider ===
        self.slider_label = QLabel("Slider Value: 0")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.valueChanged.connect(self.update_slider)
        right_panel.addWidget(self.slider_label)
        right_panel.addWidget(self.slider)

        # === Table ===
        self.table = QTableWidget(3, 2)
        self.table.setHorizontalHeaderLabels(["Key", "Value"])
        self.table.setItem(0, 0, QTableWidgetItem("Temp"))
        self.table.setItem(1, 0, QTableWidgetItem("Humidity"))
        self.table.setItem(2, 0, QTableWidgetItem("Status"))
        right_panel.addWidget(self.table)

        # === Status Indicator ===
        self.status_label = QLabel("● Disconnected")
        self.status_label.setStyleSheet("color: red; font-size: 16px;")
        right_panel.addWidget(self.status_label)

        # Set layout
        self.setLayout(main_layout)

        # Timer to simulate data update
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(500)

        # (Optional) Serial connection to ESP32
        # self.serial_port = serial.Serial("COM3", 115200, timeout=1)

    def update_data(self):
        # Random test data (replace with ESP32 data)
        new_val = random.randint(0, 100)
        self.plot_data.append(new_val)
        if len(self.plot_data) > 50:
            self.plot_data.pop(0)
        self.plot_curve.setData(self.plot_data)

        # Scatter plot points
        self.scatter_data.setData([random.randint(0, 10) for _ in range(5)],
                                  [random.randint(0, 10) for _ in range(5)])

        # Update bar chart
        self.bar_y = [random.randint(0, 20) for _ in range(5)]
        self.bar_chart.clear()
        self.bar_item = pg.BarGraphItem(x=self.bar_x, height=self.bar_y, width=0.6, brush='g')
        self.bar_chart.addItem(self.bar_item)

        # Update table values
        self.table.setItem(0, 1, QTableWidgetItem(f"{new_val} °C"))
        self.table.setItem(1, 1, QTableWidgetItem(f"{50+random.randint(-10,10)} %"))
        self.table.setItem(2, 1, QTableWidgetItem("OK"))

        # Status light (simulate connected/disconnected)
        if random.random() > 0.2:
            self.status_label.setText("● Connected")
            self.status_label.setStyleSheet("color: green; font-size: 16px;")
        else:
            self.status_label.setText("● Disconnected")
            self.status_label.setStyleSheet("color: red; font-size: 16px;")

    def send_command(self):
        print("Command sent to ESP32")
        # Example: self.serial_port.write(b"LED_ON\n")

    def update_slider(self, value):
        self.slider_label.setText(f"Slider Value: {value}")
        # Example: self.serial_port.write(f"PWM:{value}\n".encode())


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ESP32Dashboard()
    window.show()
    sys.exit(app.exec_())
