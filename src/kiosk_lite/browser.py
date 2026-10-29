"""Start one Chromium profile per pane and copy a signed-in profile."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time

from kiosk_lite.cdp import Cdp, CdpError

_SKIP_NAMES = {
    "SingletonLock",
    "SingletonSocket",
    "SingletonCookie",
    "lockfile",
}
_SKIP_DIRS = {
    "Cache",
    "Code Cache",
    "GPUCache",
    "DawnGraphiteCache",
    "DawnWebGPUCache",
    "GrShaderCache",
    "ShaderCache",
}


def find_browser() -> str:
    for name in ("chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("chromium is not installed")


def chromium_command(binary: str, profile: str, url: str, port: int) -> list[str]:
    origin = f"http://127.0.0.1:{port}"
    return [
        binary,
        "--ozone-platform=wayland",
        f"--user-data-dir={profile}",
        f"--app={url}",
        "--password-store=basic",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-translate",
        "--disable-features=TranslateUI",
        "--disable-infobars",
        "--noerrdialogs",
        "--autoplay-policy=no-user-gesture-required",
        "--check-for-update-interval=31536000",
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-allow-origins={origin}",
    ]


def start_chromium(command: list[str], log_path: str) -> subprocess.Popen:
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "ab")
    try:
        return subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log.close()


def wait_for_port(port: int, timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 1):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def close_port(port: int) -> None:
    try:
        cdp = Cdp(port)
        cdp.connect_browser()
        try:
            cdp.call("Browser.close", timeout=5)
        finally:
            cdp.close()
    except (CdpError, OSError):
        return


def port_is_closed(port: int, timeout: float = 20) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), 1):
                time.sleep(0.4)
        except OSError:
            return True
    return False


def close_chromium(port: int, proc: subprocess.Popen, timeout: float = 20) -> None:
    try:
        cdp = Cdp(port)
        cdp.connect_browser()
        try:
            cdp.call("Browser.close", timeout=5)
        finally:
            cdp.close()
    except (CdpError, OSError):
        proc.terminate()
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def copy_profile(source: str, destination: str) -> None:
    """Copy a profile that Chromium is not using. Lock files are left behind."""
    if os.path.isdir(destination):
        shutil.rmtree(destination)

    def ignore(directory: str, names: list[str]) -> set[str]:
        del directory
        return {
            name
            for name in names
            if name in _SKIP_NAMES or name in _SKIP_DIRS or name.startswith("Singleton")
        }

    shutil.copytree(source, destination, ignore=ignore)
    os.chmod(destination, 0o700)
