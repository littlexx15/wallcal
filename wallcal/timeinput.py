from __future__ import annotations

import re
import unicodedata


def parse_time(value: str) -> str | None:
    text = unicodedata.normalize("NFKC", value or "").strip()
    if not text:
        return ""
    match = re.fullmatch(r"([0-9]{1,2})\s*:\s*([0-9]{2})", text)
    if match:
        hour, minute = map(int, match.groups())
        if 0 <= hour < 24 and 0 <= minute < 60:
            return f"{hour:02d}:{minute:02d}"
    return None
