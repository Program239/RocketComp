
ESP32 Modern Dashboard (PyQt5 + PyQtGraph)
=========================================

1) Install Python 3.10+ and pip.

2) In this folder, install deps:
   pip install -r requirements.txt

3) Run the dashboard for development:
   python dashboard.py

4) Build a standalone executable (Windows):
   - Double-click build_windows.bat
   (macOS/Linux: run build_mac_linux.sh)

5) Connect the ESP32 by USB, pick the COM port, click Connect.

6) Click "Start Polling" to have the app send READ
 at your chosen interval.
   The ESP32 should respond with something like:
     TEMP:27.53,HUM:63.1
   (CSV or JSON also works; see esp32_firmware_example.ino)

Tips:
- If you don't see your port, click Refresh. On macOS the device is like /dev/tty.usbserial-XXXX,
  on Linux /dev/ttyUSB0 or /dev/ttyACM0, on Windows COM3, COM4, etc.
- If packaging fails, try: pip install --upgrade pip setuptools wheel pyinstaller
- For CH340/CP210x USB chips, you may need drivers on Windows.
- You can customize the protocol in handle_line() and on the ESP32 side.

Happy hacking!
