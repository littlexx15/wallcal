from __future__ import annotations

import calendar
from datetime import date, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .fonts import font
from .memos import daily_habits, events_on, is_done, month_stats, pending_on
from .paths import DATA_DIR, WALLPAPER_PATH
from .themes import Theme, get_theme, tag_color
from .winwallpaper import screen_size, set_wallpaper

WEEK_HEADER = ["日", "一", "二", "三", "四", "五", "六"]
MONTHS = [
    "一月",
    "二月",
    "三月",
    "四月",
    "五月",
    "六月",
    "七月",
    "八月",
    "九月",
    "十月",
    "十一月",
    "十二月",
]
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


class Scale:
    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height
        self.k = min(width / 1920.0, height / 1080.0)

    def __call__(self, value: float) -> int:
        return int(round(value * self.k))


def greeting(now: datetime) -> str:
    hour = now.hour
    if 5 <= hour < 9:
        return "清晨好"
    if 9 <= hour < 12:
        return "上午好"
    if 12 <= hour < 14:
        return "中午好"
    if 14 <= hour < 18:
        return "下午好"
    if 18 <= hour < 23:
        return "晚上好"
    return "夜深了，早点休息"


def ellipsize(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> str:
    if not text:
        return ""
    if max_width <= 0:
        return ""
    if draw.textlength(text, font=fnt) <= max_width:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if draw.textlength(text[:mid] + ell, font=fnt) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo] + ell) if lo else ell


def put_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    fnt,
    fill,
    anchor: str = "lt",
) -> tuple[int, int]:
    draw.text(xy, text, font=fnt, fill=fill, anchor=anchor)
    bbox = draw.textbbox(xy, text, font=fnt, anchor=anchor)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def gradient_bg(size: tuple[int, int], c0: tuple[int, int, int], c1: tuple[int, int, int]) -> Image.Image:
    width, height = size
    top = Image.new("RGB", size, c0)
    bottom = Image.new("RGB", size, c1)
    mask = Image.linear_gradient("L").resize((1, height)).resize(size)
    return Image.composite(bottom, top, mask)


def apply_vignette(img: Image.Image) -> Image.Image:
    width, height = img.size
    rad = Image.radial_gradient("L").resize((int(width * 1.15), int(height * 1.25)))
    left = (rad.width - width) // 2
    top = (rad.height - height) // 2
    rad = rad.crop((left, top, left + width, top + height))
    edge = rad.point(lambda p: int(p * 0.28))
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 255))
    overlay.putalpha(edge)
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def rounded_card(
    img: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    width: int = 1,
) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    return Image.alpha_composite(img, overlay)


def mix(c0: tuple[int, int, int], c1: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(c0[0] + (c1[0] - c0[0]) * t),
        int(c0[1] + (c1[1] - c0[1]) * t),
        int(c0[2] + (c1[2] - c0[2]) * t),
    )


def with_alpha(color: tuple[int, int, int], alpha: int) -> tuple[int, int, int, int]:
    return (color[0], color[1], color[2], alpha)


def render_wallpaper(
    state: dict[str, Any],
    *,
    now: datetime | None = None,
    size: tuple[int, int] | None = None,
    dest: Path | None = None,
    apply: bool = False,
) -> Path:
    now = now or datetime.now()
    today = now.date()
    theme = get_theme(state.get("settings", {}).get("theme", "ink"))
    memos = state.get("memos") or []
    width, height = size or screen_size()
    s = Scale(width, height)

    img = gradient_bg((width, height), theme.bg0, theme.bg1).convert("RGBA")
    img = apply_vignette(img)

    margin = s(48)
    top = s(36)
    bottom = height - s(40)
    left = margin
    right = width - margin

    header_h = s(88)
    _draw_header(img, theme, s, now, today, memos, (left, top, right, top + header_h))

    cal_box = (left, top + header_h + s(12), right, bottom)
    img = rounded_card(img, cal_box, s(24), theme.card, theme.card_line, max(s(1), 1))
    _draw_month_grid(img, theme, s, memos, today, cal_box)

    draw = ImageDraw.Draw(img)
    put_text(
        draw,
        (width / 2, height - s(20)),
        "壁历  ·  整月日程都在格子里，改备忘会马上刷新到桌面",
        font(s(15)),
        theme.muted,
        anchor="mm",
    )

    rgb = img.convert("RGB")
    out = dest or _next_desktop_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    rgb.save(out, "JPEG", quality=95, optimize=True)
    try:
        rgb.save(WALLPAPER_PATH, "JPEG", quality=95, optimize=True)
    except OSError:
        pass
    if apply:
        set_wallpaper(out)
    return out


def _next_desktop_path() -> Path:
    import winreg

    first = DATA_DIR / "desktop_a.jpg"
    second = DATA_DIR / "desktop_b.jpg"
    current = ""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop")
        current, _ = winreg.QueryValueEx(key, "WallPaper")
        winreg.CloseKey(key)
    except OSError:
        current = ""
    marker = current.lower().replace("\\", "/")
    return second if "desktop_a.jpg" in marker else first


def _draw_header(
    img: Image.Image,
    theme: Theme,
    s: Scale,
    now: datetime,
    today: date,
    memos: list[dict[str, Any]],
    box: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    hi = f"{greeting(now)}  ·  {WEEKDAYS[today.weekday()]}"
    put_text(draw, (x0, y0 + s(2)), hi, font(s(18)), theme.muted)
    put_text(
        draw,
        (x0, y0 + s(28)),
        f"{today.year} 年 {MONTHS[today.month - 1]}",
        font(s(34), bold=True),
        theme.text,
    )

    pending, done = month_stats(memos, today.year, today.month)
    today_n = len(pending_on(memos, today))
    stats = f"今天 {today.day} 日 · {today_n} 件     本月待办 {pending}     已完成 {done}"
    put_text(draw, (x1, y0 + s(6)), stats, font(s(18)), theme.accent, anchor="rt")

    habits = daily_habits(memos, today)
    if habits:
        names = "、".join((m.get("title") or "") for m in habits[:4] if m.get("title"))
        put_text(
            draw,
            (x1, y0 + s(40)),
            f"每日  {names}",
            font(s(15)),
            theme.muted,
            anchor="rt",
        )


def _draw_month_grid(
    img: Image.Image,
    theme: Theme,
    s: Scale,
    memos: list[dict[str, Any]],
    today: date,
    box: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    pad = s(22)
    x = x0 + pad
    y = y0 + pad
    inner_w = x1 - x0 - pad * 2
    inner_h = y1 - y0 - pad * 2

    header_h = s(36)
    weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(today.year, today.month)
    row_count = len(weeks)
    cell_w = inner_w / 7
    cell_h = (inner_h - header_h) / row_count

    for i, name in enumerate(WEEK_HEADER):
        cx = x + cell_w * i + cell_w / 2
        color = theme.weekend if i in (0, 6) else theme.muted
        put_text(draw, (cx, y + s(4)), name, font(s(18), bold=True), color, anchor="mt")

    grid_top = y + header_h
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            cx = x + cell_w * c
            cy = grid_top + cell_h * r
            _draw_day_cell(
                od,
                theme,
                s,
                memos,
                day,
                today,
                (cx, cy, cx + cell_w, cy + cell_h),
            )
    composed = Image.alpha_composite(img, overlay)
    img.paste(composed)


def _draw_day_cell(
    draw: ImageDraw.ImageDraw,
    theme: Theme,
    s: Scale,
    memos: list[dict[str, Any]],
    day: date,
    today: date,
    box: tuple[float, float, float, float],
) -> None:
    inset = s(4)
    x0, y0, x1, y1 = box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset
    in_month = day.month == today.month
    is_today = day == today
    is_past = day < today
    weekend = day.weekday() >= 5
    items = events_on(memos, day, skip_daily=True, include_done=True)

    radius = s(10)
    if is_today:
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=with_alpha(theme.accent, 38),
            outline=with_alpha(theme.accent, 210),
            width=max(s(2), 1),
        )
    elif in_month and items:
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=with_alpha(theme.text, 12),
        )
    else:
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=with_alpha(theme.text, 6),
        )

    if not in_month:
        num_fill = theme.other_month
    elif is_today:
        num_fill = theme.accent
    elif weekend:
        num_fill = theme.weekend
    else:
        num_fill = theme.text

    num_font = font(s(18), bold=True)
    put_text(draw, (x0 + s(10), y0 + s(6)), str(day.day), num_font, num_fill)

    if is_today:
        put_text(
            draw,
            (x1 - s(10), y0 + s(8)),
            "今天",
            font(s(13), bold=True),
            theme.accent,
            anchor="rt",
        )
    elif in_month:
        pending_n = sum(1 for m in items if not is_done(m, day))
        done_n = sum(1 for m in items if is_done(m, day))
        if pending_n or done_n:
            badge = f"{pending_n}" if not done_n else f"{done_n}✓" if not pending_n else f"{pending_n}/{pending_n + done_n}"
            put_text(
                draw,
                (x1 - s(10), y0 + s(8)),
                badge,
                font(s(13)),
                theme.muted if is_past else theme.accent,
                anchor="rt",
            )

    if not items:
        return

    line_h = s(22)
    text_top = y0 + s(32)
    avail = y1 - text_top - s(6)
    max_lines = max(1, int(avail // line_h))
    shown = items[:max_lines]
    leftover = len(items) - len(shown)
    if leftover > 0 and max_lines >= 1:
        shown = items[: max_lines - 1]
        leftover = len(items) - len(shown)

    title_font = font(s(14))
    for i, memo in enumerate(shown):
        yy = text_top + i * line_h
        if yy + s(16) > y1 - s(4):
            break
        done = is_done(memo, day)
        color = tag_color(theme, memo.get("tag") or "life")
        if done or not in_month:
            color = mix(color, theme.faint, 0.45)
        bar_x = x0 + s(8)
        draw.rounded_rectangle(
            (bar_x, yy + s(4), bar_x + s(5), yy + s(16)),
            radius=s(2),
            fill=color,
        )
        title = memo.get("title") or ""
        time_text = memo.get("time") or ""
        label = f"{time_text} {title}".strip() if time_text else title
        if done:
            label = f"✓ {label}"
        fill = theme.faint if (done or not in_month) else theme.text
        if is_past and in_month and not done:
            fill = theme.muted
        text = ellipsize(draw, label, title_font, (x1 - s(10)) - (bar_x + s(10)))
        put_text(draw, (bar_x + s(10), yy + s(1)), text, title_font, fill)

    if leftover > 0:
        yy = text_top + len(shown) * line_h
        if yy + s(14) < y1 - s(2):
            put_text(
                draw,
                (x0 + s(10), yy),
                f"还有 {leftover} 件",
                font(s(12)),
                theme.muted,
            )


def refresh_wallpaper(state: dict[str, Any], apply: bool = True) -> Path:
    return render_wallpaper(state, apply=apply)
