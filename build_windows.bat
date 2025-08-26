
@echo off
REM Build a single-file executable (Windows)
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name ESP32_Dashboard dashboard.py
echo.
echo Build complete. Find the EXE in the "dist" folder.
pause
