from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

from wallcal import __version__

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
ICO = ASSETS / "icon.ico"
NAME = f"WallCal-{__version__}"


def ensure_ico() -> Path:
    ASSETS.mkdir(parents=True, exist_ok=True)
    png = ASSETS / "icon.png"
    if not png.exists():
        raise SystemExit("缺少 assets/icon.png")
    image = Image.open(png).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    image.save(ICO, format="ICO", sizes=sizes)
    return ICO


def main() -> None:
    ensure_ico()
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        NAME,
        "--icon",
        str(ICO),
        "--add-data",
        f"{ASSETS / 'icon.png'};assets",
        "--collect-all",
        "customtkinter",
        "--hidden-import",
        "PIL._tkinter_finder",
        str(ROOT / "main.py"),
    ]
    print(" ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    print(f"ok: {dist / (NAME + '.exe')}")


if __name__ == "__main__":
    main()
