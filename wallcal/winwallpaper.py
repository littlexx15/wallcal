from __future__ import annotations
import ctypes
import json
import shutil
import winreg
from ctypes import wintypes
from pathlib import Path
from .paths import DATA_DIR

DESKTOP_KEY = r"Control Panel\Desktop"
ORIGINAL = DATA_DIR / "original_wallpaper.json"

def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()

def screen_size() -> tuple[int, int]:
    return (ctypes.windll.user32.GetSystemMetrics(0) or 1920,
            ctypes.windll.user32.GetSystemMetrics(1) or 1080)

def work_area() -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    w, h = screen_size()
    return 0, 0, w, h - 48

def _desktop_values() -> dict[str, str]:
    values = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DESKTOP_KEY) as key:
        for name in ("Wallpaper", "WallpaperStyle", "TileWallpaper"):
            try:
                values[name] = str(winreg.QueryValueEx(key, name)[0])
            except FileNotFoundError:
                values[name] = ""
    return values

def capture_original() -> None:
    if ORIGINAL.exists():
        return
    values = _desktop_values()
    source = Path(values["Wallpaper"]) if values["Wallpaper"] else None
    if source and source.parent.resolve() == DATA_DIR.resolve() and source.name.startswith(("desktop_", "wallpaper")):
        return
    if source and not source.is_file():
        raise FileNotFoundError("原壁纸无法读取，已取消更换。请先在显示设置中选择原壁纸备份。")
    if source and source.is_file():
        backup = DATA_DIR / ("original_background" + source.suffix)
        shutil.copy2(source, backup)
        values["backup"] = str(backup)
    temporary = ORIGINAL.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    temporary.replace(ORIGINAL)

def choose_original(source: Path) -> None:
    """Explicit recovery image for installations predating automatic backup."""
    import uuid
    from PIL import Image, ImageOps
    backup = DATA_DIR / f"original_background_{uuid.uuid4().hex}.png"
    with Image.open(source) as image:
        ImageOps.exif_transpose(image).convert("RGB").save(backup, "PNG")
    values = {"Wallpaper": str(source), "backup": str(backup),
              "WallpaperStyle": "10", "TileWallpaper": "0"}
    temporary = ORIGINAL.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    temporary.replace(ORIGINAL)


def _apply(path: str, style: str, tile: str) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, DESKTOP_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, style)
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, tile)
    if not ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3):
        raise OSError("Windows 未能应用壁纸，请重试")
    # Windows owns its theme cache. Never delete it after setting a wallpaper.

def set_wallpaper(image_path: Path, monitor_id: str | None = None) -> None:
    path = Path(image_path).resolve()
    from PIL import Image
    with Image.open(path) as image:
        image.verify()
    if monitor_id is not None:
        from .monitors import apply
        apply(path, monitor_id)
        return
    capture_original()
    _apply(str(path), "10", "0")

def restore_original(monitor_id: str | None = None) -> None:
    if monitor_id is not None:
        from .monitors import restore
        if not restore():
            raise OSError("此屏幕尚无本版应用记录，请在 Windows 个性化中选择壁纸，或先应用日历后恢复。")
        return
    if not ORIGINAL.exists():
        raise FileNotFoundError("未找到原壁纸备份（旧版无法补回原图）。已停止更新，请在 Windows 个性化设置中选择背景。")
    values = json.loads(ORIGINAL.read_text(encoding="utf-8"))
    path = values.get("backup") or values.get("Wallpaper", "")
    if path and not Path(path).is_file():
        raise FileNotFoundError("原壁纸文件已不存在，请在 Windows 个性化设置中选择背景。")
    _apply(path, values.get("WallpaperStyle", "10"), values.get("TileWallpaper", "0"))
