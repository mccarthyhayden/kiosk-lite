"""Sway IPC helpers. Command replies are not written into the run report."""

from __future__ import annotations

import json
import os
import subprocess
import time


class SwayError(RuntimeError):
    pass


def ensure_socket() -> None:
    if os.environ.get("SWAYSOCK"):
        return
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not runtime:
        return
    for name in os.listdir(runtime):
        if name.startswith("sway-ipc.") and name.endswith(".sock"):
            os.environ["SWAYSOCK"] = os.path.join(runtime, name)
            return


def swaymsg(command: str) -> str:
    result = subprocess.run(
        ["swaymsg", "--raw", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SwayError(detail or f"swaymsg failed: {command.split()[0]}")
    return result.stdout


def sway_type(message_type: str) -> object:
    result = subprocess.run(
        ["swaymsg", "--raw", "-t", message_type],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SwayError(result.stderr.strip() or message_type)
    return json.loads(result.stdout)


def app_windows(tree: dict | None = None) -> list[dict]:
    if tree is None:
        tree = sway_type("get_tree")
    found: list[dict] = []

    def walk(node: dict) -> None:
        if node.get("app_id") and node.get("pid"):
            found.append(node)
        for child in list(node.get("nodes") or []) + list(node.get("floating_nodes") or []):
            walk(child)

    walk(tree)
    return found


def active_output() -> dict | None:
    outputs = sway_type("get_outputs")
    for output in outputs:
        if output.get("active"):
            return output
    return None


def wait_for_output(timeout: float = 90) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        output = active_output()
        if output is not None:
            return output
        time.sleep(1)
    raise SwayError("no active display output")


def set_mode(output_name: str, mode: str) -> bool:
    output = None
    for item in sway_type("get_outputs"):
        if item.get("name") == output_name:
            output = item
            break
    if output is None:
        return False
    modes = output.get("modes") or []
    wanted = mode.split("@", 1)[0]
    if not any(str(item.get("width")) + "x" + str(item.get("height")) == wanted for item in modes):
        return False
    swaymsg(f'output "{output_name}" mode {mode}')
    deadline = time.time() + 15
    width = int(wanted.split("x", 1)[0])
    while time.time() < deadline:
        current = active_output()
        rect = (current or {}).get("rect") or {}
        if rect.get("width") == width:
            return True
        time.sleep(0.5)
    return False


def wait_for_new_window(previous_ids: set[int], timeout: float = 180) -> dict:
    """Wait until one new application container exists.

    Every Odoo pane shares one host, so the app id cannot tell them apart.
    The caller starts one Chromium at a time and passes the ids that already
    existed.
    """
    deadline = time.time() + timeout
    stable: list[dict] = []
    stable_since = 0.0
    while time.time() < deadline:
        current = [item for item in app_windows() if item["id"] not in previous_ids]
        if len(current) == 1:
            return current[0]
        if len(current) > 1:
            newest = max(current, key=lambda item: item["id"])
            if not stable or stable[0]["id"] != newest["id"]:
                stable = [newest]
                stable_since = time.time()
            elif time.time() - stable_since > 2:
                return newest
        else:
            stable = []
        time.sleep(0.5)
    raise SwayError("a Chromium window did not appear")


def place(con_id: int, mark: str, x: int, y: int, width: int, height: int) -> None:
    swaymsg(f'[con_id={con_id}] mark --replace {mark}')
    swaymsg(
        f'[con_mark="{mark}"] fullscreen disable, floating enable, border none, '
        f"resize set {width} {height}, move absolute position {x} {y}"
    )


def window_by_mark(mark: str) -> dict | None:
    for window in app_windows():
        if mark in (window.get("marks") or []):
            return window
    return None
