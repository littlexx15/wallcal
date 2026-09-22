"""Isolated Windows GUI smoke test. Never changes the desktop wallpaper."""
import os
import sys
import time
import statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["WALLCAL_DATA_DIR"] = str(Path("build/gui-test-data").resolve())
from copy import deepcopy
from datetime import date, timedelta
from unittest.mock import patch
from PIL import ImageGrab
from wallcal import storage
from wallcal.winwallpaper import enable_dpi_awareness, work_area

state = deepcopy(storage.DEFAULT_STATE)
state["settings"]["first_run"] = False
state["memos"] = [storage.new_memo(title="整理本周工作计划，检查完整事项的显示", day=date.today(), time="09:30"),
                  storage.new_memo(title="午后散步十分钟", day=date.today(), time="14:00")]
state["memos"][1]["done_dates"] = [date.today().isoformat()]
storage.save(state)
enable_dpi_awareness()
from wallcal.ui import WallCalWindow
import customtkinter as ctk
out = Path("build/qa")
out.mkdir(parents=True, exist_ok=True)

def pump(app, seconds):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        app.update()
        time.sleep(.02)

def capture(widget, name):
    widget.update_idletasks()
    ImageGrab.grab(bbox=(widget.winfo_rootx(), widget.winfo_rooty(),
        widget.winfo_rootx()+widget.winfo_width(), widget.winfo_rooty()+widget.winfo_height())).save(out/name)

with patch("wallcal.winwallpaper.set_wallpaper") as apply, patch("wallcal.ui.cloudsync.logged_in", return_value=False), patch("wallcal.ui.autostart.is_enabled", return_value=False):
    app = WallCalWindow()
    callback_errors = []
    app.report_callback_exception = lambda exc, value, tb: callback_errors.append(str(value))
    try:
        deadline = time.monotonic()+8
        while apply.call_count < 1 and time.monotonic() < deadline:
            pump(app,.1)
        assert apply.call_count >= 1, f"startup did not refresh wallpaper: {app.status.cget("text")}"
        capture(app, "window.png")
        x0,y0,x1,y1 = work_area()
        assert app.winfo_y()+app.winfo_height() <= y1, "window crosses taskbar"
        assert app.time_entry.winfo_width() > 75, "time input squeezed out"
        assert app.submit_btn.winfo_rootx()+app.submit_btn.winfo_width() <= app.winfo_rootx()+app.winfo_width(), "submit button clipped"
        with patch("wallcal.ui.date") as clock, patch.object(app, "on_new_day") as change:
            clock.today.return_value = date.today()+timedelta(days=1)
            app._check_clock()
            change.assert_called_once()
        old_generation = app._render_generation
        app._render_request = None
        app.store["settings"]["wallpaper_enabled"] = False
        app._render_generation += 1
        stale = Path(os.environ["WALLCAL_DATA_DIR"])/"stale.jpg"
        stale.write_bytes(b"stale")
        before = apply.call_count
        app._render_results.put((old_generation, stale, None))
        app._pump_flags()
        assert apply.call_count == before and not stale.exists(), "stale render replaced restored wallpaper"
        # Rapid requests must eventually display the latest state.
        app.store["settings"]["wallpaper_enabled"] = True
        for i in range(8):
            app.store["settings"]["font_scale"] = 1.4 if i == 7 else 1.0
            app.refresh_wallpaper_async()
        deadline = time.monotonic()+8
        while (app._refreshing or app._render_request is not None) and time.monotonic() < deadline:
            pump(app,.1)
        assert not app._refreshing and app._render_request is None
        app._open_display_settings()
        pump(app, .5)
        dialogs = [w for w in app.winfo_children() if isinstance(w, ctk.CTkToplevel)]
        assert dialogs
        from wallcal.dialogs import DragOnlySlider
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        slider = next(w for w in descendants(dialogs[-1]) if isinstance(w, DragOnlySlider))
        panel = slider.master
        panel._parent_canvas.yview_moveto(.35)
        pump(app, .1)
        value_before = slider.get()
        scroll_before = panel._parent_canvas.yview()
        slider._canvas.event_generate("<MouseWheel>", delta=-120)
        pump(app, .1)
        assert slider.get() == value_before, "scrolling changed transparency"
        assert panel._parent_canvas.yview()[0] > scroll_before[0], "wheel did not scroll settings"
        slider._canvas.event_generate("<Button-1>", x=20, y=8)
        pump(app, .1)
        assert slider.get() != value_before, "slider click stopped working"
        clicked = slider.get()
        slider._canvas.event_generate("<B1-Motion>", x=150, y=8)
        pump(app, .1)
        assert slider.get() != clicked, "slider drag stopped working"
        capture(dialogs[-1], "settings.png")
        for w in dialogs: w.destroy()
        app._open_holiday_dialog()
        pump(app, .3)
        for w in list(app.winfo_children()):
            if isinstance(w, ctk.CTkToplevel): w.destroy()
        app._open_data_tools()
        pump(app, .3)
        for w in list(app.winfo_children()):
            if isinstance(w, ctk.CTkToplevel): w.destroy()
        ctk.set_widget_scaling(1.2)
        pump(app, 1.1)
        app.geometry("800x560+20+20")
        pump(app, .5)
        assert app.memo_panel.grid_info()["row"] == 0, "editor moved below calendar"
        for widget in (app.title_entry, app.time_entry, app.submit_btn):
            assert widget.winfo_rooty() >= app.winfo_rooty(), "editor above viewport"
            assert widget.winfo_rooty()+widget.winfo_height() <= app.status.winfo_rooty(), "editor requires scrolling"
            assert widget.winfo_rootx() >= app.winfo_rootx(), "editor outside left edge"
        assert app.submit_btn.winfo_rootx()+app.submit_btn.winfo_width() <= app.winfo_rootx()+app.winfo_width(), "large text clipped form"
        pump(app, .2)
        capture(app, "small-window.png")
        buttons = dict(app._day_buttons)
        for day in list(buttons)[5:10]:
            if day.month == app.view_month:
                app._select_day(day)
                for same_day in set(buttons) & set(app._day_buttons):
                    assert buttons[same_day] is app._day_buttons[same_day], "calendar buttons rebuilt"
        # Pooled cards must act on the currently displayed memo, not the prior day.
        app._select_day(date.today())
        app.update_idletasks()
        card = app._memo_rows[0]
        card._buttons[1].invoke()
        assert app.editing_id == card._memo["id"], "pooled edit button targets stale memo"
        edited = card._memo
        original_day = date.fromisoformat(edited["date"])
        target_day = original_day + timedelta(days=35)
        edited["done_dates"] = [original_day.isoformat()]
        original_id = edited["id"]
        app.edit_date_entry.delete(0, "end")
        app.edit_date_entry.insert(0, "2026-02-30")
        with patch("wallcal.ui.messagebox.showwarning") as warning:
            app._submit_memo()
            warning.assert_called_once()
        assert edited["date"] == original_day.isoformat()
        app.edit_date_entry.delete(0, "end")
        app.edit_date_entry.insert(0, target_day.isoformat())
        app._submit_memo()
        assert edited["id"] == original_id and edited["date"] == target_day.isoformat()
        assert edited["done_dates"] == [target_day.isoformat()]
        assert app.selected == target_day and app.view_month == target_day.month
        saved = storage.load()
        assert next(m for m in saved["memos"] if m["id"] == original_id)["date"] == target_day.isoformat()
        edited["repeat"] = "weekly"
        app._select_day(target_day + timedelta(days=7))
        app._start_edit(edited)
        assert app.edit_date_entry.cget("state") == "disabled"
        app._submit_memo()
        assert edited["date"] == target_day.isoformat(), "editing changed repeat anchor"
        app._cancel_edit()
        from wallcal.themes import image_palette, theme_from_settings
        from PIL import Image
        source=out/"palette-source.jpg"
        Image.new("RGB",(600,300),(130,92,158)).save(source)
        profile=dict(image_palette(source),mode="dark",name="暮紫",background=str(source.resolve()))
        app.store["settings"]["custom_themes"]={"custom_test":profile}
        app.title_entry.insert(0,"未提交的内容")
        app._on_theme("图片 · 暮紫")
        pump(app,.3)
        assert app.title_entry.get()=="未提交的内容", "theme change lost draft"
        assert app.title_entry.cget("fg_color")==app.theme.ui_input
        assert app.time_entry.cget("fg_color")==app.theme.ui_input
        capture(app,"image-theme-window.png")
        app._open_image_theme()
        pump(app,.3)
        for w in list(app.winfo_children()):
            if isinstance(w,ctk.CTkToplevel):
                capture(w,"image-theme-editor.png")
                w.destroy()
        app._on_theme("护眼")
        assert app.store["settings"]["background"]==""
        assert not callback_errors, callback_errors
        print("GUI smoke passed: startup, work area, next day, stale render cancellation, rapid edits, all dialogs")
    finally:
        app.quit_app()
