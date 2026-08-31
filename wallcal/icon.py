from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .fonts import font
from .paths import ASSETS_DIR, ICON_PATH
from .themes import THEMES


def ensure_icon(path: Path | None = None) -> Path:
    dest = path or ICON_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    image = render_icon(256)
    image.save(dest, "PNG")
    return dest


def load_icon_image(size: int = 64) -> Image.Image:
    ensure_icon()
    image = Image.open(ICON_PATH).convert("RGBA")
    return image.resize((size, size), Image.Resampling.LANCZOS)


def render_icon(size: int = 256) -> Image.Image:
    theme = THEMES["ink"]
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size // 16
    draw.rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=size // 6,
        fill=(14, 22, 40, 255),
    )
    header = pad + size // 7
    draw.rounded_rectangle(
        (pad, pad, size - pad, header + size // 10),
        radius=size // 6,
        fill=theme.accent + (255,),
    )
    draw.rectangle(
        (pad, header, size - pad, header + size // 10),
        fill=theme.accent + (255,),
    )
    ring_y = pad + size // 18
    for cx in (size * 0.34, size * 0.66):
        r = size // 28
        draw.rounded_rectangle(
            (cx - r, ring_y, cx + r, ring_y + size // 9),
            radius=r,
            fill=(28, 22, 10, 255),
        )
    number = "31"
    f = font(int(size * 0.42), bold=True)
    bbox = draw.textbbox((0, 0), number, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - tw) / 2 - bbox[0]
    y = size * 0.42 - bbox[1]
    draw.text((x, y), number, font=f, fill=theme.accent)
    note = (
        size * 0.58,
        size * 0.62,
        size - pad - 4,
        size - pad - 8,
    )
    draw.rounded_rectangle(note, radius=size // 18, fill=(244, 236, 220, 255))
    draw.ellipse(
        (note[0] + 6, note[1] - 8, note[0] + 22, note[1] + 8),
        fill=(232, 197, 107, 255),
    )
    return img


ASSETS_DIR.mkdir(parents=True, exist_ok=True)
