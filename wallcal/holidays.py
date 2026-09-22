from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterable


@dataclass(frozen=True)
class DayMark:
    kind: str
    name: str
    official: bool


def _span(year: int, month: int, day: int, end_month: int, end_day: int) -> list[date]:
    start = date(year, month, day)
    end = date(year, end_month, end_day)
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _d(year: int, month: int, day: int) -> date:
    return date(year, month, day)


def _year_pack(
    *,
    blocks: list[tuple[str, list[date], list[date]]],
) -> dict[str, Any]:
    off: dict[str, str] = {}
    work: dict[str, str] = {}
    groups: list[dict[str, Any]] = []
    for name, rest_days, work_days in blocks:
        for day in rest_days:
            off[day.isoformat()] = name
        for day in work_days:
            work[day.isoformat()] = f"{name}调休"
        groups.append(
            {
                "name": name,
                "off": [d.isoformat() for d in rest_days],
                "work": [d.isoformat() for d in work_days],
            }
        )
    return {"off": off, "work": work, "groups": groups}


# 来源：国务院办公厅通知（中国政府网）
# 2025：国办发明电〔2024〕12号
# 2026：国办发明电〔2025〕7号
OFFICIAL: dict[int, dict[str, Any]] = {
    2025: _year_pack(
        blocks=[
            ("元旦", [_d(2025, 1, 1)], []),
            (
                "春节",
                _span(2025, 1, 28, 2, 4),
                [_d(2025, 1, 26), _d(2025, 2, 8)],
            ),
            ("清明节", _span(2025, 4, 4, 4, 6), []),
            ("劳动节", _span(2025, 5, 1, 5, 5), [_d(2025, 4, 27)]),
            ("端午节", _span(2025, 5, 31, 6, 2), []),
            (
                "国庆节、中秋节",
                _span(2025, 10, 1, 10, 8),
                [_d(2025, 9, 28), _d(2025, 10, 11)],
            ),
        ]
    ),
    2026: _year_pack(
        blocks=[
            ("元旦", _span(2026, 1, 1, 1, 3), [_d(2026, 1, 4)]),
            (
                "春节",
                _span(2026, 2, 15, 2, 23),
                [_d(2026, 2, 14), _d(2026, 2, 28)],
            ),
            ("清明节", _span(2026, 4, 4, 4, 6), []),
            ("劳动节", _span(2026, 5, 1, 5, 5), [_d(2026, 5, 9)]),
            ("端午节", _span(2026, 6, 19, 6, 21), []),
            ("中秋节", _span(2026, 9, 25, 9, 27), []),
            (
                "国庆节",
                _span(2026, 10, 1, 10, 7),
                [_d(2026, 9, 20), _d(2026, 10, 10)],
            ),
        ]
    ),
}


def official_years() -> list[int]:
    return sorted(OFFICIAL)


def mark_on(day: date, personal: Iterable[dict[str, Any]] | None = None, *, include_official: bool = True) -> DayMark | None:
    key = day.isoformat()
    for item in personal or []:
        if str(item.get("date") or "")[:10] == key:
            kind = str(item.get("kind") or "leave")
            return DayMark(kind, str(item.get("name") or "休假"), False)
    pack = OFFICIAL.get(day.year) if include_official else None
    if pack:
        if key in pack["off"]:
            return DayMark("off", pack["off"][key], True)
        if key in pack["work"]:
            return DayMark("work", pack["work"][key], True)
    return None


def month_counts(
    year: int,
    month: int,
    personal: Iterable[dict[str, Any]] | None = None,
) -> tuple[int, int]:
    off = leave = 0
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    day = start
    while day < end:
        mark = mark_on(day, personal)
        if mark:
            if mark.kind in {"off", "rest"}:
                off += 1
            elif mark.kind == "leave":
                leave += 1
        day += timedelta(days=1)
    return off, leave


def next_rest_day(
    today: date,
    personal: Iterable[dict[str, Any]] | None = None,
    limit: int = 400,
) -> tuple[date, DayMark] | None:
    for offset in range(0, limit):
        day = today + timedelta(days=offset)
        mark = mark_on(day, personal)
        if mark and mark.kind in {"off", "leave", "rest"}:
            return day, mark
    return None


def year_groups(year: int) -> list[dict[str, Any]]:
    pack = OFFICIAL.get(year)
    if not pack:
        return []
    return list(pack["groups"])


def upsert_personal(
    personal: list[dict[str, Any]],
    day: date,
    *,
    kind: str,
    name: str,
) -> list[dict[str, Any]]:
    key = day.isoformat()
    kept = [item for item in personal if str(item.get("date") or "")[:10] != key]
    kept.append({"date": key, "kind": kind, "name": name})
    kept.sort(key=lambda item: str(item.get("date") or ""))
    return kept


def remove_personal(personal: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    key = day.isoformat()
    return [item for item in personal if str(item.get("date") or "")[:10] != key]
