from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any


def parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def occurs_on(memo: dict[str, Any], day: date) -> bool:
    start = parse_date(memo["date"])
    if day < start:
        return False
    repeat = memo.get("repeat") or "none"
    if repeat == "daily":
        return True
    if repeat == "weekly":
        return day.weekday() == start.weekday()
    if repeat == "monthly":
        last = calendar.monthrange(day.year, day.month)[1]
        target = min(start.day, last)
        return day.day == target
    return day == start


def is_done(memo: dict[str, Any], day: date) -> bool:
    return day.isoformat() in (memo.get("done_dates") or [])


def toggle_done(memo: dict[str, Any], day: date) -> None:
    key = day.isoformat()
    done = list(memo.get("done_dates") or [])
    if key in done:
        done.remove(key)
    else:
        done.append(key)
    memo["done_dates"] = sorted(set(done))


def memos_on(memos: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    items = [m for m in memos if occurs_on(m, day)]
    return sorted(items, key=_sort_key(day))


def pending_on(memos: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    return [m for m in memos_on(memos, day) if not is_done(m, day)]


def events_on(
    memos: list[dict[str, Any]],
    day: date,
    *,
    skip_daily: bool = False,
    include_done: bool = True,
) -> list[dict[str, Any]]:
    items = memos_on(memos, day)
    if skip_daily:
        items = [m for m in items if (m.get("repeat") or "none") != "daily"]
    if not include_done:
        items = [m for m in items if not is_done(m, day)]
    return items


def daily_habits(memos: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    items = []
    seen: set[str] = set()
    for memo in memos_on(memos, day):
        if (memo.get("repeat") or "none") != "daily":
            continue
        if memo["id"] in seen:
            continue
        seen.add(memo["id"])
        items.append(memo)
    return items


def month_stats(memos: list[dict[str, Any]], year: int, month: int) -> tuple[int, int]:
    pending = 0
    done = 0
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    day = start
    while day < end:
        for memo in events_on(memos, day, skip_daily=True, include_done=True):
            if is_done(memo, day):
                done += 1
            else:
                pending += 1
        day += timedelta(days=1)
    return pending, done


def days_with_memos(memos: list[dict[str, Any]], year: int, month: int) -> dict[int, list[str]]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    marks: dict[int, list[str]] = {}
    day = start
    while day < end:
        tags: list[str] = []
        for memo in memos:
            if occurs_on(memo, day) and not is_done(memo, day):
                tag = memo.get("tag") or "life"
                if tag not in tags:
                    tags.append(tag)
        if tags:
            marks[day.day] = tags
        day += timedelta(days=1)
    return marks


def upcoming(
    memos: list[dict[str, Any]],
    today: date,
    days: int = 14,
    limit: int = 8,
) -> list[tuple[date, dict[str, Any]]]:
    found: list[tuple[date, dict[str, Any]]] = []
    for offset in range(1, days + 1):
        day = today + timedelta(days=offset)
        for memo in memos_on(memos, day):
            if memo.get("repeat") == "daily":
                continue
            if is_done(memo, day):
                continue
            found.append((day, memo))
            if len(found) >= limit:
                return found
    return found


def count_pending_month(memos: list[dict[str, Any]], year: int, month: int) -> int:
    marks = days_with_memos(memos, year, month)
    total = 0
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    day = start
    while day < end:
        total += len(pending_on(memos, day))
        day += timedelta(days=1)
    return total


def _sort_key(day: date):
    def key(memo: dict[str, Any]):
        done = 1 if is_done(memo, day) else 0
        time = memo.get("time") or "99:99"
        return (done, time, memo.get("created_at") or "")

    return key
