@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -c "import PIL, imageio_ffmpeg, dotenv" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto fail
)
start "" ".venv\Scripts\pythonw.exe" "%~dp0launch.pyw"
exit /b 0
:fail
echo Khong khoi dong duoc. Hay chup lai thong bao loi nay.
pause
