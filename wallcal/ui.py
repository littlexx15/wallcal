from __future__ import annotations

import calendar
import re
import threading
from copy import deepcopy
from datetime import date
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from . import autostart
from . import __version__
from .holidays import (
    mark_on,
    official_years,
    remove_personal,
    upsert_personal,
    year_groups,
)
from .icon import ensure_icon
from .memos import is_done, memos_on, pending_on, toggle_done
from .paths import ICON_PATH
from .storage import ensure_welcome, load, new_memo, remember_deleted, save, touch_memo
from . import sync as cloudsync
from .themes import (
    REPEAT_FROM_LABEL,
    REPEAT_KEYS,
    TAG_FROM_LABEL,
    TAG_KEYS,
    THEMES,
    get_theme,
    tag_hex,
)
from .wallpaper import render_wallpaper

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
WEEK_HEADER = ["日", "一", "二", "三", "四", "五", "六"]


def _short_date(value: str) -> str:
    day = date.fromisoformat(value[:10])
    return f"{day.month}/{day.day}"


def _compact_range(values: list[str]) -> str:
    if not values:
        return "—"
    days = [date.fromisoformat(v[:10]) for v in values]
    if len(days) == 1:
        return _short_date(values[0])
    return f"{_short_date(values[0])}–{_short_date(values[-1])}（{len(days)}天）"


def parse_time(value: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return ""
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return None


class WallCalWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.store = load()
        if ensure_welcome(self.store):
            save(self.store)
        theme_key = self.store["settings"].get("theme") or "eye"
        if theme_key == "dusk":
            theme_key = "celadon"
            self.store["settings"]["theme"] = "eye"
            save(self.store)
        if theme_key == "ink":
            theme_key = "eye"
            self.store["settings"]["theme"] = "eye"
            save(self.store)
        self.theme = get_theme(theme_key)
        ctk.set_appearance_mode(self.theme.ui_mode)
        ctk.set_default_color_theme("green")

        self.title(f"壁历 v{__version__} — 在这里写备忘")
        self.geometry("1100x740+50+36")
        self.minsize(980, 660)
        self.configure(fg_color=self.theme.ui_surface)
        try:
            self.iconname("壁历")
        except Exception:
            pass

        ensure_icon()

        self.selected = date.today()
        self.view_year = self.selected.year
        self.view_month = self.selected.month
        self.editing_id: str | None = None
        self.tray = None
        self._refreshing = False
        self._day_buttons: dict[date, ctk.CTkButton] = {}
        self._want_show = False
        self._want_new_day = False
        self._pending_wallpaper = None
        self._pending_status: str | None = None
        self._sync_busy = False
        self._want_sync_pull = False
        self._want_sync_push = False
        self._want_reload_ui = False

        self._build()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.after(80, self.show_window)
        self.after(200, self._pump_flags)
        self.after(400, lambda: self.title_entry.focus_set())
        if cloudsync.logged_in():
            self.after(900, self._queue_sync_pull)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_top()
        self._build_calendar_panel()
        self._build_memo_panel()
        self._build_status()
        self.redraw()

    def _build_top(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 8))
        bar.grid_columnconfigure(1, weight=1)

        title = ctk.CTkLabel(
            bar,
            text="壁历",
            font=ctk.CTkFont(family="Microsoft YaHei", size=28, weight="bold"),
            text_color=self.theme.ui_text,
        )
        title.grid(row=0, column=0, sticky="w")
        subtitle = ctk.CTkLabel(
            bar,
            text=f"  v{__version__}  ·  选一天，写下安排。整月日程铺在桌面上。",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=self.theme.ui_muted,
        )
        subtitle.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self._title_label = title
        self._subtitle_label = subtitle

        theme_labels = [item.label for item in THEMES.values()]
        current_label = self.theme.label
        self.theme_menu = ctk.CTkOptionMenu(
            bar,
            values=theme_labels,
            width=88,
            command=self._on_theme,
            fg_color=self.theme.ui_accent,
            button_color=self.theme.ui_hover,
            button_hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
            dropdown_fg_color=self.theme.ui_card,
            dropdown_text_color=self.theme.ui_text,
        )
        self.theme_menu.set(current_label)
        self.theme_menu.grid(row=0, column=2, padx=8)

        self.holiday_var = ctk.BooleanVar(
            value=bool(self.store["settings"].get("show_holidays", True))
        )
        self.holiday_switch = ctk.CTkSwitch(
            bar,
            text="法定假日",
            variable=self.holiday_var,
            command=self._on_toggle_holidays,
            progress_color=self.theme.ui_accent,
        )
        self.holiday_switch.grid(row=0, column=3, padx=6)

        self.autostart_var = ctk.BooleanVar(value=bool(self.store["settings"].get("autostart")))
        self.autostart_switch = ctk.CTkSwitch(
            bar,
            text="开机启动",
            variable=self.autostart_var,
            command=self._on_autostart,
            progress_color=self.theme.ui_accent,
        )
        self.autostart_switch.grid(row=0, column=4, padx=6)

        refresh_btn = ctk.CTkButton(
            bar,
            text="刷新壁纸",
            width=96,
            fg_color=self.theme.ui_accent,
            hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
            command=lambda: self.refresh_wallpaper_async("正在刷新壁纸…"),
        )
        refresh_btn.grid(row=0, column=5, padx=6)
        self.sync_btn = ctk.CTkButton(
            bar,
            text="云同步",
            width=72,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme.ui_border,
            text_color=self.theme.ui_text,
            hover_color=self.theme.ui_card,
            command=self._open_sync_window,
        )
        self.sync_btn.grid(row=0, column=6, padx=6)
        self.quit_btn = ctk.CTkButton(
            bar,
            text="退出",
            width=64,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme.ui_border,
            text_color=self.theme.ui_muted,
            hover_color=self.theme.ui_card,
            command=self.quit_app,
        )
        self.quit_btn.grid(row=0, column=7, padx=(0, 0))

    def _build_calendar_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            corner_radius=22,
            fg_color=self.theme.ui_card,
            border_width=1,
            border_color=self.theme.ui_border,
        )
        panel.grid(row=1, column=0, sticky="nsew", padx=(20, 8), pady=10)
        self.cal_panel = panel
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        nav = ctk.CTkFrame(panel, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        nav.grid_columnconfigure(1, weight=1)

        nav_style = {
            "width": 40,
            "fg_color": "transparent",
            "border_width": 1,
            "border_color": self.theme.ui_border,
            "text_color": self.theme.ui_text,
            "hover_color": self.theme.ui_input,
        }
        ctk.CTkButton(nav, text="‹", command=lambda: self._shift_month(-1), **nav_style).grid(row=0, column=0)
        self.month_label = ctk.CTkLabel(
            nav,
            text="",
            font=ctk.CTkFont(family="Microsoft YaHei", size=20, weight="bold"),
            text_color=self.theme.ui_text,
        )
        self.month_label.grid(row=0, column=1)
        ctk.CTkButton(nav, text="›", command=lambda: self._shift_month(1), **nav_style).grid(row=0, column=2)
        ctk.CTkButton(
            nav,
            text="今天",
            width=64,
            fg_color=self.theme.ui_accent,
            hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
            command=self._goto_today,
        ).grid(row=0, column=3, padx=(8, 0))

        head = ctk.CTkFrame(panel, fg_color="transparent")
        head.grid(row=1, column=0, sticky="ew", padx=16, pady=(8, 0))
        for i, name in enumerate(WEEK_HEADER):
            head.grid_columnconfigure(i, weight=1)
            color = self.theme.ui_accent if i in (0, 6) else self.theme.ui_muted
            ctk.CTkLabel(
                head,
                text=name,
                text_color=color,
                font=ctk.CTkFont(family="Microsoft YaHei", size=13, weight="bold"),
            ).grid(row=0, column=i, pady=4)

        self.cal_grid = ctk.CTkFrame(panel, fg_color="transparent")
        self.cal_grid.grid(row=2, column=0, sticky="nsew", padx=12, pady=(4, 16))
        for i in range(7):
            self.cal_grid.grid_columnconfigure(i, weight=1)
        for r in range(6):
            self.cal_grid.grid_rowconfigure(r, weight=1)

    def _build_memo_panel(self) -> None:
        panel = ctk.CTkFrame(
            self,
            corner_radius=22,
            fg_color=self.theme.ui_card,
            border_width=1,
            border_color=self.theme.ui_border,
        )
        panel.grid(row=1, column=1, sticky="nsew", padx=(8, 20), pady=10)
        self.memo_panel = panel
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        self.day_title = ctk.CTkLabel(
            panel,
            text="",
            font=ctk.CTkFont(family="Microsoft YaHei", size=22, weight="bold"),
            text_color=self.theme.ui_text,
            anchor="w",
        )
        self.day_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 4))
        self.holiday_banner = ctk.CTkLabel(
            panel,
            text="",
            anchor="w",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=self.theme.ui_accent,
        )
        self.holiday_banner.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 4))

        self.memo_list = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.memo_list.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)

        form = ctk.CTkFrame(panel, fg_color="transparent")
        form.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 16))
        form.grid_columnconfigure(0, weight=1)

        hint = ctk.CTkLabel(
            form,
            text="写在下面，会出现在桌面日历对应的那一格。",
            anchor="w",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=self.theme.ui_muted,
        )
        hint.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 6))

        self.title_entry = ctk.CTkEntry(
            form,
            placeholder_text="例如：下午三点开会",
            height=46,
            font=ctk.CTkFont(family="Microsoft YaHei", size=15),
            fg_color=self.theme.ui_input,
            border_color=self.theme.ui_border,
            text_color=self.theme.ui_text,
            placeholder_text_color=self.theme.ui_muted,
        )
        self.title_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        self.title_entry.bind("<Return>", lambda _e: self._submit_memo())

        self.time_entry = ctk.CTkEntry(
            form,
            placeholder_text="时间 09:30",
            width=110,
            fg_color=self.theme.ui_input,
            border_color=self.theme.ui_border,
            text_color=self.theme.ui_text,
            placeholder_text_color=self.theme.ui_muted,
        )
        self.time_entry.grid(row=2, column=0, sticky="w", padx=(0, 8))

        self.tag_menu = ctk.CTkOptionMenu(form, values=list(TAG_KEYS.values()), width=90)
        self.tag_menu.set("生活")
        self.tag_menu.grid(row=2, column=1, padx=4)

        self.repeat_menu = ctk.CTkOptionMenu(form, values=list(REPEAT_KEYS.values()), width=96)
        self.repeat_menu.set("仅一次")
        self.repeat_menu.grid(row=2, column=2, padx=4)

        self.submit_btn = ctk.CTkButton(
            form,
            text="添加备忘",
            width=110,
            height=36,
            fg_color=self.theme.ui_accent,
            hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
            command=self._submit_memo,
        )
        self.submit_btn.grid(row=2, column=3, padx=(8, 0))

        self.cancel_edit_btn = ctk.CTkButton(
            form,
            text="取消编辑",
            width=90,
            fg_color="transparent",
            border_width=1,
            command=self._cancel_edit,
        )
        self.cancel_edit_btn.grid(row=3, column=3, sticky="e", pady=(8, 0))
        self.cancel_edit_btn.grid_remove()

        holiday_bar = ctk.CTkFrame(form, fg_color="transparent")
        holiday_bar.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        quiet = {
            "height": 30,
            "fg_color": "transparent",
            "border_width": 1,
            "border_color": self.theme.ui_border,
            "text_color": self.theme.ui_muted,
            "hover_color": self.theme.ui_input,
        }
        ctk.CTkButton(
            holiday_bar, text="标成年假", width=84, command=self._mark_leave, **quiet
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            holiday_bar, text="清除年假", width=84, command=self._clear_personal_mark, **quiet
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            holiday_bar, text="本年假日一览", width=104, command=self._show_year_holidays, **quiet
        ).pack(side="left", padx=6)

    def _build_status(self) -> None:
        self.status = ctk.CTkLabel(
            self,
            text="格子里 休=法定放假，年=自己的年假。点「本年假日一览」看全年安排。",
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            text_color=self.theme.ui_muted,
            anchor="w",
        )
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=22, pady=(0, 12))

    def _on_accent_hex(self) -> str:
        r, g, b = self.theme.on_accent
        return f"#{r:02x}{g:02x}{b:02x}"

    def redraw(self) -> None:
        self._redraw_calendar()
        self._redraw_memos()

    def _redraw_calendar(self) -> None:
        self.month_label.configure(text=f"{self.view_year} 年 {MONTHS[self.view_month - 1]}")
        for child in self.cal_grid.winfo_children():
            child.destroy()
        self._day_buttons.clear()

        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(self.view_year, self.view_month)
        today = date.today()
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                in_month = day.month == self.view_month
                items = pending_on(self.store["memos"], day) if in_month else []
                is_today = day == today
                is_selected = day == self.selected
                label = str(day.day)
                holiday = None
                if self.store["settings"].get("show_holidays", True):
                    holiday = mark_on(day, self.store.get("personal_holidays") or [])
                if holiday:
                    tag = {"off": "休", "leave": "年"}.get(holiday.kind, "")
                    label = f"{day.day} {tag}".strip()
                elif items:
                    label = f"{day.day}  ·{len(items)}"

                fg = "transparent"
                hover = self.theme.ui_input
                text_color = self.theme.ui_text if in_month else self.theme.ui_muted
                border = 0
                border_color = self.theme.ui_border

                if not in_month:
                    text_color = self.theme.ui_muted
                elif is_today:
                    fg = self.theme.ui_accent
                    text_color = self._on_accent_hex()
                    hover = self.theme.ui_hover
                elif is_selected:
                    fg = self.theme.ui_input
                    border = 2
                    border_color = self.theme.ui_accent
                elif holiday and holiday.kind == "off":
                    fg = self.theme.ui_input
                    text_color = "#A56A60"
                elif items:
                    fg = self.theme.ui_input
                    text_color = self.theme.ui_accent

                btn = ctk.CTkButton(
                    self.cal_grid,
                    text=label,
                    width=46,
                    height=44,
                    corner_radius=12,
                    fg_color=fg,
                    hover_color=hover,
                    text_color=text_color,
                    border_width=border,
                    border_color=border_color,
                    font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold" if is_today or is_selected else "normal"),
                    command=lambda d=day: self._select_day(d),
                )
                btn.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
                self._day_buttons[day] = btn

    def _redraw_memos(self) -> None:
        weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][
            self.selected.weekday()
        ]
        flag = "（今天）" if self.selected == date.today() else ""
        items = memos_on(self.store["memos"], self.selected)
        pending = pending_on(self.store["memos"], self.selected)
        self.day_title.configure(
            text=f"{self.selected.month}月{self.selected.day}日  {weekday} {flag}    {len(pending)} 件待办"
        )
        holiday = None
        if self.store["settings"].get("show_holidays", True):
            holiday = mark_on(self.selected, self.store.get("personal_holidays") or [])
        if holiday:
            if holiday.kind == "off":
                banner = f"法定放假 · {holiday.name}"
            else:
                banner = f"个人年假 · {holiday.name}"
            self.holiday_banner.configure(text=banner)
        else:
            self.holiday_banner.configure(text="不是法定假日。可以把这一天标成自己的年假。")

        for child in self.memo_list.winfo_children():
            child.destroy()

        if not items:
            empty = ctk.CTkLabel(
                self.memo_list,
                text="这一天还空着。\n写一件小事，就会出现在桌面日历格里。",
                justify="left",
                font=ctk.CTkFont(family="Microsoft YaHei", size=14),
                text_color=self.theme.ui_muted,
            )
            empty.pack(anchor="w", padx=8, pady=18)
            return

        for memo in items:
            self._memo_row(memo)

    def _memo_row(self, memo: dict[str, Any]) -> None:
        done = is_done(memo, self.selected)
        row = ctk.CTkFrame(
            self.memo_list,
            corner_radius=14,
            fg_color=self.theme.ui_input,
            border_width=1,
            border_color=self.theme.ui_border,
        )
        row.pack(fill="x", padx=6, pady=6)
        row.grid_columnconfigure(3, weight=1)

        tag_key = memo.get("tag") or "life"
        tag_label = TAG_KEYS.get(tag_key, "生活")
        color = tag_hex(self.theme, tag_key)
        bar = ctk.CTkFrame(row, width=5, corner_radius=3, fg_color=color)
        bar.grid(row=0, column=0, sticky="ns", padx=(8, 6), pady=10)
        tag = ctk.CTkLabel(
            row,
            text=tag_label,
            width=44,
            text_color=color,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12, weight="bold"),
        )
        tag.grid(row=0, column=1, padx=(2, 4), pady=10)

        time_text = memo.get("time") or "全天"
        ctk.CTkLabel(
            row,
            text=time_text,
            width=52,
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=self.theme.ui_muted,
        ).grid(row=0, column=2, padx=4)

        title_color = self.theme.ui_muted if done else self.theme.ui_text
        title = memo.get("title") or ""
        if done:
            title = f"✓  {title}"
        repeat = REPEAT_KEYS.get(memo.get("repeat") or "none", "仅一次")
        extra = "" if repeat == "仅一次" else f"  · {repeat}"
        ctk.CTkLabel(
            row,
            text=title + extra,
            anchor="w",
            font=ctk.CTkFont(family="Microsoft YaHei", size=14, weight="bold"),
            text_color=title_color,
        ).grid(row=0, column=3, sticky="ew", padx=6)

        quiet = {
            "width": 54,
            "fg_color": "transparent",
            "border_width": 1,
            "border_color": self.theme.ui_border,
            "text_color": self.theme.ui_muted,
            "hover_color": self.theme.ui_card,
        }
        ctk.CTkButton(
            row,
            text="未做" if done else "完成",
            command=lambda m=memo: self._toggle_done(m),
            **quiet,
        ).grid(row=0, column=4, padx=3)
        ctk.CTkButton(
            row,
            text="编辑",
            command=lambda m=memo: self._start_edit(m),
            **quiet,
        ).grid(row=0, column=5, padx=3)
        ctk.CTkButton(
            row,
            text="删除",
            width=54,
            fg_color="transparent",
            border_width=1,
            border_color=self.theme.ui_border,
            text_color="#A56A60",
            hover_color=self.theme.ui_card,
            command=lambda m=memo: self._delete_memo(m),
        ).grid(row=0, column=6, padx=(3, 10))

    def _select_day(self, day: date) -> None:
        self.selected = day
        self.view_year = day.year
        self.view_month = day.month
        self._cancel_edit()
        self.redraw()

    def _shift_month(self, delta: int) -> None:
        month = self.view_month + delta
        year = self.view_year
        while month < 1:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        self.view_year, self.view_month = year, month
        self._redraw_calendar()

    def _goto_today(self) -> None:
        self._select_day(date.today())

    def _submit_memo(self) -> None:
        title = self.title_entry.get().strip()
        if not title:
            self._set_status("先写一下要做的事")
            return
        time_value = parse_time(self.time_entry.get())
        if time_value is None:
            messagebox.showwarning("时间格式", "时间请写成 09:30 这样，也可以留空。")
            return
        tag = TAG_FROM_LABEL.get(self.tag_menu.get(), "life")
        repeat = REPEAT_FROM_LABEL.get(self.repeat_menu.get(), "none")

        if self.editing_id:
            memo = next((m for m in self.store["memos"] if m["id"] == self.editing_id), None)
            if memo:
                memo["title"] = title
                memo["time"] = time_value
                memo["tag"] = tag
                memo["repeat"] = repeat
                memo["date"] = self.selected.isoformat()
                touch_memo(memo)
            self.editing_id = None
            self.submit_btn.configure(text="添加备忘")
            self.cancel_edit_btn.grid_remove()
            self._set_status("备忘已更新，壁纸即将刷新")
        else:
            self.store["memos"].append(
                new_memo(
                    title=title,
                    day=self.selected,
                    time=time_value,
                    tag=tag,
                    repeat=repeat,
                )
            )
            self._set_status("已写上，桌面壁纸马上会看到这件事")

        self.title_entry.delete(0, "end")
        self.time_entry.delete(0, "end")
        self._persist()
        self.redraw()
        self.refresh_wallpaper_async()

    def _start_edit(self, memo: dict[str, Any]) -> None:
        self.editing_id = memo["id"]
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, memo.get("title") or "")
        self.time_entry.delete(0, "end")
        self.time_entry.insert(0, memo.get("time") or "")
        self.tag_menu.set(TAG_KEYS.get(memo.get("tag") or "life", "生活"))
        self.repeat_menu.set(REPEAT_KEYS.get(memo.get("repeat") or "none", "仅一次"))
        self.submit_btn.configure(text="保存修改")
        self.cancel_edit_btn.grid()

    def _cancel_edit(self) -> None:
        self.editing_id = None
        self.submit_btn.configure(text="添加备忘")
        self.cancel_edit_btn.grid_remove()
        self.title_entry.delete(0, "end")
        self.time_entry.delete(0, "end")

    def _toggle_done(self, memo: dict[str, Any]) -> None:
        toggle_done(memo, self.selected)
        touch_memo(memo)
        self._persist()
        self.redraw()
        self.refresh_wallpaper_async("状态已更新，壁纸刷新中")

    def _delete_memo(self, memo: dict[str, Any]) -> None:
        if not messagebox.askyesno("删除备忘", f"删除「{memo.get('title')}」？"):
            return
        remember_deleted(self.store, str(memo["id"]))
        self.store["memos"] = [m for m in self.store["memos"] if m["id"] != memo["id"]]
        if self.editing_id == memo["id"]:
            self._cancel_edit()
        self._persist()
        self.redraw()
        self.refresh_wallpaper_async("已删除，壁纸刷新中")

    def _on_theme(self, label: str) -> None:
        key = next((k for k, t in THEMES.items() if t.label == label), "eye")
        self.store["settings"]["theme"] = key
        self.theme = get_theme(key)
        self._persist()
        ctk.set_appearance_mode(self.theme.ui_mode)
        self._apply_chrome()
        self.redraw()
        self.refresh_wallpaper_async("正在切换壁纸主题…")

    def _apply_chrome(self) -> None:
        self.configure(fg_color=self.theme.ui_surface)
        for panel in (getattr(self, "cal_panel", None), getattr(self, "memo_panel", None)):
            if panel is not None:
                panel.configure(fg_color=self.theme.ui_card, border_color=self.theme.ui_border)
        if hasattr(self, "_title_label"):
            self._title_label.configure(text_color=self.theme.ui_text)
        if hasattr(self, "_subtitle_label"):
            self._subtitle_label.configure(text_color=self.theme.ui_muted)
        self.theme_menu.configure(
            fg_color=self.theme.ui_accent,
            button_color=self.theme.ui_hover,
            button_hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
            dropdown_fg_color=self.theme.ui_card,
            dropdown_text_color=self.theme.ui_text,
        )
        self.submit_btn.configure(
            fg_color=self.theme.ui_accent,
            hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
        )
        if hasattr(self, "sync_btn"):
            self.sync_btn.configure(
                border_color=self.theme.ui_border,
                text_color=self.theme.ui_text,
                hover_color=self.theme.ui_card,
            )
        if hasattr(self, "quit_btn"):
            self.quit_btn.configure(
                border_color=self.theme.ui_border,
                text_color=self.theme.ui_muted,
                hover_color=self.theme.ui_card,
            )
        self.day_title.configure(text_color=self.theme.ui_text)
        self.month_label.configure(text_color=self.theme.ui_text)
        self.status.configure(text_color=self.theme.ui_muted)
        self.title_entry.configure(
            fg_color=self.theme.ui_input,
            border_color=self.theme.ui_border,
            text_color=self.theme.ui_text,
            placeholder_text_color=self.theme.ui_muted,
        )

    def _on_toggle_holidays(self) -> None:
        enabled = bool(self.holiday_var.get())
        self.store["settings"]["show_holidays"] = enabled
        self._persist()
        self.redraw()
        self.refresh_wallpaper_async("已显示法定假日" if enabled else "已隐藏法定假日")

    def _mark_leave(self) -> None:
        personal = list(self.store.get("personal_holidays") or [])
        official = mark_on(self.selected, [])
        if official and official.kind == "off":
            self._set_status("这一天已经是法定放假，不用再标年假")
            return
        self.store["personal_holidays"] = upsert_personal(
            personal, self.selected, kind="leave", name="年假"
        )
        self._persist()
        self.redraw()
        self.refresh_wallpaper_async("已标成年假，壁纸刷新中")

    def _clear_personal_mark(self) -> None:
        personal = list(self.store.get("personal_holidays") or [])
        self.store["personal_holidays"] = remove_personal(personal, self.selected)
        self._persist()
        self.redraw()
        self.refresh_wallpaper_async("已清除这一天的个人假期标记")

    def _show_year_holidays(self) -> None:
        year = self.view_year
        win = ctk.CTkToplevel(self)
        win.title(f"{year} 年假日一览")
        win.geometry("520x520")
        win.transient(self)
        box = ctk.CTkScrollableFrame(win, fg_color="transparent")
        box.pack(fill="both", expand=True, padx=16, pady=16)
        groups = year_groups(year)
        head = ctk.CTkLabel(
            box,
            text=f"{year} 年国务院法定节假日",
            font=ctk.CTkFont(family="Microsoft YaHei", size=18, weight="bold"),
            anchor="w",
        )
        head.pack(fill="x", pady=(0, 8))
        if not groups:
            ctk.CTkLabel(
                box,
                text="这一年的放假安排还没写进软件。\n国务院一般在年底公布下一年。\n公布后更新壁历即可；也可以先把某天标成自己的年假。",
                justify="left",
                font=ctk.CTkFont(family="Microsoft YaHei", size=14),
            ).pack(fill="x", pady=8)
        else:
            source = "来源：国务院办公厅通知，只标放假，不标调休上班。"
            ctk.CTkLabel(
                box,
                text=source,
                justify="left",
                font=ctk.CTkFont(family="Microsoft YaHei", size=12),
                text_color=self.theme.ui_muted,
            ).pack(fill="x", pady=(0, 10))
            for group in groups:
                off_text = _compact_range(group["off"])
                line = f"{group['name']}    {off_text}"
                ctk.CTkLabel(
                    box,
                    text=line,
                    anchor="w",
                    justify="left",
                    font=ctk.CTkFont(family="Microsoft YaHei", size=14),
                ).pack(fill="x", pady=4)
        years = "、".join(str(y) for y in official_years())
        ctk.CTkLabel(
            box,
            text=f"软件已内置：{years}。选中某一天，可用「标成年假」记下自己的带薪假。",
            justify="left",
            wraplength=460,
            font=ctk.CTkFont(family="Microsoft YaHei", size=12),
            text_color=self.theme.ui_muted,
        ).pack(fill="x", pady=(16, 0))

    def _on_autostart(self) -> None:
        enabled = bool(self.autostart_var.get())
        try:
            autostart.set_enabled(enabled)
            self.store["settings"]["autostart"] = enabled
            save(self.store)
            self._set_status("开机启动已打开" if enabled else "开机启动已关闭")
        except OSError as exc:
            self.autostart_var.set(not enabled)
            messagebox.showerror("开机启动", str(exc))

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def request_show(self) -> None:
        self._want_show = True

    def request_new_day(self) -> None:
        self._want_new_day = True

    def _persist(self) -> None:
        save(self.store)
        self._queue_sync_push()

    def _queue_sync_push(self) -> None:
        if cloudsync.autosync_enabled():
            self._want_sync_push = True

    def _queue_sync_pull(self) -> None:
        if cloudsync.logged_in():
            self._want_sync_pull = True

    def _start_sync_job(self, mode: str) -> None:
        if self._sync_busy:
            return
        self._sync_busy = True
        snapshot = deepcopy(self.store)

        def job() -> None:
            try:
                if mode == "pull":
                    merged, message = cloudsync.pull_and_merge(snapshot)
                    self.store = merged
                    save(self.store)
                    self._want_reload_ui = True
                    self._pending_status = message
                    self.refresh_wallpaper_async()
                else:
                    message = cloudsync.push_state(snapshot)
                    self._pending_status = message
            except Exception as exc:
                self._pending_status = f"同步失败：{exc}"
            finally:
                self._sync_busy = False

        threading.Thread(target=job, daemon=True).start()

    def _open_sync_window(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("云同步")
        win.geometry("560x420")
        win.transient(self)
        pad = ctk.CTkFrame(win, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=20, pady=18)

        auth = cloudsync.load_auth()
        title = ctk.CTkLabel(
            pad,
            text="用 GitHub 账号同步待办",
            font=ctk.CTkFont(family="Microsoft YaHei", size=20, weight="bold"),
            anchor="w",
        )
        title.pack(fill="x")
        hint = ctk.CTkLabel(
            pad,
            text="登录后，待办、年假会存到你的 GitHub 私有 Gist。换电脑用同一个账号登录就能拉下来。",
            justify="left",
            wraplength=500,
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=self.theme.ui_muted,
        )
        hint.pack(fill="x", pady=(6, 12))

        status = ctk.CTkLabel(
            pad,
            text="",
            justify="left",
            anchor="w",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
        )
        status.pack(fill="x", pady=(0, 8))

        token_box = ctk.CTkEntry(pad, placeholder_text="粘贴 GitHub 令牌（gist 权限）", show="*", height=38)
        detected = cloudsync.detect_gh_token()
        if detected and not auth.get("token"):
            token_box.insert(0, detected)

        def refresh_status() -> None:
            info = cloudsync.load_auth()
            if info.get("token"):
                last = info.get("last_sync") or "还没有同步过"
                status.configure(text=f"已登录  @{info.get('login')}    上次同步：{last}")
                token_box.pack_forget()
            else:
                status.configure(text="还没登录。点下面创建令牌，勾选 gist，生成后粘贴过来。")
                token_box.pack(fill="x", pady=6)

        def do_login() -> None:
            try:
                cloudsync.login(token_box.get().strip() or cloudsync.detect_gh_token())
                refresh_status()
                self._queue_sync_pull()
                self._set_status("登录成功，正在同步…")
            except Exception as exc:
                messagebox.showerror("登录失败", str(exc))

        def do_sync() -> None:
            self._want_sync_pull = True
            win.destroy()

        def do_logout() -> None:
            cloudsync.clear_auth()
            refresh_status()
            token_box.pack(fill="x", pady=6)

        btns = ctk.CTkFrame(pad, fg_color="transparent")
        btns.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(
            btns,
            text="打开创建令牌网页",
            width=140,
            command=lambda: __import__("webbrowser").open(cloudsync.TOKEN_HELP),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btns, text="登录", width=80, command=do_login).pack(side="left", padx=4)
        ctk.CTkButton(btns, text="立即同步", width=90, command=do_sync).pack(side="left", padx=4)
        ctk.CTkButton(
            btns,
            text="退出登录",
            width=90,
            fg_color="transparent",
            border_width=1,
            command=do_logout,
        ).pack(side="left", padx=4)

        auto_var = ctk.BooleanVar(value=bool(auth.get("autosync", True)))

        def on_auto() -> None:
            info = cloudsync.load_auth()
            if not info.get("token"):
                return
            info["autosync"] = bool(auto_var.get())
            cloudsync.save_auth(info)

        ctk.CTkSwitch(
            pad,
            text="改动后自动同步",
            variable=auto_var,
            command=on_auto,
            progress_color=self.theme.ui_accent,
        ).pack(anchor="w", pady=(16, 0))
        refresh_status()

    def _pump_flags(self) -> None:
        try:
            if self._want_show:
                self._want_show = False
                self.show_window()
            if self._want_new_day:
                self._want_new_day = False
                self.on_new_day()
            if self._want_reload_ui:
                self._want_reload_ui = False
                self.theme = get_theme(self.store["settings"].get("theme", "eye"))
                ctk.set_appearance_mode(self.theme.ui_mode)
                self._apply_chrome()
                if hasattr(self, "holiday_var"):
                    self.holiday_var.set(bool(self.store["settings"].get("show_holidays", True)))
                self.redraw()
            if self._pending_status is not None:
                text = self._pending_status
                self._pending_status = None
                self._set_status(text)
            if self._pending_wallpaper is not None:
                path = self._pending_wallpaper
                self._pending_wallpaper = None
                self._apply_rendered_wallpaper(path)
            if not self._sync_busy and self._want_sync_pull:
                self._want_sync_pull = False
                self._start_sync_job("pull")
            elif not self._sync_busy and self._want_sync_push:
                self._want_sync_push = False
                self._start_sync_job("push")
        except Exception:
            pass
        self.after(150, self._pump_flags)

    def refresh_wallpaper_async(self, message: str | None = None) -> None:
        if message:
            self._set_status(message)
        snapshot = deepcopy(self.store)

        def job() -> None:
            try:
                path = render_wallpaper(snapshot, apply=False)
                self._pending_wallpaper = path
            except Exception as exc:
                self._pending_status = f"壁纸更新失败：{exc}"

        threading.Thread(target=job, daemon=True).start()

    def _apply_rendered_wallpaper(self, path) -> None:
        try:
            from .winwallpaper import set_wallpaper

            set_wallpaper(path)
            self._set_status("桌面壁纸已更新。日子过了会自动换上新一天的日程。")
        except Exception as exc:
            self._set_status(f"壁纸更新失败：{exc}")

    def on_new_day(self) -> None:
        today = date.today()
        self.selected = today
        self.view_year = today.year
        self.view_month = today.month
        self.redraw()
        self.refresh_wallpaper_async("新的一天到了，正在换上今日壁纸…")

    def hide_to_tray(self) -> None:
        self.iconify()
        self._set_status("已缩到任务栏。再点任务栏上的「壁历」就能继续写备忘。")

    def show_window(self) -> None:
        try:
            self.deiconify()
            self.geometry("1080x720+60+40")
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.update_idletasks()
            self.after(800, lambda: self.attributes("-topmost", False))
            self.after(200, lambda: self.title_entry.focus_set())
        except Exception:
            pass

    def quit_app(self) -> None:
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.destroy()
