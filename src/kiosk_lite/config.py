"""Load the pane layout and the Pi-local Odoo login file."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Pane:
    id: str
    url: str
    x: int
    y: int
    width: int
    height: int
    hide_navbar: bool = True
    refresh_seconds: int = 300


@dataclass(frozen=True)
class Layout:
    mode: str
    password_file: str
    panes: tuple[Pane, ...]


class Login:
    """Odoo web login. The password is never included in repr or logs."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password

    def __repr__(self) -> str:
        return f"Login(username={self.username!r}, password=<redacted>)"


def load_layout(path: str) -> Layout:
    import yaml

    with open(path, encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a mapping")
    display = raw.get("display") or {}
    login = raw.get("login") or {}
    mode = str(display.get("mode") or "1920x1080")
    refresh_seconds = _refresh_seconds(display.get("refresh_seconds", 300), "display")
    password_file = os.path.expanduser(str(login.get("password_file") or ""))
    panes_raw = raw.get("panes") or []
    if not panes_raw:
        raise ValueError(f"{path} has no panes")
    panes: list[Pane] = []
    seen: set[str] = set()
    for item in panes_raw:
        hide_navbar = item.get("hide_navbar", True)
        if not isinstance(hide_navbar, bool):
            raise ValueError(f"{item.get('id', 'pane')} hide_navbar must be true or false")
        pane_refresh = item.get("refresh_seconds", refresh_seconds)
        pane = Pane(
            id=str(item["id"]),
            url=str(item["url"]),
            x=int(item["x"]),
            y=int(item["y"]),
            width=int(item["width"]),
            height=int(item["height"]),
            hide_navbar=hide_navbar,
            refresh_seconds=_refresh_seconds(pane_refresh, str(item.get("id", "pane"))),
        )
        if pane.id in seen:
            raise ValueError(f"duplicate pane id {pane.id}")
        if not pane.url.startswith("https://"):
            raise ValueError(f"{pane.id} url must start with https://")
        if pane.width < 1 or pane.height < 1:
            raise ValueError(f"{pane.id} has an empty rectangle")
        seen.add(pane.id)
        panes.append(pane)
    return Layout(mode=mode, password_file=password_file, panes=tuple(panes))


def _refresh_seconds(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} refresh_seconds must be a whole number of seconds, or 0 to disable")
    return value


def load_login(path: str) -> Login | None:
    """Read username and password. Missing file means the session stands alone."""
    if not path or not os.path.isfile(path):
        return None
    username = ""
    password = ""
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key == "username":
                username = value
            elif key == "password":
                password = value
    if not username or not password:
        raise ValueError(f"{path} needs username= and password= lines")
    return Login(username, password)


def login_file_is_private(path: str) -> bool:
    if os.name != "posix" or not os.path.isfile(path):
        return True
    return (os.stat(path).st_mode & 0o077) == 0
