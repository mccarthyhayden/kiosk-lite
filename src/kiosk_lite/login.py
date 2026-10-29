"""Submit the Odoo login form only when a pane is already on that page."""

from __future__ import annotations

import json
import urllib.parse

from kiosk_lite.cdp import Cdp
from kiosk_lite.config import Login


def is_login_url(url: str) -> bool:
    path = urllib.parse.urlparse(url or "").path.rstrip("/")
    return path == "/web/login"


def page_url(cdp: Cdp) -> str:
    value = cdp.evaluate("location.href")
    return value if isinstance(value, str) else ""


def login_stage(cdp: Cdp) -> str:
    """Return password, challenge, or absent. A second factor is left for a person."""
    value = cdp.evaluate(
        "(() => {"
        "const secret = document.querySelector('input[name=\"password\"]');"
        "if (!secret) return 'absent';"
        "const totp = document.querySelector('input[name=\"totp_token\"], input[name=\"otp\"]');"
        "if (totp) return 'challenge';"
        "return 'password';"
        "})()"
    )
    return value if isinstance(value, str) else "absent"


def submit_login(cdp: Cdp, login: Login) -> str:
    """Fill the form in the page. Returns a short status word, never the password."""
    script = (
        "(() => {"
        f"const creds = {json.dumps({'username': login.username, 'password': login.password})};"
        "const user = document.querySelector('input[name=\"login\"]');"
        "const secret = document.querySelector('input[name=\"password\"]');"
        "if (!user || !secret) return 'missing-fields';"
        "user.focus();"
        "user.value = creds.username;"
        "user.dispatchEvent(new Event('input', {bubbles: true}));"
        "secret.focus();"
        "secret.value = creds.password;"
        "secret.dispatchEvent(new Event('input', {bubbles: true}));"
        "const form = secret.closest('form');"
        "const button = form && form.querySelector('button[type=\"submit\"]');"
        "if (button) { button.click(); return 'clicked'; }"
        "if (form) { form.submit(); return 'submitted'; }"
        "return 'missing-form';"
        "})()"
    )
    value = cdp.evaluate(script)
    return value if isinstance(value, str) else "unknown"
