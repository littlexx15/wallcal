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
