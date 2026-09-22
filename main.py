from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def preview() -> None:
    from wallcal.storage import new_memo
    from wallcal.storage import load
    from wallcal.wallpaper import render_wallpaper
    from wallcal.winwallpaper import enable_dpi_awareness, screen_size

    enable_dpi_awareness()
    state = load()
    today = datetime.now().date()
    if not state["memos"]:
        state["memos"] = [
            new_memo(title="把今天最重要的一件事写进来", day=today, time="09:00", tag="important"),
            new_memo(title="午后散步十分钟", day=today, time="14:30", tag="life"),
            new_memo(title="整理本周工作", day=today, time="16:00", tag="work"),
        ]
    path = render_wallpaper(state, apply="--apply" in sys.argv)
    print(path)
    print("screen", screen_size())


def _crash(exc: BaseException) -> None:
    from wallcal.paths import LOG_PATH

    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(text, encoding="utf-8")
    except OSError:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "壁历窗口没能打开。\n请再双击桌面上的「壁历」。\n\n" + text[-800:],
            "壁历",
            0x10,
        )
    except Exception:
        pass


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview()
    else:
        try:
            from wallcal.app import run

            run()
        except SystemExit:
            raise
        except BaseException as exc:
            _crash(exc)
            raise
