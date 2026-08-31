from __future__ import annotations

import os
import sys
from pathlib import Path


def install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return Path(meipass)
    return install_dir()


def data_dir() -> Path:
    root = Path(os.environ.get("APPDATA", install_dir())) / "WallCal"
    root.mkdir(parents=True, exist_ok=True)
    return root


APP_ROOT = install_dir()
RESOURCE_ROOT = resource_root()
DATA_DIR = data_dir()
STORE_PATH = DATA_DIR / "data.json"
WALLPAPER_PATH = DATA_DIR / "wallpaper.jpg"
LOG_PATH = DATA_DIR / "app.log"
ICON_PATH = RESOURCE_ROOT / "assets" / "icon.png"
ASSETS_DIR = RESOURCE_ROOT / "assets"
