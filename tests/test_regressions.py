from __future__ import annotations
import csv
import json
import os
import tempfile
import unittest
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

TEST_ROOT = tempfile.TemporaryDirectory(prefix="wallcal-tests-")
os.environ["WALLCAL_DATA_DIR"] = TEST_ROOT.name
from PIL import Image
from wallcal import dataio, storage, winwallpaper
from wallcal.holidays import mark_on, upsert_personal
from wallcal.timeinput import parse_time
from wallcal.wallpaper import render_wallpaper


class RegressionTests(unittest.TestCase):
    def test_photo_transparency_preview_has_no_side_effects(self):
        from wallcal.wallpaper import render_wallpaper_image
        from wallcal.themes import theme_from_settings
        state = self.state()
        path = Path(TEST_ROOT.name) / "solid.png"
        Image.new("RGB", (1280, 720), (20, 60, 100)).save(path)
        state["settings"].update(background=str(path), layout="full")
        before = set(Path(TEST_ROOT.name).iterdir())
        with patch("wallcal.wallpaper.set_wallpaper") as apply:
            picture = render_wallpaper_image(state, size=(1280, 720))
            apply.assert_not_called()
        self.assertEqual(before, set(Path(TEST_ROOT.name).iterdir()))
        # Blank panel padding: white/tinted surface blends with photo at 65%.
        card = theme_from_settings(state["settings"]).card[:3]
        for actual, surface, bg in zip(picture.getpixel((640, 114)), card, (20, 60, 100)):
            self.assertAlmostEqual(actual, surface * .65 + bg * .35, delta=2)
        state["settings"]["background_visibility"] = 0
        opaque = render_wallpaper_image(state, size=(1280, 720))
        self.assertEqual(opaque.getpixel((640, 114)), card)

    def test_icon_changes_wait_for_stability(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from wallcal.ui import WallCalWindow
        app = SimpleNamespace(store={"settings": {"layout": "auto"}},
            _icon_signature=None, _icon_candidate=None, _render_request=None,
            refresh_wallpaper_async=Mock(), _set_status=Mock())
        accept = lambda signature, error=None: WallCalWindow._accept_icon_probe(app, signature, error)
        a, b, c = ((0, 0, 50, 50),), ((100, 0, 150, 50),), ((200, 0, 250, 50),)
        self.assertEqual(accept(a), 2000)
        for _ in range(5): self.assertEqual(accept(a), 2000)
        self.assertEqual(accept(b), 1000)
        self.assertEqual(accept(c), 1000)
        app.refresh_wallpaper_async.assert_not_called()
        self.assertEqual(accept(c), 2000)
        app.refresh_wallpaper_async.assert_called_once()
        accept(c)
        accept(b)
        accept(c)  # Returned to original position: no refresh.
        app.refresh_wallpaper_async.assert_called_once()
        accept(b)
        accept(None, "temporary error")
        self.assertEqual(accept(b), 1000)
        app.store["settings"]["wallpaper_enabled"] = False
        accept(b)
        app.refresh_wallpaper_async.assert_called_once()

    def test_wrapped_titles_and_theme_choices(self):
        from PIL import ImageDraw
        from wallcal.wallpaper import wrap_text
        from wallcal.fonts import font
        from wallcal.themes import theme_choices
        draw = ImageDraw.Draw(Image.new("RGB", (400, 300)))
        fnt = font(20)
        title = "整理本周工作计划并核对事项"
        lines = wrap_text(draw, title, fnt, 160, 2)
        self.assertEqual("".join(lines), title)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(draw.textlength(line, font=fnt) <= 160 for line in lines))
        self.assertTrue(wrap_text(draw, title * 4, fnt, 160, 2)[-1].endswith("…"))
        self.assertEqual(set(theme_choices({}).values()), {"eye", "ink"})

    def test_time_input(self):
        for value in ("9:30", "9：30", " ０９：３０ ", "09 : 30"):
            self.assertEqual(parse_time(value), "09:30")
        for value in ("24:00", "12:60", "09:3", "9.30", "-1:30", "text"):
            self.assertIsNone(parse_time(value))
        self.assertEqual(parse_time(" "), "")

    def test_personal_override_and_clear(self):
        day = date(2026, 10, 1)
        self.assertEqual(mark_on(day).kind, "off")
        personal = upsert_personal([], day, kind="work", name="值班")
        self.assertEqual(mark_on(day, personal).kind, "work")
        self.assertFalse(mark_on(day, personal).official)
        self.assertEqual(mark_on(day, personal, include_official=False).name, "值班")
        self.assertIsNone(mark_on(day, include_official=False))
        self.assertEqual(mark_on(date(2026, 10, 10)).kind, "work")

    def state(self):
        state = deepcopy(storage.DEFAULT_STATE)
        state["memos"] = [storage.new_memo(title="=事项", day=date(2026, 9, 20), repeat="daily")]
        state["memos"][0]["done_dates"] = ["2026-09-21"]
        state["personal_holidays"] = [{"date":"2026-09-22", "kind":"rest", "name":"补休"}]
        return state

    def test_csv_recurrence_completion_and_formula(self):
        path = Path(TEST_ROOT.name) / "events.csv"
        count = dataio.export_csv(self.state(), path, date(2026,9,20), date(2026,9,22))
        self.assertEqual(count, 3)
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[2][5], "已完成")
        self.assertEqual(rows[1][2], "'=事项")
        self.assertEqual(rows[3][0], "2026-09-22")
        with self.assertRaises(ValueError):
            dataio.export_csv(self.state(), path, date(2026,9,22), date(2026,9,20))

    def test_backup_roundtrip_with_background(self):
        source = Path(TEST_ROOT.name) / "source.png"
        Image.new("RGB", (80, 60), "blue").save(source)
        state = self.state()
        state["settings"]["background"] = dataio.import_background(source)
        state["settings"]["layout"] = "four_fifths"
        source.unlink()
        path = Path(TEST_ROOT.name) / "backup.json"
        dataio.write_backup(state, path)
        restored, background = dataio.read_backup(path)
        self.assertEqual(restored["memos"], state["memos"])
        self.assertEqual(restored["settings"]["layout"], "auto")
        self.assertEqual(restored["personal_holidays"], state["personal_holidays"])
        self.assertTrue(background)
        self.assertNotIn("token", path.read_text(encoding="utf-8"))
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["state"]["memos"][0]["date"] = "not-a-date"
        path.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(ValueError):
            dataio.read_backup(path)

    def test_corrupt_store_is_not_overwritten(self):
        path = Path(TEST_ROOT.name) / "broken.json"
        path.write_text("{broken", encoding="utf-8")
        with patch.object(storage, "STORE_PATH", path), self.assertRaises(RuntimeError):
            storage.load()
        self.assertEqual(path.read_text(), "{broken")

    def test_render_layouts_fonts_six_week_month(self):
        state = self.state()
        with patch("wallcal.wallpaper.set_wallpaper") as apply:
            for layout in ("full", "right", "compact", "four_fifths"):
                for scale in (1.0, 1.2, 1.4):
                    state["settings"].update(layout=layout, font_scale=scale)
                    path = render_wallpaper(state, now=datetime(2026,5,16), size=(1280,720))
                    with Image.open(path) as image:
                        self.assertEqual(image.size, (1280,720))
                        image.verify()
            apply.assert_not_called()

    def test_auto_layout_avoids_icons(self):
        from wallcal.desktop_layout import free_rectangle
        icons = [(0,0,390,1000),(1700,0,1900,220)]
        bounds = free_rectangle((30,30,1890,1000),icons)
        for x0,y0,x1,y1 in icons:
            self.assertFalse(bounds[0] < x1+16 and bounds[2] > x0-16 and bounds[1] < y1+16 and bounds[3] > y0-16)
        self.assertGreater(bounds[2]-bounds[0],1000)
        self.assertLess(free_rectangle((30,30,1890,1000),[])[0],50)
        with self.assertRaises(RuntimeError):
            free_rectangle((0,0,800,600),[(0,0,800,600)])

    def test_picture_theme_contrast_and_backup(self):
        from wallcal.themes import theme_from_settings,image_palette,contrast_ratio
        source = Path(TEST_ROOT.name)/"theme.jpg"
        Image.new("RGB",(100,100),(165,102,74)).save(source)
        profile = dict(image_palette(source),name="测试图片",mode="light",background=str(source))
        state = self.state()
        state["settings"].update(theme="custom_test",custom_themes={"custom_test":profile})
        for mode in ("light","dark"):
            for accent in ("#FFFFFF","#000000","#B8B8B8","#FAEBCD"):
                profile.update(mode=mode,accent=accent)
                theme = theme_from_settings(state["settings"])
                self.assertGreaterEqual(contrast_ratio(theme.text,theme.card[:3]),4.5)
                self.assertGreaterEqual(contrast_ratio(theme.accent,theme.card[:3]),4.5)
                self.assertGreaterEqual(contrast_ratio(theme.accent,theme.on_accent),4.5)
        target = Path(TEST_ROOT.name)/"picture-backup.json"
        dataio.write_backup(state,target)
        restored, media = dataio.read_backup(target)
        self.assertEqual(restored["settings"]["theme"],"custom_test")
        self.assertIn("custom_test",media)
        self.assertEqual(restored["settings"]["custom_themes"]["custom_test"]["background"],"")

    def test_invalid_wallpaper_never_applied(self):
        path = Path(TEST_ROOT.name) / "bad.jpg"
        path.write_bytes(b"not an image")
        with patch.object(winwallpaper, "_apply") as apply, self.assertRaises(Exception):
            winwallpaper.set_wallpaper(path)
        apply.assert_not_called()

    def test_missing_original_blocks_apply_and_manual_recovery(self):
        folder = Path(TEST_ROOT.name)
        original = folder / "manual-original.json"
        source = folder / "manual-source.png"
        Image.new("RGB", (30, 30), "blue").save(source)
        values = {"Wallpaper": str(folder / "missing.png"), "WallpaperStyle": "6", "TileWallpaper": "0"}
        with patch.object(winwallpaper, "ORIGINAL", original), patch.object(winwallpaper, "_desktop_values", return_value=values):
            with patch.object(winwallpaper, "_apply") as apply:
                with self.assertRaises(FileNotFoundError):
                    winwallpaper.set_wallpaper(source)
                apply.assert_not_called()
            self.assertFalse(original.exists())
            winwallpaper.choose_original(source)
            source.unlink()
            with patch.object(winwallpaper, "_apply") as apply:
                winwallpaper.restore_original()
                self.assertTrue(Path(apply.call_args.args[0]).is_file())

    def test_original_saved_once_and_restored(self):
        source = Path(TEST_ROOT.name) / "user_background.png"
        Image.new("RGB", (30,30), "red").save(source)
        original = Path(TEST_ROOT.name) / "original-test.json"
        values = {"Wallpaper": str(source), "WallpaperStyle": "6", "TileWallpaper": "0"}
        with patch.object(winwallpaper, "ORIGINAL", original), patch.object(winwallpaper, "_desktop_values", return_value=values):
            winwallpaper.capture_original()
            source.unlink()
            with patch.object(winwallpaper, "_desktop_values", side_effect=AssertionError("already saved")):
                winwallpaper.capture_original()
            with patch.object(winwallpaper, "_apply") as apply:
                winwallpaper.restore_original()
                args = apply.call_args.args
                self.assertTrue(Path(args[0]).is_file())
                self.assertEqual(args[1:], ("6", "0"))

if __name__ == "__main__":
    unittest.main()
