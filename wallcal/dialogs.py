from __future__ import annotations

import calendar
import io
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, colorchooser

import customtkinter as ctk
from PIL import Image

from . import dataio
from . import sync as cloudsync
from .holidays import upsert_personal
from .paths import DATA_DIR
from .storage import save
from .themes import get_theme, readable_theme, theme_from_settings, image_palette
from .winwallpaper import restore_original, work_area


class DragOnlySlider(ctk.CTkSlider):
    """Leave wheel events to the surrounding scrollable settings panel."""
    def _mouse_scroll_event(self, event):
        # CTkScrollableFrame excludes sliders from its global wheel handler.
        # Forward once using its canvas as the event target, preserving delta.
        from copy import copy
        parent = self.master
        while parent is not None:
            if isinstance(parent, ctk.CTkScrollableFrame):
                forwarded = copy(event)
                forwarded.widget = parent._parent_canvas
                parent._mouse_wheel_all(forwarded)
                return "break"
            parent = getattr(parent, "master", None)
        return None


class SettingsDialogs:
    def _dialog(self, title: str):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.configure(fg_color=self.theme.ui_surface)
        x0, y0, x1, y1 = work_area()
        scale = dialog._get_window_scaling()
        w, h = min(620, int((x1-x0-40)/scale)), min(690, int((y1-y0-70)/scale))
        dialog.geometry(f"{w}x{h}+{x0+24}+{y0+24}")
        dialog.transient(self)
        dialog.after(100, dialog.lift)
        frame = ctk.CTkScrollableFrame(dialog,fg_color=self.theme.ui_card)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        return dialog, frame

    def _open_display_settings(self) -> None:
        dialog, frame = self._dialog("显示设置")
        settings = self.store["settings"]
        def label(text):
            ctk.CTkLabel(frame, text=text, anchor="w").pack(fill="x", pady=(12, 4))
        label("日历布局 · 自动读取图标位置，无需计算比例")
        layouts = {"自动避让图标（推荐）": "auto", "全屏": "full"}
        layout = ctk.CTkOptionMenu(frame, values=list(layouts), width=200)
        layout.set(next((k for k, v in layouts.items() if v == settings.get("layout", "auto")), "自动避让图标（推荐）"))
        layout.pack(anchor="w")
        ctk.CTkLabel(frame, text="每 2 秒检查图标位置，稳定约 1 秒后调整；暂不支持第三方桌面整理面板。", wraplength=480).pack(anchor="w", pady=6)
        ctk.CTkButton(frame, text="从图片创建 / 编辑整套主题…", command=self._open_image_theme).pack(anchor="w", pady=8)
        label("壁纸字号 · 长事项自动换行，超出格子容量会提示")
        fonts = {"标准": 1.0, "大": 1.2, "特大": 1.4}
        font_menu = ctk.CTkOptionMenu(frame, values=list(fonts))
        font_menu.set(next((k for k, v in fonts.items() if v == settings.get("font_scale", 1.0)), "标准"))
        font_menu.pack(anchor="w")
        label("软件界面缩放")
        scales = {"标准": 1.0, "放大 10%": 1.1, "放大 20%": 1.2}
        ui_menu = ctk.CTkOptionMenu(frame, values=list(scales))
        ui_menu.set(next((k for k, v in scales.items() if v == settings.get("ui_scale", 1.0)), "标准"))
        ui_menu.pack(anchor="w")
        contrast = ctk.BooleanVar(value=settings.get("high_contrast", True))
        ctk.CTkCheckBox(frame, text="增强文字对比度", variable=contrast).pack(anchor="w", pady=14)
        background = [settings.get("background", "")]
        label("背景图片 · 自动保存副本，移动原图也不影响")
        background_label = ctk.CTkLabel(frame, text="已使用自定义图片" if background[0] else "使用主题背景")
        background_label.pack(anchor="w")
        def choose():
            source = filedialog.askopenfilename(parent=dialog, filetypes=[("图片", "*.jpg *.jpeg *.png *.webp *.bmp")])
            if source:
                try:
                    background[0] = dataio.import_background(Path(source))
                    background_label.configure(text=Path(source).name)
                    schedule_preview()
                except Exception as exc:
                    messagebox.showerror("图片无法使用", str(exc), parent=dialog)
        def clear():
            background[0] = ""
            background_label.configure(text="使用主题背景")
            schedule_preview()
        ctk.CTkButton(frame, text="选择背景图片", command=choose).pack(anchor="w", pady=4)
        ctk.CTkButton(frame, text="使用主题背景", command=clear).pack(anchor="w", pady=4)
        label("背景透出程度 · 点击或拖动调整，滚轮仅滚动页面")
        visibility_label = ctk.CTkLabel(frame, text="")
        visibility_label.pack(anchor="w")
        preview_job = [None]
        def update_preview():
            preview_job[0] = None
            from .wallpaper import render_wallpaper_image
            state = deepcopy(self.store)
            state["settings"].update(background=background[0],
                background_visibility=round(visibility.get()), layout="full",
                font_scale=fonts[font_menu.get()], high_contrast=contrast.get())
            try:
                picture = render_wallpaper_image(state, size=(1280, 720))
                picture.thumbnail((460, 259))
                preview.configure(image=ctk.CTkImage(light_image=picture, dark_image=picture,
                    size=picture.size), text="")
            except Exception:
                preview.configure(image=None, text="背景预览不可用，请重新选择图片")
        def schedule_preview(value=None):
            amount = round(visibility.get())
            visibility_label.configure(text=f"透出 {amount}% · 日历底板不透明度 {100-amount}%" if background[0] else "选择背景图片后生效")
            if preview_job[0] is not None:
                dialog.after_cancel(preview_job[0])
            preview_job[0] = dialog.after(180, update_preview)
        visibility = DragOnlySlider(frame, from_=0, to=60, number_of_steps=60, command=schedule_preview)
        visibility.set(max(0, min(60, float(settings.get("background_visibility", 35)))))
        visibility.pack(fill="x", pady=6)
        preview = ctk.CTkLabel(frame, text="正在生成预览…")
        preview.pack(pady=8)
        ctk.CTkLabel(frame, text="效果预览采用完整布局；保存后应用到桌面，输入窗口保持清晰。", wraplength=460).pack(anchor="w")
        def cancel_preview(event):
            if event.widget is dialog and preview_job[0] is not None:
                dialog.after_cancel(preview_job[0])
                preview_job[0] = None
        dialog.bind("<Destroy>", cancel_preview, add="+")
        font_menu.configure(command=schedule_preview)
        schedule_preview()
        def apply():
            self.store["settings"].update(layout=layouts[layout.get()], font_scale=fonts[font_menu.get()],
                ui_scale=scales[ui_menu.get()], high_contrast=contrast.get(), background=background[0],
                background_visibility=round(visibility.get()), wallpaper_enabled=True)
            self._persist()
            self._refresh_appearance()
            self.refresh_wallpaper_async("正在应用显示设置…")
            dialog.destroy()
        ctk.CTkButton(frame, text="保存并应用到桌面", command=apply).pack(fill="x", pady=(18, 8))
        def select_original():
            source = filedialog.askopenfilename(parent=dialog, title="选择停止使用壁历后恢复的原壁纸",
                filetypes=[("图片", "*.jpg *.jpeg *.png *.webp *.bmp")])
            if not source:
                return
            if not messagebox.askyesno("设置恢复图片", "将保存此图片的副本，作为以后恢复的原壁纸。已有的恢复设置将被替换，是否继续？", parent=dialog):
                return
            try:
                from .winwallpaper import choose_original
                choose_original(Path(source))
                messagebox.showinfo("已保存", "原壁纸副本已保存。点击“停止更新并恢复原壁纸”即可恢复。", parent=dialog)
            except Exception as exc:
                messagebox.showerror("备份失败", str(exc), parent=dialog)
        ctk.CTkButton(frame, text="选择原壁纸 / 补设恢复图片…", command=select_original).pack(fill="x", pady=8)
        ctk.CTkButton(frame, text="停止更新并恢复原壁纸", command=lambda: self._stop_wallpaper(dialog)).pack(fill="x", pady=8)
        ctk.CTkLabel(frame, text="桌面日历是一张壁纸；编辑事项请打开壁历。", wraplength=460).pack(anchor="w", pady=8)

    def _refresh_appearance(self) -> None:
        settings = self.store["settings"]
        self.theme = theme_from_settings(settings)
        ctk.set_appearance_mode(self.theme.ui_mode)
        ctk.set_widget_scaling(float(settings.get("ui_scale", 1.0)))
        self.theme_menu.set(self.theme.label)
        self.holiday_var.set(settings.get("show_holidays", True))
        self._apply_chrome()
        self.redraw()
        self.after(100, self._fit_window)

    def _stop_wallpaper(self, parent=None) -> None:
        self.store["settings"]["wallpaper_enabled"] = False
        self._render_generation += 1
        self._render_request = None
        save(self.store)
        try:
            restore_original()
            self._set_status("已停止自动更新并恢复原壁纸；点“刷新壁纸”可重新启用。")
        except Exception as exc:
            messagebox.showinfo("已停止壁纸更新", str(exc), parent=parent or self)
            self._set_status("已停止更新。可在 Windows 个性化设置中选择背景。")

    def _open_holiday_dialog(self) -> None:
        dialog, frame = self._dialog("标记个人休假 / 上班")
        ctk.CTkLabel(frame, text="个人安排优先于法定安排；清除后恢复法定显示。", wraplength=480).pack(pady=8)
        starts, ends = self._date_fields(frame, self.selected, self.selected)
        kinds = {"年假": "leave", "休息 / 调休": "rest", "上班": "work"}
        menu = ctk.CTkOptionMenu(frame, values=list(kinds))
        menu.pack(anchor="w", pady=12)
        name = ctk.CTkEntry(frame, placeholder_text="自定义名称（可留空，例如：补休）", width=340)
        name.pack(anchor="w", pady=8)
        def apply():
            try:
                start, end = date.fromisoformat(starts.get().strip()), date.fromisoformat(ends.get().strip())
                if end < start or (end-start).days > 366:
                    raise ValueError("请选择不超过一年的有效范围")
                personal = list(self.store.get("personal_holidays", []))
                day = start
                while day <= end:
                    personal = upsert_personal(personal, day, kind=kinds[menu.get()], name=name.get().strip()[:30] or menu.get())
                    day += timedelta(days=1)
                self.store["personal_holidays"] = personal
                self._persist()
                self.redraw()
                self.refresh_wallpaper_async("个人安排已保存")
                dialog.destroy()
            except (ValueError, OSError) as exc:
                messagebox.showerror("无法保存", str(exc), parent=dialog)
        ctk.CTkButton(frame, text="保存标记", command=apply).pack(fill="x", pady=20)

    def _date_fields(self, frame, start, end):
        fields = []
        for text, value in (("开始日期（YYYY-MM-DD）", start), ("结束日期（含当天）", end)):
            ctk.CTkLabel(frame, text=text).pack(anchor="w", pady=(12, 3))
            entry = ctk.CTkEntry(frame, width=200)
            entry.insert(0, value.isoformat())
            entry.pack(anchor="w")
            fields.append(entry)
        return fields

    def _open_data_tools(self) -> None:
        dialog, frame = self._dialog("导出事项 / 备份恢复")
        ctk.CTkLabel(frame, text="CSV 留档：按日期展开重复事项，保留完成状态。", wraplength=480).pack(anchor="w", pady=8)
        start = date(self.view_year, self.view_month, 1)
        end = date(self.view_year, self.view_month, calendar.monthrange(self.view_year, self.view_month)[1])
        starts, ends = self._date_fields(frame, start, end)
        def export():
            try:
                start, end = date.fromisoformat(starts.get().strip()), date.fromisoformat(ends.get().strip())
                if end < start or (end-start).days > 3660:
                    raise ValueError("请选择不超过十年的有效日期范围")
                path = filedialog.asksaveasfilename(parent=dialog, defaultextension=".csv", initialfile=f"壁历事项-{start}-{end}.csv", filetypes=[("CSV", "*.csv")])
                if path:
                    count = dataio.export_csv(self.store, Path(path), start, end)
                    messagebox.showinfo("导出完成", f"已导出 {count} 条事项。", parent=dialog)
            except Exception as exc:
                messagebox.showerror("导出失败", str(exc), parent=dialog)
        def backup():
            path = filedialog.asksaveasfilename(parent=dialog, defaultextension=".json", initialfile=f"壁历备份-{date.today()}.json", filetypes=[("壁历备份", "*.json")])
            if path:
                try:
                    dataio.write_backup(self.store, Path(path))
                    messagebox.showinfo("备份完成", "已保存事项、个人假期、设置和背景图片。备份不包含登录令牌。", parent=dialog)
                except Exception as exc:
                    messagebox.showerror("备份失败", str(exc), parent=dialog)
        ctk.CTkButton(frame, text="导出所选日期的 CSV", command=export).pack(fill="x", pady=16)
        ctk.CTkLabel(frame, text="JSON 备份包含全部日期的数据，与上面的导出范围无关。", wraplength=480).pack(anchor="w", pady=8)
        ctk.CTkButton(frame, text="备份全部数据", command=backup).pack(fill="x", pady=8)
        ctk.CTkButton(frame, text="从备份恢复…", command=lambda: self._restore_backup(dialog)).pack(fill="x", pady=8)

    def _restore_backup(self, parent) -> None:
        if self._sync_busy:
            messagebox.showinfo("请稍后", "正在云同步，请完成后再恢复备份。", parent=parent)
            return
        path = filedialog.askopenfilename(parent=parent, filetypes=[("壁历备份", "*.json")])
        if not path:
            return
        try:
            restored, background = dataio.read_backup(Path(path))
            if not messagebox.askyesno("恢复备份", "这会替换本机全部事项和假期。恢复前会自动备份当前数据，并暂停自动云同步。是否继续？", parent=parent):
                return
            backup_path = DATA_DIR / f"before_restore_{datetime.now():%Y%m%d_%H%M%S_%f}.json"
            dataio.write_backup(self.store, backup_path)
            # Keep device-specific preferences local.
            for key in ("autostart", "window", "wallpaper_enabled"):
                if key in self.store["settings"]:
                    restored["settings"][key] = self.store["settings"][key]
            restored["settings"]["first_run"] = False
            import uuid
            for media_key, image_bytes in background.items():
                target = DATA_DIR / f"background_{uuid.uuid4().hex}.jpg"
                with Image.open(io.BytesIO(image_bytes)) as image:
                    image.convert("RGB").save(target, "JPEG", quality=95)
                if media_key == "active":
                    restored["settings"]["background"] = str(target)
                else:
                    restored["settings"]["custom_themes"][media_key]["background"] = str(target)
            auth = cloudsync.load_auth()
            if auth:
                auth["autosync"] = False
                cloudsync.save_auth(auth)
            restored["settings"]["sync_paused"] = True
            save(restored)
            self.store = restored
            self._revision += 1
            self._want_sync_push = self._want_sync_pull = False
            self._cancel_edit()
            self._refresh_appearance()
            self.refresh_wallpaper_async()
            messagebox.showinfo("恢复完成", f"恢复前的数据已备份到：\n{backup_path}\n\n云同步已暂停。确认本机数据后，可在云同步窗口手动同步。", parent=parent)
        except Exception as exc:
            messagebox.showerror("恢复失败", str(exc), parent=parent)

    def _open_image_theme(self) -> None:
        import uuid
        from PIL import ImageOps
        settings = self.store["settings"]
        current_key = settings.get("theme")
        current = settings.get("custom_themes", {}).get(current_key)
        if current:
            profile = deepcopy(current)
            key = current_key
        else:
            source = filedialog.askopenfilename(parent=self, title="选择主题背景图片", filetypes=[("图片", "*.jpg *.jpeg *.png *.webp *.bmp")])
            if not source: return
            try:
                background = dataio.import_background(Path(source))
                profile = dict(image_palette(background), background=background, mode="light", name=Path(source).stem[:18])
                key = "custom_"+uuid.uuid4().hex[:10]
            except Exception as exc:
                messagebox.showerror("图片无法使用", str(exc), parent=self)
                return
        dialog, frame = self._dialog("图片主题 · 桌面和窗口一起换色")
        ctk.CTkLabel(frame, text="从图片提取配色，自动搭配清晰文字和卡片底色。", wraplength=480).pack(anchor="w", pady=8)
        thumbnail = ctk.CTkLabel(frame, text="")
        thumbnail.pack(pady=8)
        name = ctk.CTkEntry(frame, width=320, placeholder_text="主题名称")
        name.insert(0, profile["name"])
        name.pack(anchor="w", pady=6)
        mode = ctk.CTkOptionMenu(frame, values=["浅色 · 清爽", "深色 · 沉静"], width=180)
        mode.set("深色 · 沉静" if profile["mode"] == "dark" else "浅色 · 清爽")
        mode.pack(anchor="w", pady=6)
        preview = ctk.CTkFrame(frame, height=140)
        preview.pack(fill="x", pady=12)
        sample_title = ctk.CTkLabel(preview, text="今天 · 写下一件重要的事", font=ctk.CTkFont(size=18,weight="bold"))
        sample_title.pack(anchor="w", padx=16, pady=(14,6))
        sample_entry = ctk.CTkEntry(preview, placeholder_text="例如：午后散步十分钟")
        sample_entry.pack(fill="x",padx=16,pady=6)
        sample_button = ctk.CTkButton(preview,text="添加备忘")
        sample_button.pack(anchor="w",padx=16,pady=(6,14))
        def update_preview(*_):
            profile["mode"] = "dark" if mode.get().startswith("深色") else "light"
            temp = dict(settings, theme=key, custom_themes={key:profile})
            theme = theme_from_settings(temp)
            preview.configure(fg_color=theme.ui_card)
            sample_title.configure(text_color=theme.ui_text)
            sample_entry.configure(fg_color=theme.ui_input,text_color=theme.ui_text,placeholder_text_color=theme.ui_muted,border_color=theme.ui_border)
            sample_button.configure(fg_color=theme.ui_accent,hover_color=theme.ui_hover,text_color="#%02x%02x%02x" % theme.on_accent)
        mode.configure(command=update_preview)
        def show_image():
            with Image.open(profile["background"]) as image:
                small = ImageOps.fit(image.convert("RGB"),(440,180))
            dialog._theme_image = ctk.CTkImage(small,size=(440,180))
            thumbnail.configure(image=dialog._theme_image)
        def choose_image():
            source = filedialog.askopenfilename(parent=dialog,filetypes=[("图片","*.jpg *.jpeg *.png *.webp *.bmp")])
            if not source: return
            try:
                profile["background"] = dataio.import_background(Path(source))
                profile.update(image_palette(profile["background"]))
                show_image(); update_preview()
            except Exception as exc:
                messagebox.showerror("图片无法使用",str(exc),parent=dialog)
        def tweak_color():
            _, value = colorchooser.askcolor(profile["accent"],parent=dialog,title="微调强调色")
            if value:
                profile["accent"] = value
                update_preview()
        ctk.CTkButton(frame,text="更换图片并重新取色",command=choose_image).pack(anchor="w",pady=4)
        ctk.CTkButton(frame,text="微调强调色",command=tweak_color).pack(anchor="w",pady=4)
        def apply_theme():
            title = name.get().strip()[:24]
            if not title:
                messagebox.showinfo("主题名称","给这个主题起个名字吧。",parent=dialog); return
            profiles = self.store["settings"].setdefault("custom_themes",{})
            if any(k != key and item.get("name") == title for k,item in profiles.items()):
                messagebox.showinfo("名称已存在","请换一个名称。",parent=dialog); return
            profile["name"] = title
            profiles[key] = deepcopy(profile)
            self.store["settings"].update(theme=key,background=profile["background"])
            self._persist()
            self._refresh_appearance()
            self.refresh_wallpaper_async("正在应用图片主题…")
            dialog.destroy()
        ctk.CTkButton(frame,text="保存并应用到桌面和窗口",command=apply_theme).pack(fill="x",pady=16)
        try:
            show_image(); update_preview()
        except Exception as exc:
            messagebox.showerror("无法打开图片",str(exc),parent=dialog)
            dialog.destroy()
