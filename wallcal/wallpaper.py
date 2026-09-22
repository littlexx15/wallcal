from __future__ import annotations

import calendar
from datetime import date, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageOps

from .fonts import font
from .holidays import mark_on, month_counts, next_rest_day
from .memos import daily_habits, events_on, is_done, month_stats, pending_on
from .paths import DATA_DIR, WALLPAPER_PATH
from .themes import Theme, get_theme, tag_color, readable_theme, theme_from_settings
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

    def text(self, value: float) -> int:
        return max(11, round(value * self.k * getattr(self, "font_scale", 1.0)))

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


def wrap_text(draw, text, fnt, width, limit=2):
    """Fit complete lines, with an explicit ellipsis only on the last line."""
    text = " ".join(text.split())
    lines = []
    while text and len(lines) < limit:
        if len(lines) == limit - 1:
            lines.append(ellipsize(draw, text, fnt, width))
            break
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if draw.textlength(text[:mid], font=fnt) <= width:
                lo = mid
            else:
                hi = mid - 1
        if not lo:
            break
        lines.append(text[:lo])
        text = text[lo:].lstrip()
    return lines


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


def render_wallpaper_image(
    state: dict[str, Any],
    *,
    now: datetime | None = None,
    size: tuple[int, int] | None = None,
) -> Image.Image:
    now = now or datetime.now()
    today = now.date()
    settings = state.get("settings", {})
    theme = theme_from_settings(settings)
    memos = state.get("memos") or []
    show_holidays = bool(state.get("settings", {}).get("show_holidays", True))
    personal = state.get("personal_holidays") or []
    width, height = size or screen_size()
    s = Scale(width, height)
    s.font_scale = float(settings.get("font_scale", 1.0))

    img = gradient_bg((width, height), theme.bg0, theme.bg1).convert("RGBA")
    img = apply_vignette(img)

    background = settings.get("background")
    s.picture_background = bool(background)
    if background:
        with Image.open(background) as source:
            img = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), (width, height)).convert("RGBA")

    margin = max(12, s(30))
    top = margin
    bottom = height - max(64, s(80))
    left = margin
    right = width - margin
    if size is None:
        from .winwallpaper import work_area
        wx0, wy0, wx1, wy1 = work_area()
        left = max(left, wx0 + margin)
        top = max(top, wy0 + margin)
        right = min(right, wx1 - margin)
        bottom = min(bottom, wy1 - margin)
    available = right - left
    layout = settings.get("layout", "right")
    if layout == "auto":
        from .desktop_layout import icon_rectangles, free_rectangle
        icons = settings.get("_icon_rectangles")
        if icons is None:
            icons = icon_rectangles() if size is None else []
        left, top, right, bottom = free_rectangle((left,top,right,bottom), icons,
            padding=max(12,s(18)), minimum=(max(440,s(650)),max(300,s(480))))
    elif layout != "full":
        left = right - int(available * {"compact": 0.58, "four_fifths": 0.8}.get(layout, 0.67))
    visibility = max(0, min(60, float(settings.get("background_visibility", 35))))
    panel = (*theme.card[:3], round(255 * (1 - visibility / 100))) if background else theme.card
    header = (*theme.card[:3], round(255 * min(1, 1.15 - visibility / 100))) if background else theme.card
    header_h = max(s(116), s.text(20) * 4 + s(16))
    img = rounded_card(img, (left, top, right, top + header_h), s(18), header, theme.card_line)
    _draw_header(
        img,
        theme,
        s,
        now,
        today,
        memos,
        (left + s(20), top + s(10), right - s(20), top + header_h),
        show_holidays,
        personal,
    )

    cal_box = (left, top + header_h + s(12), right, bottom)
    img = rounded_card(img, cal_box, s(24), panel, theme.card_line, max(s(1), 1))
    _draw_month_grid(img, theme, s, memos, today, cal_box, show_holidays, personal)


    return img.convert("RGB")


def render_wallpaper(
    state: dict[str, Any], *, now: datetime | None = None,
    size: tuple[int, int] | None = None, dest: Path | None = None,
    apply: bool = False,
) -> Path:
    rgb = render_wallpaper_image(state, now=now, size=size)
    out = dest or _next_desktop_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(".tmp")
    rgb.save(temporary, "JPEG", quality=95, optimize=True)
    temporary.replace(out)
    try:
        rgb.save(WALLPAPER_PATH, "JPEG", quality=95, optimize=True)
    except OSError:
        pass
    if apply:
        set_wallpaper(out)
    return out


def _next_desktop_path() -> Path:
    import uuid
    return DATA_DIR / f"desktop_{uuid.uuid4().hex}.jpg"


def _draw_header(
    img: Image.Image,
    theme: Theme,
    s: Scale,
    now: datetime,
    today: date,
    memos: list[dict[str, Any]],
    box: tuple[int, int, int, int],
    show_holidays: bool,
    personal: list[dict[str, Any]],
) -> None:
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    width = x1 - x0
    title = f"{today.year} 年 {today.month} 月   ·   今天 {today.day} 日  {WEEKDAYS[today.weekday()]}"
    put_text(draw, (x0, y0), ellipsize(draw, title, font(s.text(26), bold=True), width), font(s.text(26), bold=True), theme.text)
    pending, done = month_stats(memos, today.year, today.month)
    stats = f"今日待办 {len(pending_on(memos, today))} 件    本月待办 {pending} 件    已完成 {done} 件"
    put_text(draw, (x0, y0 + s.text(34)), ellipsize(draw, stats, font(s.text(16)), width), font(s.text(16)), theme.accent)
    marks = mark_on(today, personal, include_official=show_holidays)
    hint = f"{marks.name}  ·  " if marks else ""
    hint += "过去日期已淡化 · 打开壁历编辑事项"
    put_text(draw, (x0, y0 + s.text(60)), ellipsize(draw, hint, font(s.text(13)), width), font(s.text(13)), theme.muted)


def _draw_month_grid(
    img: Image.Image,
    theme: Theme,
    s: Scale,
    memos: list[dict[str, Any]],
    today: date,
    box: tuple[int, int, int, int],
    show_holidays: bool,
    personal: list[dict[str, Any]],
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
        put_text(draw, (cx, y + s(4)), name, font(s.text(18), bold=True), color, anchor="mt")

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
                show_holidays,
                personal,
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
    show_holidays: bool,
    personal: list[dict[str, Any]],
) -> None:
    inset = s(4)
    x0, y0, x1, y1 = box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset
    in_month = day.month == today.month
    is_today = day == today
    is_past = day < today
    weekend = day.weekday() >= 5
    items = events_on(memos, day, skip_daily=False, include_done=True)
    holiday = mark_on(day, personal, include_official=show_holidays)

    radius = s(10)
    photo = getattr(s, "picture_background", False)
    if is_today:
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=with_alpha(theme.accent, 32 if photo else 55),
            outline=with_alpha(theme.accent, 210),
            width=max(s(3), 2),
        )
    elif is_past and in_month:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=with_alpha(theme.muted, 12 if photo else 28))
    elif holiday and holiday.kind == "off":
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=with_alpha(theme.weekend, 20 if photo else 36),
        )
    elif holiday and holiday.kind == "leave":
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=with_alpha(theme.life, 20 if photo else 36),
        )
    elif in_month and items:
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=with_alpha(theme.text, 8 if photo else 12),
        )
    else:
        draw.rounded_rectangle(
            (x0, y0, x1, y1),
            radius=radius,
            fill=with_alpha(theme.text, 4 if photo else 6),
        )

    if not in_month:
        num_fill = theme.other_month
    elif is_today:
        num_fill = theme.accent
    elif holiday and holiday.kind == "off":
        num_fill = theme.weekend
    elif weekend:
        num_fill = theme.weekend
    else:
        num_fill = theme.text

    num_font = font(s.text(18), bold=True)
    put_text(draw, (x0 + s(10), y0 + s(6)), str(day.day), num_font, num_fill)

    badge = ""
    badge_color = theme.muted
    if holiday and holiday.kind == "off":
        badge, badge_color = "休", theme.weekend
    elif holiday:
        badge, badge_color = {"leave": "年", "rest": "休", "work": "班"}.get(holiday.kind, "假"), theme.life
    elif is_today:
        badge, badge_color = "今天", theme.accent
    elif in_month:
        pending_n = sum(1 for m in items if not is_done(m, day))
        done_n = sum(1 for m in items if is_done(m, day))
        if pending_n or done_n:
            badge = f"{pending_n}" if not done_n else f"完{done_n}" if not pending_n else f"{pending_n}/{pending_n + done_n}"
            badge_color = theme.muted if is_past else theme.accent
    if is_today and holiday:
        badge = "今天"
        badge_color = theme.accent
    if badge:
        put_text(
            draw,
            (x1 - s(10), y0 + s(8)),
            badge,
            font(s.text(13), bold=True if holiday or is_today else False),
            badge_color,
            anchor="rt",
        )

    extra_lines: list[tuple[str, tuple[int, int, int]]] = []
    if holiday and in_month:
        label = holiday.name
        color = theme.weekend if holiday.kind == "off" else theme.life
        extra_lines.append((label, color))

    line_h = s.text(14) + max(2, s(3))
    text_top = y0 + max(s(28), s.text(18) + s(7))
    if extra_lines:
        put_text(
            draw,
            (x0 + s(10), text_top),
            ellipsize(draw, extra_lines[0][0], font(s.text(13), bold=True), (x1 - s(12)) - (x0 + s(10))),
            font(s.text(13), bold=True),
            extra_lines[0][1],
        )
        text_top += s.text(13) + s(8)

    if not items:
        return
    avail = y1 - text_top - s(6)
    max_lines = max(0, int(avail // line_h))
    title_font = font(s.text(14))
    used_lines = 0
    shown_count = 0
    for i, memo in enumerate(items):
        remaining = max_lines - used_lines
        if remaining <= (1 if i < len(items) - 1 else 0):
            break
        # Reserve one line per following item, or one overflow indicator.
        reserve = min(len(items) - i - 1, max(0, remaining - 1))
        budget = min(2, remaining - reserve)
        yy = text_top + used_lines * line_h
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
        text_x = bar_x + s(12)
        if done:
            tick = max(8, s.text(12))
            draw.line([(text_x, yy + tick * .55), (text_x + tick * .35, yy + tick * .9),
                       (text_x + tick, yy + tick * .15)], fill=theme.accent, width=max(2, s(2)))
            text_x += tick + s(5)
        fill = theme.faint if (done or not in_month) else theme.text
        if is_past and in_month and not done:
            fill = theme.muted
        lines = wrap_text(draw, label, title_font, (x1 - s(10)) - text_x, budget)
        if not lines:
            break
        for line_index, text in enumerate(lines):
            put_text(draw, (text_x, yy + line_index * line_h + s(1)), text, title_font, fill)
        used_lines += len(lines)
        shown_count += 1

    leftover = len(items) - shown_count
    if leftover > 0 and used_lines < max_lines:
        put_text(draw, (x0 + s(10), text_top + used_lines * line_h),
                 ellipsize(draw, f"还有 {leftover} 件 · 打开壁历查看", font(s.text(12)), x1-x0-s(20)), font(s.text(12)), theme.muted)



def refresh_wallpaper(state: dict[str, Any], apply: bool = True) -> Path:
    return render_wallpaper(state, apply=apply)
