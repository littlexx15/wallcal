from __future__ import annotations

from dataclasses import dataclass


def _hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    ui_mode: str
    bg0: tuple[int, int, int]
    bg1: tuple[int, int, int]
    card: tuple[int, int, int, int]
    card_line: tuple[int, int, int, int]
    text: tuple[int, int, int]
    muted: tuple[int, int, int]
    faint: tuple[int, int, int]
    accent: tuple[int, int, int]
    on_accent: tuple[int, int, int]
    weekend: tuple[int, int, int]
    other_month: tuple[int, int, int]
    work: tuple[int, int, int]
    life: tuple[int, int, int]
    important: tuple[int, int, int]
    ui_accent: str
    ui_hover: str
    ui_surface: str
    ui_card: str
    ui_text: str
    ui_muted: str
    ui_border: str
    ui_input: str


THEMES: dict[str, Theme] = {
    "eye": Theme(
        key="eye",
        label="护眼",
        ui_mode="light",
        bg0=(226, 232, 220),
        bg1=(210, 220, 206),
        card=(247, 245, 238, 235),
        card_line=(120, 132, 118, 48),
        text=(48, 54, 46),
        muted=(106, 118, 108),
        faint=(154, 164, 152),
        accent=(90, 128, 98),
        on_accent=(247, 250, 245),
        weekend=(168, 110, 98),
        other_month=(168, 176, 166),
        work=(90, 122, 148),
        life=(90, 128, 98),
        important=(168, 110, 98),
        ui_accent="#5A8062",
        ui_hover="#4A6C52",
        ui_surface="#E6EBE2",
        ui_card="#F7F5EE",
        ui_text="#30362E",
        ui_muted="#6A766C",
        ui_border="#D4D9CE",
        ui_input="#FFFcf6",
    ),
    "paper": Theme(
        key="paper",
        label="宣纸",
        ui_mode="light",
        bg0=(244, 236, 222),
        bg1=(232, 220, 200),
        card=(252, 248, 240, 240),
        card_line=(140, 118, 90, 50),
        text=(56, 46, 34),
        muted=(122, 108, 88),
        faint=(168, 154, 132),
        accent=(143, 92, 64),
        on_accent=(252, 246, 238),
        weekend=(156, 92, 76),
        other_month=(176, 164, 148),
        work=(86, 114, 148),
        life=(96, 124, 92),
        important=(156, 92, 76),
        ui_accent="#8F5C40",
        ui_hover="#744A34",
        ui_surface="#F3EBDD",
        ui_card="#FBF7F0",
        ui_text="#382E22",
        ui_muted="#7A6C58",
        ui_border="#E2D6C4",
        ui_input="#FFFDF8",
    ),
    "ink": Theme(
        key="ink",
        label="墨夜",
        ui_mode="dark",
        bg0=(16, 20, 26),
        bg1=(24, 32, 42),
        card=(28, 36, 48, 220),
        card_line=(180, 196, 210, 36),
        text=(220, 226, 232),
        muted=(140, 152, 164),
        faint=(92, 104, 116),
        accent=(168, 186, 164),
        on_accent=(22, 28, 24),
        weekend=(196, 150, 140),
        other_month=(78, 88, 100),
        work=(130, 164, 196),
        life=(150, 186, 160),
        important=(196, 150, 140),
        ui_accent="#A8BAA4",
        ui_hover="#8A9E88",
        ui_surface="#161C24",
        ui_card="#1E2630",
        ui_text="#DCE2E8",
        ui_muted="#8C98A4",
        ui_border="#2C3642",
        ui_input="#1A222C",
    ),
    "celadon": Theme(
        key="celadon",
        label="青瓷",
        ui_mode="dark",
        bg0=(14, 28, 28),
        bg1=(20, 44, 42),
        card=(18, 40, 38, 220),
        card_line=(160, 200, 190, 40),
        text=(222, 236, 232),
        muted=(132, 164, 158),
        faint=(80, 108, 104),
        accent=(120, 176, 164),
        on_accent=(12, 28, 26),
        weekend=(196, 156, 140),
        other_month=(70, 96, 92),
        work=(118, 164, 196),
        life=(120, 176, 164),
        important=(196, 150, 128),
        ui_accent="#78B0A4",
        ui_hover="#5E968C",
        ui_surface="#122422",
        ui_card="#183230",
        ui_text="#DEECE8",
        ui_muted="#84A49E",
        ui_border="#244440",
        ui_input="#102220",
    ),
}

TAG_KEYS = {
    "life": "生活",
    "work": "工作",
    "important": "重要",
}
TAG_FROM_LABEL = {v: k for k, v in TAG_KEYS.items()}
REPEAT_KEYS = {
    "none": "仅一次",
    "daily": "每天",
    "weekly": "每周",
    "monthly": "每月",
}
REPEAT_FROM_LABEL = {v: k for k, v in REPEAT_KEYS.items()}


def get_theme(key: str) -> Theme:
    if key == "dusk":
        key = "celadon"
    return THEMES.get(key, THEMES["eye"])


def tag_color(theme: Theme, tag: str) -> tuple[int, int, int]:
    return {
        "work": theme.work,
        "life": theme.life,
        "important": theme.important,
    }.get(tag, theme.life)


def tag_hex(theme: Theme, tag: str) -> str:
    return _hex(tag_color(theme, tag))


def readable_theme(theme: Theme, enabled: bool = True) -> Theme:
    if not enabled:
        return theme
    from dataclasses import replace
    dark = theme.ui_mode == "dark"
    return replace(theme,
        muted=(198, 204, 200) if dark else (65, 74, 67),
        faint=(178, 187, 182) if dark else (83, 93, 86),
        ui_muted="#C6CCC8" if dark else "#414A43")


def _rgb(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise ValueError("颜色应为 #RRGGBB 格式")
    return tuple(int(value[i:i+2], 16) for i in (1,3,5))


def _blend(a, b, amount):
    return tuple(round(x*(1-amount)+y*amount) for x,y in zip(a,b))


def contrast_ratio(a, b):
    def lum(color):
        channels = [v/255 for v in color]
        linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return sum(v*w for v,w in zip(linear,(.2126,.7152,.0722)))
    x,y = sorted((lum(a),lum(b)))
    return (y+.05)/(x+.05)


def image_palette(path):
    import colorsys
    from PIL import Image, ImageOps
    with Image.open(path) as image:
        sample = ImageOps.exif_transpose(image).convert("RGB")
        sample.thumbnail((160,160))
        reduced = sample.quantize(colors=12).convert("RGB")
        colors = sorted(reduced.getcolors(256) or [], reverse=True)
    if not colors:
        raise ValueError("无法从图片提取颜色")
    dominant = colors[0][1]
    def score(item):
        count, color = item
        _, light, saturation = colorsys.rgb_to_hls(*(v/255 for v in color))
        return count**.4*(saturation+.15)*(1-abs(light-.5))
    accent = max(colors, key=score)[1]
    return {"surface": _hex(dominant), "accent": _hex(accent)}


def theme_choices(settings):
    choices = {THEMES[key].label: key for key in ("eye", "ink")}
    for key, profile in settings.get("custom_themes", {}).items():
        choices[f"图片 · {profile.get('name', '自定义')}"] = key
    return choices


def theme_from_settings(settings):
    key = settings.get("theme", "eye")
    profile = settings.get("custom_themes", {}).get(key)
    if profile is None:
        return readable_theme(get_theme(key), settings.get("high_contrast", True))
    from dataclasses import replace
    import colorsys
    dark = profile.get("mode") == "dark"
    seed = _rgb(profile.get("surface", "#789080"))
    accent = _rgb(profile.get("accent", "#5A8062"))
    h,l,sat = colorsys.rgb_to_hls(*(v/255 for v in seed))
    base = tuple(round(v*255) for v in colorsys.hls_to_rgb(h, .10 if dark else .94, min(sat,.20)))
    card = _blend(base, (255,255,255), .07 if dark else .65)
    text = (235,240,237) if dark else (30,39,34)
    muted = _blend(text,card,.25)
    # Derive a usable accent even from pale or near-black source images.
    target = (235,245,240) if dark else (16,37,27)
    for _ in range(30):
        if contrast_ratio(accent,card) >= 4.5: break
        accent = _blend(accent,target,.12)
    on_accent = (255,255,255) if contrast_ratio(accent,(255,255,255)) >= contrast_ratio(accent,(15,20,17)) else (15,20,17)
    border = _blend(base,text,.18)
    source = THEMES["ink" if dark else "eye"]
    return replace(source,key=key,label=f"图片 · {profile.get('name','自定义')}", ui_mode="dark" if dark else "light",
        bg0=base,bg1=_blend(base,accent,.12),card=(*card,250),card_line=(*border,160),
        text=text,muted=muted,faint=_blend(text,card,.34),other_month=_blend(text,card,.5),
        accent=accent,on_accent=on_accent,life=accent,
        ui_accent=_hex(accent),ui_hover=_hex(_blend(accent,on_accent,.12)),
        ui_surface=_hex(base),ui_card=_hex(card),ui_text=_hex(text),ui_muted=_hex(muted),
        ui_border=_hex(border),ui_input=_hex(_blend(card,(255,255,255),.04 if dark else .5)))
