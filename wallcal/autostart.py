from __future__ import annotations

import sys
from pathlib import Path

from .paths import APP_ROOT


def startup_bat() -> Path:
    appdata = Path.home() / "AppData" / "Roaming"
    return appdata / r"Microsoft\Windows\Start Menu\Programs\Startup" / "WallCal.bat"


def is_enabled() -> bool:
    return startup_bat().exists()


def set_enabled(enabled: bool) -> None:
    path = startup_bat()
    if not enabled:
        if path.exists():
            path.unlink()
        return
    python = Path(sys.executable)
    if getattr(sys, "frozen", False):
        command = f'start "" "{python}"'
    else:
        pythonw = python.with_name("pythonw.exe")
        exe = pythonw if pythonw.exists() else python
        main = APP_ROOT / "main.py"
        command = f'start "" "{exe}" "{main}"'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"@echo off\r\n{command}\r\n", encoding="ascii")
