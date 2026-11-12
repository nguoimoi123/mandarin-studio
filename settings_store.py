"""Local configuration persistence; never log values."""
from pathlib import Path
import os
import tempfile
from dotenv import dotenv_values, load_dotenv, set_key


def load_settings(path):
    load_dotenv(path, override=True, interpolate=False)
    return {k: v for k, v in dotenv_values(path, interpolate=False).items() if v is not None}


def save_settings(path, values):
    path = Path(path)
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    fd, name = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as output:
            output.write(existing)
        for key, value in values.items():
            set_key(temporary, key, str(value), quote_mode='always')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
