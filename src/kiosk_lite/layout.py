"""Place the panes in config/kiosk.yaml and sign in only on the login page."""

from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import time
from dataclasses import dataclass

from kiosk_lite.browser import (
    chromium_command,
    close_chromium,
    close_port,
    copy_profile,
    find_browser,
    port_is_closed,
    start_chromium,
    wait_for_port,
)
from kiosk_lite.cdp import Cdp, CdpError
from kiosk_lite.config import Layout, Login, load_layout, load_login, login_file_is_private
from kiosk_lite.login import is_login_url, login_stage, page_url, submit_login
from kiosk_lite.sway import (
    SwayError,
    app_windows,
    ensure_socket,
    place,
    set_mode,
    wait_for_new_window,
    wait_for_output,
    window_by_mark,
)

STATE_DIR = os.path.expanduser("~/.local/state/kiosk-lite")
DATA_DIR = os.path.expanduser("~/.local/share/kiosk-lite")
REPORT_PATH = os.path.join(STATE_DIR, "last-run.txt")
LOG_PATH = os.path.join(STATE_DIR, "chromium.log")
SESSION_PROFILE = os.path.join(DATA_DIR, "profiles", "_session")


@dataclass
class RunningPane:
    pane_id: str
    port: int
    con_id: int
    app_id: str
    pid: int
    rect: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Place the kiosk panes from a YAML file.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--place-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        layout = load_layout(args.config)
    except ImportError:
        print("python3-yaml is not installed", flush=True)
        return 1
    os.makedirs(STATE_DIR, exist_ok=True)
    if args.place_only:
        return place_existing(layout)
    return run(layout)


def place_existing(layout: Layout) -> int:
    ensure_socket()
    errors = []
    for pane in layout.panes:
        mark = f"kiosk-{pane.id}"
        window = window_by_mark(mark)
        if window is None:
            errors.append(f"{pane.id} has no mark {mark}")
            continue
        place(window["id"], mark, pane.x, pane.y, pane.width, pane.height)
    if errors:
        _note("\n".join(errors))
        return 1
    return 0


def run(layout: Layout) -> int:
    lock = _acquire_lock()
    if lock is None:
        _note("kiosk-lite is already running")
        return 1
    try:
        ensure_socket()
        if not os.environ.get("SWAYSOCK"):
            _write_report("FAIL Sway is not running\n")
            return 1
        output = wait_for_output()
        mode_set = set_mode(output["name"], layout.mode)
        output = wait_for_output()
        login = _read_login(layout)
        binary = find_browser()
        _note_log(f"\n--- {datetime.datetime.now().isoformat(timespec='seconds')} ---\n")
        seeded = _seed_session(layout, login, binary)
        running = _launch_panes(layout, binary)
        _write_report(_report(output, mode_set, binary, login, seeded, running))
        _watch(layout, login, running, binary)
        return 0
    except (SwayError, OSError, RuntimeError, ValueError) as exc:
        _write_report(f"FAIL {exc}\n")
        _note(str(exc))
        return 1
    finally:
        os.rmdir(lock)


def _read_login(layout: Layout) -> Login | None:
    if not layout.password_file:
        _note("no password file configured; login will not be submitted")
        return None
    if not os.path.isfile(layout.password_file):
        _note("password file is missing; login will not be submitted")
        return None
    if not login_file_is_private(layout.password_file):
        _note(f"password file should be mode 0600: {layout.password_file}")
    return load_login(layout.password_file)


def _seed_session(layout: Layout, login: Login | None, binary: str) -> str:
    """Open one window, sign in if Odoo asks, then copy that profile to each pane.

    The copy happens only after Chromium has exited. A missing password file
    still leaves the layout able to start.
    """
    os.makedirs(SESSION_PROFILE, exist_ok=True)
    port = 9222
    before = {window["id"] for window in app_windows()}
    proc = start_chromium(
        chromium_command(binary, SESSION_PROFILE, layout.panes[0].url, port),
        LOG_PATH,
    )
    status = "not-run"
    try:
        if not wait_for_port(port):
            raise RuntimeError("Chromium debugging port did not open")
        wait_for_new_window(before)
        status = _login_if_needed(port, login)
    finally:
        close_chromium(port, proc)
    if not port_is_closed(port, timeout=10):
        raise RuntimeError("session Chromium did not exit")
    return status


def _login_if_needed(port: int, login: Login | None) -> str:
    deadline = time.time() + 60
    while time.time() < deadline:
        stage = ""
        status = ""
        try:
            cdp = Cdp(port)
            cdp.connect_page()
            try:
                href = page_url(cdp)
                if not href or href.startswith(("about:", "chrome:")):
                    stage = ""
                elif not is_login_url(href):
                    return "session-accepted"
                else:
                    stage = login_stage(cdp)
                    if stage == "challenge":
                        _note("Odoo is showing a second factor. Finish it from the TV.")
                        return "login-challenge"
                    if stage != "password":
                        stage = ""
                    elif login is None:
                        _note("Odoo is showing the login page and no password file is available")
                        return "login-required"
                    else:
                        status = submit_login(cdp, login)
            finally:
                cdp.close()
        except (CdpError, OSError):
            time.sleep(1)
            continue
        if not stage:
            time.sleep(1)
            continue
        if status not in {"clicked", "submitted"}:
            _note(f"Odoo login form was not submitted ({status})")
            return "login-failed"
        return _wait_until_left_login(port)
    _note("Odoo page did not settle")
    return "login-unknown"


def _wait_until_left_login(port: int) -> str:
    deadline = time.time() + 45
    while time.time() < deadline:
        time.sleep(1)
        try:
            cdp = Cdp(port)
            cdp.connect_page()
            try:
                href = page_url(cdp)
                stage = login_stage(cdp) if is_login_url(href) else ""
            finally:
                cdp.close()
        except (CdpError, OSError):
            continue
        if not href or href.startswith(("about:", "chrome:")):
            continue
        if not is_login_url(href):
            _note("Odoo login submitted")
            return "login-submitted"
        if stage == "challenge":
            _note("Odoo is showing a second factor. Finish it from the TV.")
            return "login-challenge"
    _note("Odoo stayed on the login page. If a second factor is showing, finish it from the TV.")
    return "login-challenge"


def _launch_panes(layout: Layout, binary: str) -> list[RunningPane]:
    running: list[RunningPane] = []
    for index, pane in enumerate(layout.panes):
        profile = os.path.join(DATA_DIR, "profiles", pane.id)
        if os.path.isdir(SESSION_PROFILE):
            copy_profile(SESSION_PROFILE, profile)
        else:
            os.makedirs(profile, exist_ok=True)
        port = 9223 + index
        before = {window["id"] for window in app_windows()}
        start_chromium(chromium_command(binary, profile, pane.url, port), LOG_PATH)
        if not wait_for_port(port, timeout=60):
            raise RuntimeError(f"{pane.id} debugging port did not open")
        window = wait_for_new_window(before)
        mark = f"kiosk-{pane.id}"
        place(window["id"], mark, pane.x, pane.y, pane.width, pane.height)
        placed = window_by_mark(mark) or window
        rect = placed.get("rect") or {}
        running.append(
            RunningPane(
                pane_id=pane.id,
                port=port,
                con_id=int(placed["id"]),
                app_id=str(placed.get("app_id") or ""),
                pid=int(placed.get("pid") or 0),
                rect=f"{rect.get('x', pane.x)},{rect.get('y', pane.y)} {rect.get('width', pane.width)}x{rect.get('height', pane.height)}",
            )
        )
    return running


def _watch(layout: Layout, login: Login | None, running: list[RunningPane], binary: str) -> None:
    """Stay up so a later session expiry can be signed in again.

    One pane submits the form. After Chromium exits, that profile is copied
    to the others and the layout is started again, so the four panes keep
    one Odoo session. A second-factor page is left alone.
    """
    quiet_until = 0.0
    while True:
        time.sleep(30)
        if time.time() < quiet_until:
            continue
        current = login
        if current is None and layout.password_file and os.path.isfile(layout.password_file):
            try:
                current = load_login(layout.password_file)
                login = current
            except ValueError as exc:
                _note(str(exc))
        if current is None:
            continue
        target = _pane_on_password_form(running)
        if target is None:
            continue
        try:
            cdp = Cdp(target.port)
            cdp.connect_page()
            try:
                status = submit_login(cdp, current)
            finally:
                cdp.close()
        except (CdpError, OSError):
            quiet_until = time.time() + 300
            continue
        if status not in {"clicked", "submitted"}:
            _note(f"Odoo login form was not submitted ({status})")
            quiet_until = time.time() + 300
            continue
        if _wait_until_left_login(target.port) != "login-submitted":
            quiet_until = time.time() + 300
            continue
        _append_report(f"login_resubmit pane={target.pane_id} time={_now()}\n")
        _note(f"Odoo login submitted for {target.pane_id}")
        try:
            running = _refresh_session(layout, binary, target, running)
        except (SwayError, OSError, RuntimeError) as exc:
            _note(str(exc))
            quiet_until = time.time() + 300


def _pane_on_password_form(running: list[RunningPane]) -> RunningPane | None:
    for pane in running:
        try:
            cdp = Cdp(pane.port)
            cdp.connect_page()
            try:
                if is_login_url(page_url(cdp)) and login_stage(cdp) == "password":
                    return pane
            finally:
                cdp.close()
        except (CdpError, OSError):
            continue
    return None


def _refresh_session(layout: Layout, binary: str, source: RunningPane, running: list[RunningPane]) -> list[RunningPane]:
    """Close every pane, then copy the signed-in profile before starting again."""
    for pane in running:
        close_port(pane.port)
    for pane in running:
        if not port_is_closed(pane.port):
            raise RuntimeError(f"{pane.pane_id} did not exit before the profile copy")
    copy_profile(os.path.join(DATA_DIR, "profiles", source.pane_id), SESSION_PROFILE)
    return _launch_panes(layout, binary)


def _report(output: dict, mode_set: bool, binary: str, login: Login | None, seeded: str, running: list[RunningPane]) -> str:
    rect = output.get("rect") or {}
    mode = output.get("current_mode") or {}
    mode_text = f"{mode.get('width')}x{mode.get('height')}"
    if mode.get("refresh"):
        mode_text += f"@{mode.get('refresh')}"
    pids = [pane.pid for pane in running]
    lines = [
        f"output={output.get('name')} mode={mode_text} requested_mode_set={'yes' if mode_set else 'no'}",
        f"output_rect={rect.get('x', 0)},{rect.get('y', 0)} {rect.get('width')}x{rect.get('height')}",
        f"time={_now()}",
        f"model={_model()}",
        f"browser={os.path.basename(binary)}",
        f"profile_model=separate",
        f"same_pid={'yes' if len(set(pids)) == 1 and pids else 'no'}",
        f"login_file={'present' if login is not None else 'missing'}",
        f"session={seeded}",
    ]
    for pane in running:
        lines.append(
            f"{pane.pane_id} con_id={pane.con_id} app_id={pane.app_id} pid={pane.pid} rect={pane.rect}"
        )
    lines.append("memory:")
    lines.append(_memory())
    lines.append(f"report={REPORT_PATH}")
    lines.append("")
    return "\n".join(lines)


def _memory() -> str:
    try:
        result = subprocess.run(["free", "-h"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return "free unavailable"
    return (result.stdout or result.stderr or "free unavailable").rstrip()


def _model() -> str:
    path = "/proc/device-tree/model"
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().replace("\x00", "").strip()
    except OSError:
        return "unknown"


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _write_report(text: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(text)


def _append_report(text: str) -> None:
    with open(REPORT_PATH, "a", encoding="utf-8") as handle:
        handle.write(text)


def _note(text: str) -> None:
    print(text, flush=True)
    _note_log(text + "\n")


def _note_log(text: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(text)


def _acquire_lock() -> str | None:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    path = os.path.join(runtime, "kiosk-lite.lock")
    try:
        os.mkdir(path)
    except FileExistsError:
        return None
    return path
