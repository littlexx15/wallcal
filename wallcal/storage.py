from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .paths import STORE_PATH

_lock = threading.Lock()

DEFAULT_STATE: dict[str, Any] = {
    "settings": {
        "theme": "eye",
        "autostart": False,
        "first_run": True,
    },
    "memos": [],
}


def _blank() -> dict[str, Any]:
    return deepcopy(DEFAULT_STATE)


def load() -> dict[str, Any]:
    with _lock:
        if not STORE_PATH.exists():
            state = _blank()
            _write(STORE_PATH, state)
            return state
        try:
            raw = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = _blank()
            _write(STORE_PATH, state)
            return state
        state = _blank()
        state["settings"].update(raw.get("settings") or {})
        memos = raw.get("memos") or []
        state["memos"] = [_normalize_memo(m) for m in memos if isinstance(m, dict)]
        return state


def save(state: dict[str, Any]) -> None:
    with _lock:
        _write(STORE_PATH, state)


def _write(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def _normalize_memo(memo: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(memo.get("id") or uuid.uuid4().hex[:10]),
        "title": str(memo.get("title") or "").strip(),
        "note": str(memo.get("note") or "").strip(),
        "date": str(memo.get("date") or date.today().isoformat()),
        "time": str(memo.get("time") or "").strip(),
        "tag": str(memo.get("tag") or "life"),
        "repeat": str(memo.get("repeat") or "none"),
        "done_dates": [str(x) for x in (memo.get("done_dates") or [])],
        "created_at": str(memo.get("created_at") or datetime.now().isoformat(timespec="seconds")),
    }


def new_memo(
    *,
    title: str,
    day: date,
    time: str = "",
    tag: str = "life",
    repeat: str = "none",
    note: str = "",
) -> dict[str, Any]:
    return _normalize_memo(
        {
            "id": uuid.uuid4().hex[:10],
            "title": title,
            "note": note,
            "date": day.isoformat(),
            "time": time,
            "tag": tag,
            "repeat": repeat,
            "done_dates": [],
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )


def ensure_welcome(state: dict[str, Any]) -> bool:
    if not state["settings"].get("first_run"):
        return False
    today = date.today()
    state["memos"].append(
        new_memo(
            title="欢迎使用壁历，把今天要做的事写在这里",
            day=today,
            tag="life",
        )
    )
    state["settings"]["first_run"] = False
    save(state)
    return True
