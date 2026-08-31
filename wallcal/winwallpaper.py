from __future__ import annotations

import ctypes
import winreg
from pathlib import Path


SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def screen_size() -> tuple[int, int]:
    user32 = ctypes.windll.user32
    width = int(user32.GetSystemMetrics(SM_CXSCREEN) or 1920)
    height = int(user32.GetSystemMetrics(SM_CYSCREEN) or 1080)
    return max(width, 1280), max(height, 720)


_HELD_WALLPAPER_PATH = ""


def set_wallpaper(image_path: Path) -> None:
    global _HELD_WALLPAPER_PATH
    path = str(Path(image_path).resolve())
    _HELD_WALLPAPER_PATH = path
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Control Panel\Desktop",
        0,
        winreg.KEY_SET_VALUE,
    )
    try:
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10")
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
        winreg.SetValueEx(key, "Wallpaper", 0, winreg.REG_SZ, path)
    finally:
        winreg.CloseKey(key)
    ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER,
        0,
        _HELD_WALLPAPER_PATH,
        SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
    )
    _clear_theme_cache()


def _clear_theme_cache() -> None:
    import os
    from pathlib import Path

    themes = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Themes"
    for name in ("TranscodedWallpaper", "TranscodedWallpaper.jpg"):
        target = themes / name
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
