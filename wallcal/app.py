from __future__ import annotations

import sys
import time
import traceback

from . import ipc
from .icon import ensure_icon
from .paths import LOG_PATH
from .ui import WallCalWindow
from .winwallpaper import enable_dpi_awareness


def _log(message: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message.rstrip() + "\n")
    except OSError:
        pass


def run() -> None:
    enable_dpi_awareness()
    ensure_icon()
    if ipc.ask_running_instance_to_show():
        _log("handed off to running instance")
        sys.exit(0)

    _log("starting window")
    try:
        window = WallCalWindow()
    except Exception:
        _log(traceback.format_exc())
        raise

    window.tray = None
    ipc.listen_for_show(window.request_show)

    window.after(150, window.show_window)
    _log("entering mainloop")
    window.mainloop()
    _log("mainloop ended")
