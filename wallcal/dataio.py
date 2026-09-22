from __future__ import annotations

import base64
import csv
import io
import json
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .memos import is_done, memos_on
from .paths import DATA_DIR
from .storage import DEFAULT_STATE, _normalize_memo
from .timeinput import parse_time


def import_background(source: Path) -> str:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((7680, 4320))
        import uuid
        target = DATA_DIR / f"background_{uuid.uuid4().hex}.jpg"
        tmp = target.with_suffix(".tmp")
        image.save(tmp, "JPEG", quality=95)
        tmp.replace(target)
    return str(target)


def write_backup(state: dict[str, Any], path: Path) -> None:
    data = {"app": "wallcal", "backup_version": 1,
            "created_at": datetime.now().isoformat(), "state": deepcopy(state)}
    background = state.get("settings", {}).get("background")
    if background and Path(background).is_file():
        data["background_base64"] = base64.b64encode(Path(background).read_bytes()).decode("ascii")
    data["state"]["settings"].pop("background", None)
    data["theme_backgrounds"] = {}
    for key, profile in data["state"]["settings"].get("custom_themes", {}).items():
        source = profile.pop("background", "")
        if source and Path(source).is_file():
            data["theme_backgrounds"][key] = base64.b64encode(Path(source).read_bytes()).decode("ascii")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_backup(path: Path) -> tuple[dict[str, Any], dict[str, bytes]]:
    if path.stat().st_size > 80 * 1024 * 1024:
        raise ValueError("备份文件过大")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("app") != "wallcal" or data.get("backup_version") != 1:
        raise ValueError("请选择壁历导出的 JSON 备份")
    raw = data.get("state")
    if not isinstance(raw, dict) or not isinstance(raw.get("memos"), list) or not isinstance(raw.get("settings"), dict):
        raise ValueError("备份数据结构不完整")
    state = deepcopy(DEFAULT_STATE)
    state["settings"].update(raw["settings"])
    if state["settings"].get("layout") in {"three_quarters", "four_fifths", "right", "compact"}:
        state["settings"]["layout"] = "auto"
    state["settings"]["background"] = ""
    if state["settings"].get("theme") in {"paper", "celadon"}:
        state["settings"]["theme"] = "eye"
    from .themes import THEMES
    profiles = state["settings"].get("custom_themes", {})
    if not isinstance(profiles, dict):
        raise ValueError("自定义主题无效")
    from .themes import _rgb
    for key, profile in profiles.items():
        if not isinstance(key,str) or not key.startswith("custom_") or not isinstance(profile,dict):
            raise ValueError("自定义主题无效")
        if not isinstance(profile.get("name"),str) or profile.get("mode") not in {"light","dark"}:
            raise ValueError("主题名称或明暗模式无效")
        _rgb(profile.get("surface")); _rgb(profile.get("accent"))
        profile["background"] = ""
    if state["settings"].get("theme") not in THEMES and state["settings"].get("theme") not in profiles:
        raise ValueError("备份主题无效")
    for key in ("high_contrast", "show_holidays"):
        if not isinstance(state["settings"].get(key), bool):
            raise ValueError(f"显示设置无效：{key}")
    seen_ids = set()
    for memo in raw["memos"]:
        if not isinstance(memo, dict) or not isinstance(memo.get("title"), str) or not memo["title"].strip():
            raise ValueError("备忘标题无效")
        date.fromisoformat(memo.get("date", ""))
        if memo.get("repeat", "none") not in {"none", "daily", "weekly", "monthly"}:
            raise ValueError("重复规则无效")
        if not isinstance(memo.get("done_dates", []), list):
            raise ValueError("完成日期无效")
        for value in memo.get("done_dates", []):
            date.fromisoformat(value)
        value = parse_time(memo.get("time", ""))
        if value is None:
            raise ValueError("备忘时间无效")
        normalized = _normalize_memo(memo)
        normalized["time"] = value
        if normalized["id"] in seen_ids:
            raise ValueError("备份中存在重复的事项 ID")
        seen_ids.add(normalized["id"])
        state["memos"].append(normalized)
    personal = raw.get("personal_holidays", [])
    if not isinstance(personal, list):
        raise ValueError("假期记录无效")
    for item in personal:
        if not isinstance(item, dict) or item.get("kind") not in {"leave", "rest", "work", "off"}:
            raise ValueError("假期类型无效")
        date.fromisoformat(item.get("date", ""))
        if not isinstance(item.get("name"), str):
            raise ValueError("假期名称无效")
    state["personal_holidays"] = personal
    deleted = raw.get("deleted_ids", [])
    if not isinstance(deleted, list) or not all(isinstance(x, str) for x in deleted):
        raise ValueError("删除记录无效")
    state["deleted_ids"] = deleted
    for key, choices in {"layout": {"auto", "right", "full", "compact", "four_fifths"}, "font_scale": {1.0, 1.2, 1.4}, "ui_scale": {1.0, 1.1, 1.2}}.items():
        if state["settings"].get(key) not in choices:
            raise ValueError(f"显示设置无效：{key}")
    media = {}
    encoded_images = dict(data.get("theme_backgrounds") or {})
    if any(key not in profiles for key in encoded_images):
        raise ValueError("备份主题图片无效")
    if data.get("background_base64"):
        encoded_images["active"] = data["background_base64"]
    for key, encoded in encoded_images.items():
        image_data = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(image_data)) as image:
            image.verify()
        media[key] = image_data
    return state, media


def export_csv(state: dict[str, Any], path: Path, start: date, end: date) -> int:
    if end < start or (end - start).days > 3660:
        raise ValueError("请选择不超过十年的有效日期范围")
    def safe(value: Any) -> str:
        text = str(value or "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text
    count = 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["日期", "时间", "事项", "分类", "重复", "状态", "备注", "事项ID"])
        day = start
        while day <= end:
            for memo in memos_on(state["memos"], day):
                writer.writerow([day.isoformat(), memo.get("time", ""), safe(memo["title"]),
                    {"life": "生活", "work": "工作", "important": "重要"}.get(memo.get("tag"), "生活"),
                    {"none": "仅一次", "daily": "每天", "weekly": "每周", "monthly": "每月"}.get(memo.get("repeat"), "仅一次"),
                    "已完成" if is_done(memo, day) else "未完成", safe(memo.get("note")), safe(memo.get("id"))])
                count += 1
            day += timedelta(days=1)
    tmp.replace(path)
    return count
