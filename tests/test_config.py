import os
import socket
import stat
import tempfile
import unittest

from kiosk_lite.browser import copy_profile
from kiosk_lite.cdp import _recv_text, _send_text
from kiosk_lite.config import Login, load_layout, load_login
from kiosk_lite.layout import RunningPane, _report
from kiosk_lite.login import is_login_url
from kiosk_lite.page import CHROME_SCRIPT, HIDE_NAVBAR_CSS


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG = os.path.join(ROOT, "config", "kiosk.yaml")


class LayoutFileTest(unittest.TestCase):
    def test_four_odoo_panes(self) -> None:
        layout = load_layout(CONFIG)
        self.assertEqual(
            [pane.id for pane in layout.panes],
            ["lead_times", "production_schedule", "meeting_notes", "dashboard"],
        )
        self.assertEqual(
            [(pane.x, pane.y, pane.width, pane.height) for pane in layout.panes],
            [(0, 0, 640, 540), (640, 0, 1280, 540), (0, 540, 640, 540), (640, 540, 1280, 540)],
        )
        for pane in layout.panes:
            self.assertTrue(pane.url.startswith("https://odoo.nxcmfg.com/"))
            self.assertTrue(pane.hide_navbar)
            self.assertEqual(pane.refresh_seconds, 300)
        self.assertEqual(layout.panes[0].refresh_seconds, 300)
        with open(CONFIG, encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("password:", text)
        self.assertNotIn("password=", text)

    def test_refresh_override_and_disable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "kiosk.yaml")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "display:\n"
                    "  refresh_seconds: 120\n"
                    "panes:\n"
                    "  - id: one\n"
                    "    url: https://odoo.nxcmfg.com/web\n"
                    "    x: 0\n"
                    "    y: 0\n"
                    "    width: 10\n"
                    "    height: 10\n"
                    "  - id: two\n"
                    "    url: https://odoo.nxcmfg.com/web\n"
                    "    x: 0\n"
                    "    y: 0\n"
                    "    width: 10\n"
                    "    height: 10\n"
                    "    refresh_seconds: 0\n"
                )
            layout = load_layout(path)
            self.assertEqual(layout.panes[0].refresh_seconds, 120)
            self.assertEqual(layout.panes[1].refresh_seconds, 0)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(
                    "display:\n"
                    "  refresh_seconds: -1\n"
                    "panes:\n"
                    "  - id: one\n"
                    "    url: https://odoo.nxcmfg.com/web\n"
                    "    x: 0\n"
                    "    y: 0\n"
                    "    width: 10\n"
                    "    height: 10\n"
                )
            with self.assertRaises(ValueError):
                load_layout(path)

    def test_login_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "odoo-login")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# local only\nusername=ada\npassword=s3cret=value\n")
            login = load_login(path)
            self.assertIsNotNone(login)
            self.assertEqual(login.username, "ada")
            self.assertEqual(login.password, "s3cret=value")
            self.assertNotIn("s3cret", repr(login))

    def test_missing_login_file(self) -> None:
        self.assertIsNone(load_login(os.path.join(tempfile.gettempdir(), "missing-odoo-login")))

    def test_navbar_css_targets_the_web_client_bar(self) -> None:
        self.assertIn(".o_main_navbar", HIDE_NAVBAR_CSS)
        self.assertIn(".o_navbar", HIDE_NAVBAR_CSS)
        self.assertIn(".o_control_panel", HIDE_NAVBAR_CSS)
        self.assertNotIn("password", CHROME_SCRIPT)
        self.assertIn("kiosk-lite-chrome", CHROME_SCRIPT)

    def test_login_urls(self) -> None:
        self.assertTrue(is_login_url("https://odoo.nxcmfg.com/web/login"))
        self.assertTrue(
            is_login_url("https://odoo.nxcmfg.com/web/login?redirect=https%3A%2F%2Fodoo.nxcmfg.com%2Fweb")
        )
        self.assertFalse(
            is_login_url("https://odoo.nxcmfg.com/web#dashboard_id=25&cids=1&action=1498&menu_id=756")
        )

    def test_profile_copy_skips_locks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "source")
            destination = os.path.join(directory, "dest")
            os.makedirs(os.path.join(source, "Default"))
            for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
                with open(os.path.join(source, name), "w", encoding="utf-8") as handle:
                    handle.write("busy")
            with open(os.path.join(source, "Default", "Cookies"), "w", encoding="utf-8") as handle:
                handle.write("cookie-jar")
            os.makedirs(os.path.join(source, "Default", "Cache"))
            with open(os.path.join(source, "Default", "Cache", "data"), "w", encoding="utf-8") as handle:
                handle.write("cache")
            copy_profile(source, destination)
            self.assertTrue(os.path.isfile(os.path.join(destination, "Default", "Cookies")))
            self.assertFalse(os.path.exists(os.path.join(destination, "SingletonLock")))
            self.assertFalse(os.path.exists(os.path.join(destination, "Default", "Cache")))
            mode = stat.S_IMODE(os.stat(destination).st_mode)
            if os.name == "posix":
                self.assertEqual(mode & 0o077, 0)

    def test_report_omits_password_and_sway_replies(self) -> None:
        login = Login("ada", "s3cret-value")
        text = _report(
            {
                "name": "HDMI-A-1",
                "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                "current_mode": {"width": 1920, "height": 1080, "refresh": 60},
            },
            True,
            "/usr/bin/chromium",
            login,
            "login-submitted",
            [
                RunningPane(
                    "lead_times",
                    9223,
                    10,
                    "chrome-odoo.nxcmfg.com__-Default",
                    100,
                    "0,0 640x540",
                )
            ],
        )
        self.assertNotIn("s3cret-value", text)
        self.assertNotIn('{"success"', text)
        self.assertIn("profile_model=separate", text)
        self.assertIn("memory:", text)
        self.assertIn("login_file=present", text)

    def test_websocket_text_roundtrip(self) -> None:
        left, right = socket.socketpair()
        try:
            payload = '{"id": 1, "method": "Runtime.evaluate"}' + ("x" * 200)
            _send_text(left, payload)
            right.settimeout(2)
            self.assertEqual(_recv_text(right), payload)
        finally:
            left.close()
            right.close()


if __name__ == "__main__":
    unittest.main()
