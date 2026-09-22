from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from copy import deepcopy
from datetime import datetime
from typing import Any

from .paths import DATA_DIR

AUTH_PATH = DATA_DIR / "sync_auth.json"
GIST_NAME = "wallcal.json"
GIST_DESC = "WallCal 壁历同步数据（请勿删除）"
TOKEN_HELP = "https://github.com/settings/tokens/new?scopes=gist&description=WallCal"
API = "https://api.github.com"


def now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_auth() -> dict[str, Any]:
    if not AUTH_PATH.exists():
        return {}
    try:
        raw = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_auth(auth: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = AUTH_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(auth, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(AUTH_PATH)


def clear_auth() -> None:
    try:
        if AUTH_PATH.exists():
            AUTH_PATH.unlink()
    except OSError:
        pass


def logged_in() -> bool:
    return bool(load_auth().get("token"))


def autosync_enabled() -> bool:
    return bool(load_auth().get("autosync", True)) and logged_in()


def detect_gh_token() -> str:
    env = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if env:
        return env
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            return (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def _request(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> Any:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "WallCal",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None if body is None else json.dumps(body).encode("utf-8")
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(_friendly_http(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"网络打不开 GitHub：{exc.reason}") from exc


def _friendly_http(code: int, detail: str) -> str:
    if code in (401, 403):
        return "令牌无效或没有 gist 权限，请重新登录。"
    if code == 404:
        return "没找到同步仓库，将重新创建一个。"
    return f"GitHub 返回 {code}：{detail[:180]}"


def fetch_user(token: str) -> dict[str, Any]:
    return _request("GET", f"{API}/user", token)


def login(token: str) -> dict[str, Any]:
    token = token.strip()
    if not token:
        raise RuntimeError("请先填入 GitHub 令牌。")
    user = fetch_user(token)
    login_name = str(user.get("login") or "")
    if not login_name:
        raise RuntimeError("登录失败，请检查令牌。")
    auth = load_auth()
    auth.update(
        {
            "token": token,
            "login": login_name,
            "autosync": True if auth.get("autosync") is None else bool(auth.get("autosync")),
        }
    )
    save_auth(auth)
    return auth


def payload_from_state(state: dict[str, Any]) -> dict[str, Any]:
    settings = dict(state.get("settings") or {})
    settings.pop("autostart", None)
    settings.pop("first_run", None)
    payload = {
        "app": "wallcal",
        "updated_at": now_stamp(),
        "settings": {
            "theme": settings.get("theme", "eye"),
            "show_holidays": bool(settings.get("show_holidays", True)),
        },
        "memos": list(state.get("memos") or []),
        "personal_holidays": list(state.get("personal_holidays") or []),
        "deleted_ids": list(state.get("deleted_ids") or []),
    }

    if str(settings.get("theme", "")).startswith("custom_"):
        payload["settings"].pop("theme", None)
    return payload


def merge_state(local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(local)
    deleted = set(str(x) for x in (local.get("deleted_ids") or []))
    deleted.update(str(x) for x in (remote.get("deleted_ids") or []))

    by_id: dict[str, dict[str, Any]] = {}
    for memo in list(local.get("memos") or []) + list(remote.get("memos") or []):
        mid = str(memo.get("id") or "")
        if not mid or mid in deleted:
            continue
        prev = by_id.get(mid)
        if prev is None or _stamp(memo) >= _stamp(prev):
            winner = deepcopy(memo)
            if prev is not None:
                winner["done_dates"] = sorted(
                    set(prev.get("done_dates") or []) | set(memo.get("done_dates") or [])
                )
            by_id[mid] = winner
        elif prev is not None:
            prev["done_dates"] = sorted(
                set(prev.get("done_dates") or []) | set(memo.get("done_dates") or [])
            )

    holidays: dict[str, dict[str, Any]] = {}
    for item in list(remote.get("personal_holidays") or []) + list(
        local.get("personal_holidays") or []
    ):
        key = str(item.get("date") or "")[:10]
        if key:
            holidays[key] = item

    local_stamp = str(local.get("updated_at") or "")
    remote_stamp = str(remote.get("updated_at") or "")
    local_settings = dict(local.get("settings") or {})
    remote_settings = dict(remote.get("settings") or {})
    if remote_stamp > local_stamp:
        if "theme" in remote_settings and not str(local_settings.get("theme", "")).startswith("custom_"):
            local_settings["theme"] = remote_settings["theme"]
        if "show_holidays" in remote_settings:
            local_settings["show_holidays"] = remote_settings["show_holidays"]

    merged["memos"] = list(by_id.values())
    merged["personal_holidays"] = list(holidays.values())
    merged["deleted_ids"] = sorted(deleted)
    merged["settings"] = local_settings
    merged["updated_at"] = now_stamp()
    return merged


def _stamp(item: dict[str, Any]) -> str:
    return str(item.get("updated_at") or item.get("created_at") or "")


def pull_and_merge(local: dict[str, Any]) -> tuple[dict[str, Any], str]:
    auth = load_auth()
    token = str(auth.get("token") or "")
    if not token:
        raise RuntimeError("还没有登录。")
    gist_id, remote = _load_remote(token, str(auth.get("gist_id") or ""))
    auth["gist_id"] = gist_id
    if remote is None:
        save_auth(auth)
        push_state(local)
        return local, "云端是空的，已把本机数据上传"
    merged = merge_state(local, remote)
    save_auth(auth)
    _write_gist(token, gist_id, merged)
    _touch_sync()
    return merged, "已从云端同步"


def push_state(local: dict[str, Any]) -> str:
    auth = load_auth()
    token = str(auth.get("token") or "")
    if not token:
        raise RuntimeError("还没有登录。")
    gist_id = str(auth.get("gist_id") or "")
    if not gist_id:
        gist_id, _ = _load_remote(token, "")
    if not gist_id:
        gist_id = _create_gist(token, local)
    else:
        _write_gist(token, gist_id, local)
    auth["gist_id"] = gist_id
    save_auth(auth)
    _touch_sync()
    return "已同步到云端"


def _touch_sync() -> None:
    auth = load_auth()
    auth["last_sync"] = now_stamp()
    save_auth(auth)


def _load_remote(token: str, gist_id: str) -> tuple[str, dict[str, Any] | None]:
    if gist_id:
        try:
            data = _request("GET", f"{API}/gists/{gist_id}", token)
            parsed = _parse_gist(data)
            if parsed is not None:
                return gist_id, parsed
        except RuntimeError:
            gist_id = ""
    found_id, parsed = _find_gist(token)
    return found_id, parsed


def _find_gist(token: str) -> tuple[str, dict[str, Any] | None]:
    pages = _request("GET", f"{API}/gists?per_page=100", token)
    if not isinstance(pages, list):
        return "", None
    for gist in pages:
        if gist.get("description") == GIST_DESC or GIST_NAME in (gist.get("files") or {}):
            gid = str(gist.get("id") or "")
            if not gid:
                continue
            full = _request("GET", f"{API}/gists/{gid}", token)
            parsed = _parse_gist(full)
            return gid, parsed
    return "", None


def _parse_gist(data: dict[str, Any]) -> dict[str, Any] | None:
    files = data.get("files") or {}
    file = files.get(GIST_NAME) or {}
    content = file.get("content")
    if not content:
        return None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _create_gist(token: str, state: dict[str, Any]) -> str:
    body = {
        "description": GIST_DESC,
        "public": False,
        "files": {GIST_NAME: {"content": json.dumps(payload_from_state(state), ensure_ascii=False, indent=2)}},
    }
    created = _request("POST", f"{API}/gists", token, body)
    gist_id = str(created.get("id") or "")
    if not gist_id:
        raise RuntimeError("创建云端仓库失败。")
    return gist_id


def _write_gist(token: str, gist_id: str, state: dict[str, Any]) -> None:
    body = {
        "description": GIST_DESC,
        "files": {GIST_NAME: {"content": json.dumps(payload_from_state(state), ensure_ascii=False, indent=2)}},
    }
    _request("PATCH", f"{API}/gists/{gist_id}", token, body)
