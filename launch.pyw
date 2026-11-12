"""Windowless desktop entry point; keep startup errors visible and logged."""
import ctypes
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if os.name == 'nt':
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('MandarinStudio.Desktop')

try:
    # pythonw has no console streams. Preserve diagnostics for background failures.
    log = open(ROOT / 'startup.log', 'a', encoding='utf-8', buffering=1)
    sys.stdout = log
    sys.stderr = log
    from app import Studio
    Studio().mainloop()
except Exception:
    traceback.print_exc()
    ctypes.windll.user32.MessageBoxW(
        0, f'Không mở được Mandarin Studio. Xem chi tiết tại:\n{ROOT / "startup.log"}',
        'Mandarin Studio', 16)
