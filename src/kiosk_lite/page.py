"""Adjust the loaded page. This does not change Odoo."""

from __future__ import annotations

from kiosk_lite.cdp import Cdp, CdpError

# The Odoo web client draws a navbar and a control panel on /web. The control
# panel is the "Dashboards" title, and on the gantt it is the New button and
# search bar. A standalone page such as the meeting-notes TV view has none of
# these elements, so it is unchanged.
HIDE_NAVBAR_CSS = """
.o_navbar,
.o_main_navbar,
.o_control_panel {
  display: none !important;
}
.o_web_client,
.o_action,
.o_view_controller,
.o_content {
  height: 100% !important;
}
.o_action_manager,
.o_content {
  flex: 1 1 auto !important;
}
"""

CHROME_SCRIPT = (
    "(() => {"
    "const root = document.head || document.documentElement;"
    "if (!root) return 'no-document';"
    "const id = 'kiosk-lite-chrome';"
    "let style = document.getElementById(id);"
    "if (!style) {"
    "style = document.createElement('style');"
    "style.id = id;"
    "root.appendChild(style);"
    "}"
    f"style.textContent = {HIDE_NAVBAR_CSS!r};"
    "return 'installed';"
    "})()"
)


def install_chrome(cdp: Cdp, register: bool = True) -> str:
    """Hide the Odoo navbar on this document.

    When register is true, Chromium also runs the same script on later
    navigations. Call that once per pane so the registration does not pile up.
    """
    if register:
        try:
            cdp.call("Page.addScriptToEvaluateOnNewDocument", {"source": CHROME_SCRIPT})
        except CdpError:
            pass
    value = cdp.evaluate(CHROME_SCRIPT)
    return value if isinstance(value, str) else "unknown"
