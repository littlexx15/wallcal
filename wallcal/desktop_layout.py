"""Read desktop icon bounds through MSAA; never move icons or inspect their labels."""
from __future__ import annotations
import ctypes as c
import threading
import time
from ctypes import wintypes as w

_lock = threading.Lock()
_cache = None
_cached_at = 0.0


def icon_rectangles(force=False):
    global _cache, _cached_at
    with _lock:
        if not force and _cache is not None and time.monotonic()-_cached_at < 10:
            return list(_cache)
        import comtypes
        from comtypes.automation import VARIANT
        comtypes.CoInitialize()
        try:
            user = c.windll.user32
            user.FindWindowExW.argtypes = [w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR]
            user.FindWindowExW.restype = w.HWND
            handles = []
            callback = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
            @callback
            def visit(hwnd, _):
                view = user.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
                if view:
                    icons = user.FindWindowExW(view, 0, "SysListView32", None)
                    if icons:
                        handles.append(icons)
                return True
            user.EnumWindows(visit, 0)
            if not handles:
                raise RuntimeError("暂时无法读取桌面图标，请稍后刷新，或在显示设置中选择手动布局")
            rectangles = []
            for hwnd in handles:
                if not user.IsWindowVisible(hwnd):
                    continue
                pointer = c.c_void_p()
                iid = comtypes.GUID("{618736E0-3C3D-11CF-810C-00AA00389B71}")
                get_object = c.windll.oleacc.AccessibleObjectFromWindow
                get_object.argtypes = [w.HWND, w.DWORD, c.POINTER(comtypes.GUID), c.POINTER(c.c_void_p)]
                get_object.restype = c.c_long
                if get_object(hwnd, 0xFFFFFFFC, c.byref(iid), c.byref(pointer)) != 0:
                    raise RuntimeError("无法读取桌面图标位置，已保留当前壁纸")
                table = c.cast(pointer, c.POINTER(c.POINTER(c.c_void_p))).contents
                children = None
                try:
                    count = c.c_long()
                    result = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.POINTER(c.c_long))(table[8])(pointer, c.byref(count))
                    if result != 0 or count.value > 3000:
                        raise RuntimeError("无法完整读取桌面图标，已保留当前壁纸")
                    locate = c.WINFUNCTYPE(c.c_long, c.c_void_p, c.POINTER(c.c_long), c.POINTER(c.c_long), c.POINTER(c.c_long), c.POINTER(c.c_long), VARIANT)(table[22])
                    children = (VARIANT * count.value)()
                    obtained = c.c_long()
                    enumerate_children = c.windll.oleacc.AccessibleChildren
                    enumerate_children.argtypes = [c.c_void_p,c.c_long,c.c_long,c.POINTER(VARIANT),c.POINTER(c.c_long)]
                    enumerate_children.restype = c.c_long
                    if enumerate_children(pointer,0,count.value,children,c.byref(obtained)) < 0:
                        raise RuntimeError("无法完整读取桌面图标")
                    for entry in children[:obtained.value]:
                        if entry.vt != 3:  # VT_I4: standard list-view icon child IDs.
                            continue
                        child = entry.value
                        x, y, width, height = (c.c_long() for _ in range(4))
                        result = locate(pointer, c.byref(x), c.byref(y), c.byref(width), c.byref(height), VARIANT(child))
                        if result != 0:
                            raise RuntimeError("桌面图标暂时不可读取，请稍后刷新")
                        if width.value > 0 and height.value > 0:
                            rectangles.append((x.value, y.value, x.value+width.value, y.value+height.value))
                finally:
                    if children is not None:
                        for entry in children:
                            c.windll.oleaut32.VariantClear(c.byref(entry))
                    c.WINFUNCTYPE(c.c_ulong, c.c_void_p)(table[2])(pointer)
            _cache, _cached_at = tuple(sorted(rectangles)), time.monotonic()
            return list(_cache)
        finally:
            comtypes.CoUninitialize()


def free_rectangle(area, icons, padding=16, minimum=(560, 360)):
    """Largest icon-free rectangle on a conservative grid, in physical pixels."""
    left, top, right, bottom = area
    step = max(8, round(min(right-left, bottom-top)/60))
    cols, rows = (right-left)//step, (bottom-top)//step
    blocked = set()
    for x0,y0,x1,y1 in icons:
        if x1+padding <= left or x0-padding >= right or y1+padding <= top or y0-padding >= bottom:
            continue
        c0=max(0,(x0-padding-left)//step); c1=min(cols-1,(x1+padding-left)//step)
        r0=max(0,(y0-padding-top)//step); r1=min(rows-1,(y1+padding-top)//step)
        for row in range(r0,r1+1):
            for col in range(c0,c1+1): blocked.add((row,col))
    histogram = [0]*cols
    best = None
    best_area = 0
    for row in range(rows):
        histogram = [0 if (row,col) in blocked else histogram[col]+1 for col in range(cols)]
        stack = []
        for col in range(cols+1):
            height = histogram[col] if col < cols else 0
            start = col
            while stack and stack[-1][1] > height:
                start, h = stack.pop()
                width = (col-start)*step
                pixel_h = h*step
                if width >= minimum[0] and pixel_h >= minimum[1] and width*pixel_h > best_area:
                    best_area = width*pixel_h
                    best = (left+start*step, top+(row+1-h)*step, left+col*step, top+(row+1)*step)
            if not stack or stack[-1][1] < height:
                stack.append((start,height))
    if best is None:
        raise RuntimeError("桌面没有足够的连续空白区域；请整理图标或改用手动布局。未移动任何图标。")
    return best
