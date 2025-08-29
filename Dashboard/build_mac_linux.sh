
#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements.txt
python3 -m pip install pyinstaller
python3 -m PyInstaller --noconfirm --onefile --windowed --name ESP32_Dashboard dashboard.py
echo "Build complete. See dist/ESP32_Dashboard"
