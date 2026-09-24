"""Per-monitor wallpaper API. Never use a null monitor ID when setting wallpaper."""
from __future__ import annotations
import ctypes as c
from ctypes import wintypes as w
from contextlib import contextmanager
import json
import shutil
import uuid
from pathlib import Path
from .paths import DATA_DIR

STATE = DATA_DIR / "monitor_wallpapers.json"

class Desktop:
    def __init__(self):
        import comtypes
        self.com = comtypes
        comtypes.CoInitialize()
        self.ptr = c.c_void_p()
        clsid = comtypes.GUID("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")
        iid = comtypes.GUID("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")
        hr = c.windll.ole32.CoCreateInstance(c.byref(clsid), None, 23, c.byref(iid), c.byref(self.ptr))
        if hr < 0:
            comtypes.CoUninitialize()
            raise OSError("无法访问 Windows 分屏壁纸接口")
        self.table = c.cast(self.ptr, c.POINTER(c.POINTER(c.c_void_p))).contents
    def call(self, slot, types, *args):
        hr = c.WINFUNCTYPE(c.c_long, c.c_void_p, *types)(self.table[slot])(self.ptr, *args)
        if hr < 0: raise OSError(f"Windows 分屏壁纸操作失败：{hr & 0xffffffff:08x}")
        return hr
    def string(self, slot, types, *args):
        value = c.c_void_p()
        self.call(slot, [*types, c.POINTER(c.c_void_p)], *args, c.byref(value))
        try: return c.wstring_at(value) if value.value else ""
        finally:
            c.windll.ole32.CoTaskMemFree.argtypes = [c.c_void_p]
            c.windll.ole32.CoTaskMemFree(value)
    def screens(self):
        count = w.UINT()
        self.call(6, [c.POINTER(w.UINT)], c.byref(count))
        result = []
        errors = []
        for i in range(count.value):
            try:
                key = self.string(5, [w.UINT], i)
                rect = w.RECT()
                hr = self.call(7, [w.LPCWSTR, c.POINTER(w.RECT)], key, c.byref(rect))
                if hr == 1 or rect.right <= rect.left or rect.bottom <= rect.top:
                    continue
                bounds = (rect.left, rect.top, rect.right, rect.bottom)
                result.append({"id": key, "rect": bounds, "primary": rect.left == 0 and rect.top == 0})
            except OSError as exc:
                # Windows can retain unavailable display records. One bad record
                # must not hide other attached, usable monitors.
                errors.append(str(exc))
        if not result and errors:
            raise OSError("无法读取可用屏幕，请重新连接屏幕或稍后重试。" + errors[0])
        return result
    def get(self, key): return self.string(4, [w.LPCWSTR], key)
    def set(self, key, path):
        if not key: raise ValueError("必须指定屏幕")
        self.call(3, [w.LPCWSTR, w.LPCWSTR], key, path)
    def close(self):
        c.WINFUNCTYPE(c.c_ulong, c.c_void_p)(self.table[2])(self.ptr)
        self.com.CoUninitialize()

@contextmanager
def desktop():
    obj = Desktop()
    try: yield obj
    finally: obj.close()

def screens():
    with desktop() as api: return api.screens()

def resolve(key="", available=None):
    available = screens() if available is None else available
    for item in available:
        if (key and item["id"] == key) or (not key and item["primary"]): return item
    raise OSError("选定屏幕未连接或暂时无法读取，已暂停壁纸更新。请连接屏幕或在显示设置中重新选择。")

def local_icons(rect, icons):
    x,y,r,b = rect
    return [(a-x,c-y,d-x,e-y) for a,c,d,e in icons if d>x and e>y and a<r and c<b]

def _load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"originals": {}, "active": "", "applied": {}}

def _save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temp=STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8")
    temp.replace(STATE)

def _backup(path):
    if not path: return ""
    source=Path(path)
    if source.parent.resolve() == DATA_DIR.resolve() and source.name.startswith(("desktop_", "wallpaper")):
        from .winwallpaper import ORIGINAL
        if ORIGINAL.exists():
            record=json.loads(ORIGINAL.read_text(encoding="utf-8"))
            path=record.get("backup") or record.get("Wallpaper", "")
            source=Path(path)
        else: return None
    if not path: return ""
    if not source.is_file(): raise OSError("原壁纸无法备份，已取消更换；请先选择恢复图片。")
    target=DATA_DIR / ("original_monitor_"+uuid.uuid4().hex+source.suffix)
    shutil.copy2(source,target)
    return str(target)

def _restore(api,state,key):
    path=state["originals"].get(key)
    if path is None: raise OSError("此屏幕未留有原壁纸，请先选择原壁纸 / 补设恢复图片。")
    if path and not Path(path).is_file(): raise OSError("此屏幕的原壁纸备份已丢失")
    api.set(key,path)

def apply(path,key=""):
    with desktop() as api:
        attached=api.screens()
        target=resolve(key,attached)["id"]
        position=w.UINT()
        api.call(11,[c.POINTER(w.UINT)],c.byref(position))
        if position.value in (1,5):
            raise OSError("Windows 壁纸当前为平铺或跨区，请在个性化中改为填充后使用指定屏幕。")
        state=_load()
        if target not in state["originals"]:
            state["originals"][target]=_backup(api.get(target))
            _save(state)
        old=state.get("active")
        if old and old != target:
            if not any(m["id"]==old for m in attached):
                raise OSError("原日历屏幕已断开，请先重连并停止更新恢复壁纸，再切换屏幕。")
            if api.get(old)==state.get("applied",{}).get(old): _restore(api,state,old)
            state["active"]=""
            _save(state)
        api.set(target,str(path))
        state["active"]=target
        state.setdefault("applied",{})[target]=str(path)
        _save(state)

def restore():
    state=_load()
    key=state.get("active")
    if not key: return False
    with desktop() as api:
        resolve(key,api.screens())
        _restore(api,state,key)
    state["active"]=""
    _save(state)
    return True

def choose_backup(source,key=""):
    target=resolve(key)["id"]
    state=_load()
    state["originals"][target]=_backup(str(source))
    _save(state)
