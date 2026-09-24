from __future__ import annotations

import calendar
import threading
import queue
import traceback
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
from .memos import is_done, memos_on, pending_on, toggle_done, reschedule_once
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
from .timeinput import parse_time
from .dialogs import SettingsDialogs
from .themes import readable_theme, theme_from_settings, theme_choices
from .paths import LOG_PATH
from .winwallpaper import work_area

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


class WallCalWindow(SettingsDialogs, ctk.CTk):
    def __init__(self) -> None:
        state = load()
        ctk.set_widget_scaling(float(state["settings"].get("ui_scale", 1.0)))
        super().__init__()
        self.store = state
        if ensure_welcome(self.store):
            save(self.store)
        theme_key = self.store["settings"].get("theme") or "eye"
        self.theme = theme_from_settings(self.store["settings"])
        ctk.set_appearance_mode(self.theme.ui_mode)
        ctk.set_default_color_theme("green")
        for kind in ("CTkButton", "CTkOptionMenu"):
            ctk.ThemeManager.theme[kind]["fg_color"] = ["#4A6C52", "#355D45"]
            ctk.ThemeManager.theme[kind]["text_color"] = ["#FFFFFF", "#FFFFFF"]
        ctk.ThemeManager.theme["CTkOptionMenu"]["button_color"] = ["#355D45", "#294B36"]

        self.title(f"壁历 v{__version__} — 在这里写备忘")
        self.minsize(800, 520)
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
        self._render_generation = 0
        self._render_request = None
        self._render_results = queue.SimpleQueue()
        self._sync_results = queue.SimpleQueue()
        self._revision = 0
        self._closed = False
        self._last_day = date.today()
        self._last_screen = None
        self._icon_probe_busy = False
        self._icon_signature = None
        self._icon_candidate = None
        self._layout_help_shown = False
        self._icon_results = queue.SimpleQueue()
        self._day_buttons: dict[date, ctk.CTkButton] = {}
        self._memo_rows = []
        self._empty_label = None
        self._want_show = False
        self._want_new_day = False
        self._pending_wallpaper = None
        self._pending_status: str | None = None
        self._sync_busy = False
        self._want_sync_pull = False
        self._want_sync_push = False
        self._want_reload_ui = False

        self._build()
        self._apply_chrome()
        self.redraw()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.after(80, self.show_window)
        self.after(200, self._pump_flags)
        self.after(400, lambda: self.title_entry.focus_set())
        self._fit_window(initial=True)
        self.after(500, self.refresh_wallpaper_async)
        self.after(2000, self._check_clock)
        self.after(200, self._check_icons)
        if cloudsync.logged_in() and not self.store["settings"].get("sync_paused"):
            self.after(900, self._queue_sync_pull)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=4, uniform="main")
        self.grid_columnconfigure(1, weight=6, uniform="main")
        self.grid_rowconfigure(1, weight=1)

        self._build_top()
        self.content = ctk.CTkFrame(self, fg_color=self.theme.ui_surface)
        self.content.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=0)
        self.content.grid_columnconfigure(1, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
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
            text=f"v{__version__}  ·  选一天，写下安排。",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=self.theme.ui_muted,
        )
        subtitle.grid(row=0, column=1, columnspan=7, sticky="w", padx=(8, 0))
        self._title_label = title
        self._subtitle_label = subtitle

        theme_labels = list(theme_choices(self.store["settings"])) + ["＋ 图片主题…"]
        current_label = self.theme.label
        self.theme_menu = ctk.CTkOptionMenu(
            bar,
            values=theme_labels,
            width=112,
            command=self._on_theme,
            fg_color=self.theme.ui_accent,
            button_color=self.theme.ui_hover,
            button_hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
            dropdown_fg_color=self.theme.ui_card,
            dropdown_text_color=self.theme.ui_text,
        )
        self.theme_menu.set(current_label)
        self.theme_menu.grid(row=1, column=0, padx=8)

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
        self.holiday_switch.grid(row=1, column=1, padx=6)

        self.autostart_var = ctk.BooleanVar(value=autostart.is_enabled())
        self.autostart_switch = ctk.CTkSwitch(
            bar,
            text="开机启动",
            variable=self.autostart_var,
            command=self._on_autostart,
            progress_color=self.theme.ui_accent,
        )
        self.autostart_switch.grid(row=1, column=2, padx=6)

        refresh_btn = ctk.CTkButton(
            bar,
            text="刷新壁纸",
            width=96,
            fg_color=self.theme.ui_accent,
            hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
            command=self._resume_wallpaper,
        )
        refresh_btn.grid(row=1, column=3, padx=6)
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
        self.sync_btn.grid(row=1, column=4, padx=6)
        display_btn = ctk.CTkButton(bar, text="显示设置", width=86, command=self._open_display_settings)
        data_btn = ctk.CTkButton(bar, text="导出 / 备份", width=96, command=self._open_data_tools)
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
        self.quit_btn.grid(row=1, column=7, padx=(0, 0))
        toolbar = [self.theme_menu, self.holiday_switch, self.autostart_switch, refresh_btn, self.sync_btn, display_btn, data_btn, self.quit_btn]
        previous_columns = [None]
        def arrange(event):
            columns = 8 if event.width/bar._get_widget_scaling() >= 1020 else 4
            if previous_columns[0] == columns:
                return
            previous_columns[0] = columns
            for i in range(8):
                bar.grid_columnconfigure(i, weight=1 if i < columns else 0)
            subtitle.grid_configure(columnspan=columns-1)
            for i, widget in enumerate(toolbar):
                widget.grid(row=1+i//columns, column=i%columns, padx=4, pady=4, sticky="w")
        bar.bind("<Configure>", arrange, add="+")


    def _build_calendar_panel(self) -> None:
        panel = ctk.CTkFrame(
            self.content,
            corner_radius=16,
            fg_color=self.theme.ui_card,
            border_width=1,
            border_color=self.theme.ui_border,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=10)
        self.cal_panel = panel
        panel.configure(width=252)
        panel.grid_propagate(False)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)

        nav = ctk.CTkFrame(panel, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 2))
        nav.grid_columnconfigure(1, weight=1)

        nav_style = {
            "width": 26,
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
            font=ctk.CTkFont(family="Microsoft YaHei", size=15, weight="bold"),
            text_color=self.theme.ui_text,
        )
        self.month_label.grid(row=0, column=1)
        ctk.CTkButton(nav, text="›", command=lambda: self._shift_month(1), **nav_style).grid(row=0, column=2)
        ctk.CTkButton(
            nav,
            text="今天",
            width=42,
            fg_color=self.theme.ui_accent,
            hover_color=self.theme.ui_hover,
            text_color=self._on_accent_hex(),
            command=self._goto_today,
        ).grid(row=0, column=3, padx=(4, 0))

        head = ctk.CTkFrame(panel, fg_color="transparent")
        head.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))
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
        self.cal_grid.grid(row=2, column=0, sticky="nsew", padx=6, pady=(2, 8))
        for i in range(7):
            self.cal_grid.grid_columnconfigure(i, weight=1)
        for r in range(6):
            self.cal_grid.grid_rowconfigure(r, weight=1)

    def _build_memo_panel(self) -> None:
        panel = ctk.CTkFrame(
            self.content,
            corner_radius=22,
            fg_color=self.theme.ui_card,
            border_width=1,
            border_color=self.theme.ui_border,
        )
        panel.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=10)
        self.memo_panel = panel
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(3, weight=1)

        self.day_title = ctk.CTkLabel(
            panel,
            text="",
            font=ctk.CTkFont(family="Microsoft YaHei", size=18, weight="bold"),
            text_color=self.theme.ui_text,
            anchor="w",
        )
        self.day_title.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 2))
        self.holiday_banner = ctk.CTkLabel(
            panel,
            text="",
            anchor="w",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=self.theme.ui_accent,
        )
        self.holiday_banner.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 2))

        self.memo_list = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.memo_list.grid(row=3, column=0, sticky="nsew", padx=10, pady=4)

        form = ctk.CTkFrame(panel, fg_color="transparent")
        form.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 8))
        form.grid_columnconfigure(0, weight=1)

        hint = ctk.CTkLabel(
            form,
            text="写在下面，会出现在桌面日历对应的那一格。",
            anchor="w",
            font=ctk.CTkFont(family="Microsoft YaHei", size=13),
            text_color=self.theme.ui_muted,
        )
        # The editor is always visible above the independently scrolling list.

        self.edit_date_row = ctk.CTkFrame(form, fg_color="transparent")
        ctk.CTkLabel(self.edit_date_row, text="日期").pack(side="left", padx=(0, 6))
        self.edit_date_entry = ctk.CTkEntry(self.edit_date_row, width=125, placeholder_text="YYYY-MM-DD")
        self.edit_date_entry.pack(side="left")
        self.edit_date_hint = ctk.CTkLabel(self.edit_date_row, text="格式：2026-09-23")
        self.edit_date_hint.pack(side="left", padx=8)

        self.title_entry = ctk.CTkEntry(
            form,
            placeholder_text="例如：下午三点开会",
            height=38,
            font=ctk.CTkFont(family="Microsoft YaHei", size=15),
            fg_color=self.theme.ui_input,
            border_color=self.theme.ui_border,
            text_color=self.theme.ui_text,
            placeholder_text_color=self.theme.ui_muted,
        )
        self.title_entry.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.title_entry.bind("<Return>", lambda _e: self._submit_memo())

        self.time_entry = ctk.CTkEntry(
            form,
            placeholder_text="时间 09:30",
            width=80,
            fg_color=self.theme.ui_input,
            border_color=self.theme.ui_border,
            text_color=self.theme.ui_text,
            placeholder_text_color=self.theme.ui_muted,
        )
        self.time_entry.grid(row=2, column=0, sticky="ew", padx=(0, 8))

        self.tag_menu = ctk.CTkOptionMenu(form, values=list(TAG_KEYS.values()), width=76)
        self.tag_menu.set("生活")
        self.tag_menu.grid(row=2, column=1, padx=4)

        self.repeat_menu = ctk.CTkOptionMenu(form, values=list(REPEAT_KEYS.values()), width=82)
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
        self.submit_btn.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        self.cancel_edit_btn = ctk.CTkButton(
            form,
            text="取消编辑",
            text_color=self.theme.ui_text,
            width=90,
            fg_color="transparent",
            border_width=1,
            command=self._cancel_edit,
        )
        self.cancel_edit_btn.grid(row=4, column=0, columnspan=3, sticky="e", pady=(8, 0))
        self.cancel_edit_btn.grid_forget()

        holiday_bar = ctk.CTkFrame(form, fg_color="transparent")
        holiday_bar.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        quiet = {
            "height": 30,
            "fg_color": "transparent",
            "border_width": 1,
            "border_color": self.theme.ui_border,
            "text_color": self.theme.ui_muted,
            "hover_color": self.theme.ui_input,
        }
        ctk.CTkButton(
            holiday_bar, text="标记休假", width=72, command=self._mark_leave, **quiet
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            holiday_bar, text="清除标记", width=72, command=self._clear_personal_mark, **quiet
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            holiday_bar, text="本年假日一览", width=96, command=self._show_year_holidays, **quiet
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
        self.month_label.configure(text=f"{self.view_year} 年 {self.view_month} 月")
        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(self.view_year, self.view_month)
        visible_days = {day for week in weeks for day in week}
        for old_day in set(self._day_buttons) - visible_days:
            self._day_buttons.pop(old_day).destroy()
        today = date.today()
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                in_month = day.month == self.view_month
                items = pending_on(self.store["memos"], day) if in_month else []
                is_today = day == today
                is_selected = day == self.selected
                label = str(day.day)
                holiday = None
                holiday = mark_on(day, self.store.get("personal_holidays") or [], include_official=self.store["settings"].get("show_holidays", True))
                if holiday:
                    tag = {"off": "休", "leave": "年", "rest": "休", "work": "班"}.get(holiday.kind, "")
                    label = f"{day.day}\n{tag}".strip()
                elif items:
                    label = f"{day.day}\n·{len(items)}"

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

                style = dict(text=label, fg_color=fg, hover_color=hover, text_color=text_color,
                             border_width=border, border_color=border_color)
                btn = self._day_buttons.get(day)
                if btn is None:
                    btn = ctk.CTkButton(self.cal_grid, width=24, height=30, corner_radius=7,
                        font=ctk.CTkFont(family="Microsoft YaHei", size=12),
                        command=lambda d=day: self._select_day(d), **style)
                    self._day_buttons[day] = btn
                    btn._wallcal_style = style
                elif getattr(btn, "_wallcal_style", None) != style:
                    btn.configure(**style)
                    btn._wallcal_style = style
                position = (r, c)
                if getattr(btn, "_wallcal_position", None) != position:
                    btn.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")
                    btn._wallcal_position = position

    def _redraw_memos(self) -> None:
        weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][
            self.selected.weekday()
        ]
        flag = "（今天）" if self.selected == date.today() else ""
        items = memos_on(self.store["memos"], self.selected)
        pending = pending_on(self.store["memos"], self.selected)
        self.day_title.configure(
            text=f"{self.selected.month}月{self.selected.day}日  {weekday} {flag}"
        )
        holiday = None
        holiday = mark_on(self.selected, self.store.get("personal_holidays") or [], include_official=self.store["settings"].get("show_holidays", True))
        if holiday:
            prefix = "法定安排" if holiday.official else "个人安排"
            self.holiday_banner.configure(text=f"{prefix} · {holiday.name}")
        else:
            self.holiday_banner.configure(text="可标记年假、休息日或调休上班。")

        if self._empty_label is None:
            self._empty_label = ctk.CTkLabel(self.memo_list, text="这一天还没有安排，直接在上方写一条。",
                anchor="w", font=ctk.CTkFont(family="Microsoft YaHei", size=13), text_color=self.theme.ui_muted)
        for row in self._memo_rows[len(items):]:
            row.pack_forget()
        if not items:
            self._empty_label.configure(text_color=self.theme.ui_muted)
            self._empty_label.pack(anchor="w", padx=8, pady=12)
        else:
            self._empty_label.pack_forget()
            for index, memo in enumerate(items):
                self._memo_row(memo, index)

    def _memo_row(self, memo: dict[str, Any], index: int) -> None:
        if index < len(self._memo_rows):
            row = self._memo_rows[index]
        else:
            row = ctk.CTkFrame(self.memo_list, fg_color=self.theme.ui_input, corner_radius=12)
            row.grid_columnconfigure(0, weight=1)
            row._title = ctk.CTkLabel(row, text="", anchor="w", justify="left", wraplength=340,
                font=ctk.CTkFont(family="Microsoft YaHei", size=15, weight="bold"))
            row._title.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 3))
            row._last_wrap = 340
            def wrap_title(event):
                width = max(100, int(event.width/row._get_widget_scaling())-30)
                if width != row._last_wrap:
                    row._last_wrap = width
                    row._title.configure(wraplength=width)
            row.bind("<Configure>", wrap_title)
            controls = ctk.CTkFrame(row, fg_color="transparent")
            controls.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
            controls.grid_columnconfigure(0, weight=1)
            row._detail = ctk.CTkLabel(controls, text="", anchor="w")
            row._detail.grid(row=0, column=0, sticky="w")
            row._buttons = []
            for col, (label, action) in enumerate((("完成", self._toggle_done), ("编辑", self._start_edit), ("删除", self._delete_memo)), 1):
                button = ctk.CTkButton(controls, text=label, width=48, height=28, fg_color="transparent", border_width=1,
                    command=lambda fn=action, card=row: fn(card._memo))
                button.grid(row=0, column=col, padx=3)
                row._buttons.append(button)
            self._memo_rows.append(row)
        row._memo = memo
        done = is_done(memo, self.selected)
        row.configure(fg_color=self.theme.ui_input)
        row._title.configure(text=("已完成 · " if done else "") + (memo.get("title") or ""),
            text_color=self.theme.ui_muted if done else self.theme.ui_text)
        row._detail.configure(text=f"{memo.get('time') or '全天'} · {TAG_KEYS.get(memo.get('tag'), '生活')}", text_color=self.theme.ui_muted)
        row._buttons[0].configure(text="撤销" if done else "完成")
        for button in row._buttons:
            button.configure(border_color=self.theme.ui_border, text_color=self.theme.ui_text, hover_color=self.theme.ui_card)
        if not row.winfo_manager():
            row.pack(fill="x", padx=4, pady=5)

    def _select_day(self, day: date) -> None:
        self.selected = day
        self.view_year = day.year
        self.view_month = day.month
        self._cancel_edit()
        self.redraw()
        self.title_entry.focus_set()

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
                try:
                    raw_date = self.edit_date_entry.get().strip()
                    target = date.fromisoformat(raw_date)
                    if target.isoformat() != raw_date or not 1900 <= target.year <= 9998:
                        raise ValueError("日期请写成 YYYY-MM-DD，例如 2026-09-23")
                    if (memo.get("repeat") or "none") != "none" or repeat != "none":
                        if raw_date != memo["date"]:
                            raise ValueError("重复事项暂不支持改期，请保持原日期")
                    else:
                        reschedule_once(memo, target)
                        self.selected = target
                        self.view_year, self.view_month = target.year, target.month
                except ValueError as exc:
                    messagebox.showwarning("日期无法保存", str(exc), parent=self)
                    return
                memo["title"] = title
                memo["time"] = time_value
                memo["tag"] = tag
                memo["repeat"] = repeat
                touch_memo(memo)
            self.editing_id = None
            self.submit_btn.configure(text="添加备忘")
            self.cancel_edit_btn.grid_forget()
            self.edit_date_row.grid_forget()
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
        repeating = (memo.get("repeat") or "none") != "none"
        self.edit_date_entry.configure(state="normal")
        self.edit_date_entry.delete(0, "end")
        self.edit_date_entry.insert(0, memo["date"])
        self.edit_date_entry.configure(state="disabled" if repeating else "normal")
        self.edit_date_hint.configure(text="重复事项暂不支持改期" if repeating else "YYYY-MM-DD · 可改期")
        self.edit_date_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, memo.get("title") or "")
        self.time_entry.delete(0, "end")
        self.time_entry.insert(0, memo.get("time") or "")
        self.tag_menu.set(TAG_KEYS.get(memo.get("tag") or "life", "生活"))
        self.repeat_menu.set(REPEAT_KEYS.get(memo.get("repeat") or "none", "仅一次"))
        self.submit_btn.configure(text="保存修改")
        self.cancel_edit_btn.grid(row=4, column=0, columnspan=3, sticky="e", pady=(8, 0))

    def _cancel_edit(self) -> None:
        self.edit_date_row.grid_forget()
        self.editing_id = None
        self.submit_btn.configure(text="添加备忘")
        self.cancel_edit_btn.grid_forget()
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
        if label == "＋ 图片主题…":
            self.theme_menu.set(self.theme.label)
            self._open_image_theme()
            return
        key = theme_choices(self.store["settings"]).get(label, "eye")
        settings = self.store["settings"]
        settings["theme"] = key
        profile = settings.get("custom_themes", {}).get(key)
        settings["background"] = profile.get("background", "") if profile else ""
        self._persist()
        self._refresh_appearance()
        self.refresh_wallpaper_async("正在切换整套主题…")

    def _apply_chrome(self) -> None:
        # Recolor existing controls without rebuilding widgets or losing typed text.
        theme = self.theme
        defaults = {
            "CTkFrame": dict(fg_color=theme.ui_card,top_fg_color=theme.ui_card,border_color=theme.ui_border),
            "CTkLabel": dict(text_color=theme.ui_text),
            "CTkButton": dict(fg_color=theme.ui_accent,hover_color=theme.ui_hover,text_color=self._on_accent_hex(),border_color=theme.ui_border),
            "CTkEntry": dict(fg_color=theme.ui_input,text_color=theme.ui_text,placeholder_text_color=theme.ui_muted,border_color=theme.ui_border),
            "CTkOptionMenu": dict(fg_color=theme.ui_accent,button_color=theme.ui_hover,button_hover_color=theme.ui_hover,text_color=self._on_accent_hex()),
            "CTkSwitch": dict(progress_color=theme.ui_accent,text_color=theme.ui_text),
            "CTkCheckBox": dict(fg_color=theme.ui_accent,text_color=theme.ui_text,checkmark_color=self._on_accent_hex())}
        for kind, values in defaults.items():
            for key, value in values.items():
                ctk.ThemeManager.theme[kind][key] = [value,value]
        previous = getattr(self, "_applied_theme", theme)
        mapping = {getattr(previous,key).lower(): getattr(theme,key) for key in
            ("ui_surface","ui_card","ui_input","ui_text","ui_muted","ui_border","ui_accent","ui_hover")}
        self.configure(fg_color=theme.ui_surface)
        def visit(widget):
            try:
                if isinstance(widget, (ctk.CTkToplevel,)):
                    widget.configure(fg_color=theme.ui_surface)
                elif isinstance(widget, ctk.CTkScrollableFrame):
                    widget.configure(fg_color=theme.ui_card, scrollbar_button_color=theme.ui_border, scrollbar_button_hover_color=theme.ui_accent)
                elif isinstance(widget, ctk.CTkFrame):
                    current = widget.cget("fg_color")
                    if current != "transparent":
                        if isinstance(current,str): color = mapping.get(current.lower(),theme.ui_card)
                        else: color = theme.ui_card
                        widget.configure(fg_color=color)
                elif isinstance(widget, ctk.CTkOptionMenu):
                    widget.configure(fg_color=theme.ui_accent,button_color=theme.ui_hover,button_hover_color=theme.ui_hover,
                        text_color=self._on_accent_hex(),dropdown_fg_color=theme.ui_card,dropdown_text_color=theme.ui_text,
                        dropdown_hover_color=theme.ui_border)
                elif isinstance(widget, ctk.CTkButton):
                    if widget.cget("fg_color") == "transparent":
                        widget.configure(text_color=theme.ui_text,border_color=theme.ui_border,hover_color=theme.ui_input)
                    else:
                        widget.configure(fg_color=theme.ui_accent,hover_color=theme.ui_hover,text_color=self._on_accent_hex())
                elif isinstance(widget, ctk.CTkEntry):
                    widget.configure(fg_color=theme.ui_input,border_color=theme.ui_border,text_color=theme.ui_text,placeholder_text_color=theme.ui_muted)
                elif isinstance(widget, ctk.CTkLabel):
                    widget.configure(text_color=theme.ui_text)
                elif isinstance(widget, ctk.CTkSwitch):
                    widget.configure(progress_color=theme.ui_accent,text_color=theme.ui_text)
                elif isinstance(widget, ctk.CTkCheckBox):
                    widget.configure(fg_color=theme.ui_accent,text_color=theme.ui_text,checkmark_color=self._on_accent_hex())
            except (ValueError, AttributeError):
                pass
            for child in widget.winfo_children():
                visit(child)
        for child in self.winfo_children(): visit(child)
        self.content.configure(fg_color=theme.ui_surface)
        for panel in (self.cal_panel,self.memo_panel):
            panel.configure(fg_color=theme.ui_card,border_color=theme.ui_border)
        self.theme_menu.configure(values=list(theme_choices(self.store["settings"])) + ["＋ 图片主题…"])
        self.theme_menu.set(theme.label)
        self._day_buttons_style_reset()
        self._applied_theme = theme

    def _day_buttons_style_reset(self):
        for button in self._day_buttons.values():
            button._wallcal_style = None

    def _on_toggle_holidays(self) -> None:
        enabled = bool(self.holiday_var.get())
        self.store["settings"]["show_holidays"] = enabled
        self._persist()
        self.redraw()
        self.refresh_wallpaper_async("已显示法定假日" if enabled else "已隐藏法定假日")

    def _mark_leave(self) -> None:
        self._open_holiday_dialog()

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
        self._revision += 1
        save(self.store)
        self._queue_sync_push()

    def _queue_sync_push(self) -> None:
        if cloudsync.autosync_enabled() and not self.store["settings"].get("sync_paused"):
            self._want_sync_push = True

    def _queue_sync_pull(self) -> None:
        if cloudsync.logged_in():
            self._want_sync_pull = True

    def _start_sync_job(self, mode: str) -> None:
        if self._sync_busy:
            return
        self._sync_busy = True
        snapshot = deepcopy(self.store)
        revision = self._revision
        def job() -> None:
            try:
                if mode == "pull":
                    merged, message = cloudsync.pull_and_merge(snapshot)
                else:
                    merged, message = None, cloudsync.push_state(snapshot)
                self._sync_results.put((revision, merged, message))
            except Exception as exc:
                self._sync_results.put((revision, None, f"同步失败：{exc}"))
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
            self.store["settings"]["sync_paused"] = False
            save(self.store)
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
            self.store["settings"]["sync_paused"] = not bool(auto_var.get())
            save(self.store)
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
                self.theme = theme_from_settings(self.store["settings"])
                ctk.set_appearance_mode(self.theme.ui_mode)
                self._apply_chrome()
                if hasattr(self, "holiday_var"):
                    self.holiday_var.set(bool(self.store["settings"].get("show_holidays", True)))
                self.redraw()
            if self._pending_status is not None:
                text = self._pending_status
                self._pending_status = None
                self._set_status(text)
            while not self._icon_results.empty():
                signature, error = self._icon_results.get_nowait()
                self._icon_probe_busy = False
                delay = self._accept_icon_probe(signature, error)
                self.after(delay, self._check_icons)
            while not self._sync_results.empty():
                revision, merged, message = self._sync_results.get_nowait()
                self._sync_busy = False
                if merged is not None:
                    if revision != self._revision:
                        # Retry from current data; never replace newer edits with an old snapshot.
                        self._want_sync_pull = True
                    else:
                        self.store = merged
                        save(self.store)
                        self._want_reload_ui = True
                        self.refresh_wallpaper_async()
                self._set_status(message)
            while not self._render_results.empty():
                generation, path, error = self._render_results.get_nowait()
                self._refreshing = False
                monitor_id = None
                if isinstance(path, tuple):
                    path, monitor_id = path
                if generation != self._render_generation:
                    if path:
                        path.unlink(missing_ok=True)
                    continue
                if error:
                    self._set_status(f"壁纸更新失败：{error}")
                    if ("连续空白区域" in error or "桌面图标" in error) and self.store["settings"].get("layout") == "auto" and not self._layout_help_shown:
                        self._layout_help_shown = True
                        if messagebox.askyesno("自动布局无法完成", "当前桌面无法找到足够空白区域，或无法读取图标位置。\n\n是否切换为全屏日历？不会移动或隐藏桌面图标。\n如使用动态壁纸或桌面整理软件，请先退出或在其设置中调整。", parent=self):
                            self.store["settings"]["layout"] = "full"
                            self._persist()
                            self.refresh_wallpaper_async("已切换全屏，正在生成日历…")
                elif self.store["settings"].get("wallpaper_enabled", True):
                    self._apply_rendered_wallpaper(path, monitor_id)
            if self._render_request is not None and not self._refreshing:
                generation, snapshot = self._render_request
                self._render_request = None
                self._refreshing = True
                def render_job(generation=generation, snapshot=snapshot):
                    try:
                        path = render_wallpaper(snapshot, apply=False)
                        self._render_results.put((generation, (path, snapshot["settings"].get("_resolved_monitor_id", "")), None))
                    except Exception as exc:
                        self._render_results.put((generation, None, str(exc)))
                threading.Thread(target=render_job, daemon=True).start()
            if not self._sync_busy and self._want_sync_pull:
                self._want_sync_pull = False
                self._start_sync_job("pull")
            elif not self._sync_busy and self._want_sync_push:
                self._want_sync_push = False
                self._start_sync_job("push")
        except Exception:
            self._log_exception()
        if not self._closed:
            self.after(150, self._pump_flags)

    def refresh_wallpaper_async(self, message: str | None = None) -> None:
        if not self.store["settings"].get("wallpaper_enabled", True):
            return
        if message:
            self._set_status(message)
        self._render_generation += 1
        self._render_request = (self._render_generation, deepcopy(self.store))

    def _resume_wallpaper(self) -> None:
        self.store["settings"]["wallpaper_enabled"] = True
        save(self.store)
        self.refresh_wallpaper_async("正在刷新壁纸…")

    def _check_clock(self) -> None:
        if self._closed:
            return
        try:
            from .winwallpaper import screen_size
            from .monitors import screens
            screen = (screen_size(), work_area(), tuple((m["id"], m["rect"]) for m in screens()))
            if date.today() != self._last_day:
                self._last_day = date.today()
                self.on_new_day()
            elif self._last_screen is not None and screen != self._last_screen:
                self.refresh_wallpaper_async()
                self._fit_window()
            self._last_screen = screen
        except Exception:
            self._log_exception()
        self.after(20000, self._check_clock)

    def _check_icons(self) -> None:
        if self._closed or self._icon_probe_busy:
            return
        if self.store["settings"].get("layout") != "auto" or not self.store["settings"].get("wallpaper_enabled", True):
            self._icon_signature = self._icon_candidate = None
            self.after(2000, self._check_icons)
            return
        self._icon_probe_busy = True
        def probe():
            try:
                from .desktop_layout import icon_rectangles
                self._icon_results.put((tuple(icon_rectangles(force=True)), None))
            except Exception as exc:
                self._icon_results.put((None, str(exc)))
        threading.Thread(target=probe, daemon=True).start()

    def _accept_icon_probe(self, signature, error) -> int:
        # Two matching samples one second apart confirm a stable change.
        if self.store["settings"].get("layout") != "auto" or not self.store["settings"].get("wallpaper_enabled", True):
            self._icon_signature = self._icon_candidate = None
            return 2000
        if error:
            self._icon_candidate = None
            self._set_status(error)
            return 2000
        if self._icon_signature is None:
            self._icon_signature = signature
        if signature == self._icon_signature:
            self._icon_candidate = None
            return 2000
        if signature != self._icon_candidate:
            self._icon_candidate = signature
            return 1000
        self._icon_signature = signature
        self._icon_candidate = None
        self.refresh_wallpaper_async("桌面图标位置已稳定，正在调整布局…")
        # Use the confirmed coordinates; no second icon scan during rendering.
        if self._render_request is not None:
            self._render_request[1]["settings"]["_icon_rectangles"] = signature
        return 2000

    def _log_exception(self) -> None:
        try:
            with LOG_PATH.open("a", encoding="utf-8") as stream:
                stream.write(traceback.format_exc() + "\n")
        except OSError:
            pass

    def report_callback_exception(self, exc, value, tb) -> None:
        try:
            with LOG_PATH.open("a", encoding="utf-8") as stream:
                stream.write("".join(traceback.format_exception(exc, value, tb)))
        finally:
            messagebox.showerror("操作未完成", str(value), parent=self)

    def _fit_window(self, initial: bool = False) -> None:
        x0, y0, x1, y1 = work_area()
        scale = self._get_window_scaling()
        max_w, max_h = max(480, int((x1-x0-24)/scale)), max(380, int((y1-y0-48)/scale))
        self.minsize(min(800, max_w), min(520, max_h))
        stored = self.store["settings"].get("window", {}) if initial else {}
        w = min(max_w, int(stored.get("width", 1100) if initial else self._current_width))
        h = min(max_h, int(stored.get("height", 740) if initial else self._current_height))
        x = int(stored.get("x", x0+12)) if initial else self.winfo_x()
        y = int(stored.get("y", y0+12)) if initial else self.winfo_y()
        x = max(x0, min(x, x1 - int(w*scale) - 12))
        y = max(y0, min(y, y1 - int(h*scale) - 36))
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _save_window(self) -> None:
        if self.state() == "normal":
            scale = self._get_window_scaling()
            self.store["settings"]["window"] = {"width": round(self.winfo_width()/scale), "height": round(self.winfo_height()/scale), "x": self.winfo_x(), "y": self.winfo_y()}
            save(self.store)

    def _apply_rendered_wallpaper(self, path, monitor_id=None) -> None:
        try:
            from .winwallpaper import set_wallpaper

            set_wallpaper(path, monitor_id=monitor_id if monitor_id is not None else self.store["settings"].get("monitor_id", ""))
            self._set_status("桌面壁纸已更新。日期会自动刷新，可在显示设置中恢复原壁纸。")
            from .paths import DATA_DIR
            files = sorted(DATA_DIR.glob("desktop_*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in files[3:]:
                if old != path:
                    try:
                        old.unlink()
                    except OSError:
                        pass
        except Exception as exc:
            self._set_status(f"壁纸更新失败：{exc}")

    def on_new_day(self) -> None:
        today = date.today()
        self._last_day = today
        self.selected = today
        self.view_year = today.year
        self.view_month = today.month
        self.redraw()
        self.refresh_wallpaper_async("新的一天到了，正在换上今日壁纸…")

    def hide_to_tray(self) -> None:
        self._save_window()
        self.iconify()
        self._set_status("已缩到任务栏。再点任务栏上的「壁历」就能继续写备忘。")

    def show_window(self) -> None:
        try:
            self.deiconify()
            self._fit_window()
            self.lift()
            self.focus_force()
            self.attributes("-topmost", True)
            self.update_idletasks()
            self.after(800, lambda: self.attributes("-topmost", False))
            self.after(200, lambda: self.title_entry.focus_set())
        except Exception:
            pass

    def quit_app(self) -> None:
        self._save_window()
        self._closed = True
        self._render_generation += 1
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.destroy()
