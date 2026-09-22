from __future__ import annotations
import os
import sys
import winreg
from pathlib import Path
from .paths import APP_ROOT

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def startup_bat() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Microsoft/Windows/Start Menu/Programs/Startup/WallCal.bat"

def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return bool(winreg.QueryValueEx(key, "WallCal")[0])
    except FileNotFoundError:
        return startup_bat().exists()

def set_enabled(enabled: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            exe = Path(sys.executable)
            if getattr(sys, "frozen", False):
                command = f'"{exe}"'
            else:
                pythonw = exe.with_name("pythonw.exe")
                command = f'"{pythonw if pythonw.exists() else exe}" "{APP_ROOT / "main.py"}"'
            winreg.SetValueEx(key, "WallCal", 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, "WallCal")
            except FileNotFoundError:
                pass
    startup_bat().unlink(missing_ok=True)
