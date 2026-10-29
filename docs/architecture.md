# Architecture

Phase 1 is signed off on a Raspberry Pi 4 (4 GB) running Raspberry Pi OS Lite 64-bit, the CLI-only image. Phase 2 keeps that Sway session and reads the four shop-floor panes from `config/kiosk.yaml`.

The spec's later performance pass still refers to a Pi 5. This phase does not.

## Decisions

**Language.** POSIX shell starts the session. The layout program is Python 3 with the standard library and PyYAML. No web framework and no Electron.

**License.** MIT, already in the repository.

**Compositor.** Sway. `swaymsg` can move and resize a window to explicit logical pixels, which is the placement the proof has to demonstrate. labwc is the fallback if the Sway package cannot open the display on this Lite image. It is not a second implementation in this phase. Cage is unused. `raspi-config`'s Wayland menu talks to a display manager and is not part of startup.

**Session.** Console autologin on tty1 runs `poc/bin/session.sh`, which starts Sway as the logged-in user. `WLR_LIBINPUT_NO_DEVICES=1` lets Sway start when the television has no keyboard. systemd-logind provides the seat through that login. A system service is not used, because a system unit does not own the DRM seat by itself. There is no display manager.

**Browser.** One profile directory per pane, under `~/.local/share/kiosk-lite/profiles/<pane-id>`. Two Chromium processes must not share a directory. The signed-off boot used separate profiles because one shared profile did not open a second window. Each window is an `--app` page on `--ozone-platform=wayland`, with `--password-store=basic`. The sandbox is left on. `--kiosk`, `--no-sandbox`, `--class`, `--window-position`, and `--window-size` are not used.

A debugging port is bound to `127.0.0.1` so the launcher can read the page address. The Odoo password is not in the YAML. It lives in the file named by `login.password_file` (by default `~/.config/kiosk-lite/odoo-login`), mode `0600`, owned by the console user. That file is gitignored. On boot the saved cookies are sent, and the password is submitted only when a pane is on `/web/login`. One successful login is copied to the other pane profiles after Chromium has exited. Logs and `last-run.txt` do not include the password. If the account asks for a second factor, the TV shows that challenge. A temporary `wayvnc` session from another computer is the fallback, and it stays off during normal display.

**Window identity.** Different sites get different Wayland app ids. The signed-off boot recorded `chrome-example.com__-Default` and `chrome-example.org__-Default`. Those ids were enough to tell the two windows apart. Chromium ignores `--class` on Wayland, and the profile folder inside each user-data directory is still named `Default`.

All four shop-floor URLs are on `odoo.nxcmfg.com`, so every pane gets the same app id, `chrome-odoo.nxcmfg.com__-Default`. Matching on the host name does not tell them apart. The launcher starts one pane, waits until one new Sway container exists, marks it, places it, and only then starts the next pane.

**Coordinates.** Logical pixels in `config/kiosk.yaml`. The starting layout is a 1920x1080 screen with a 640 px left column and a 1280 px right column, each row 540 px tall. When the display lists 1920x1080, the session requests that mode before Chromium starts. 4K is not part of this phase. A second connected output is ignored aside from the output name in the report.

**Dependencies.** `poc/bin/check.sh` is the preflight. The apt set is `sway`, `chromium` (or `chromium-browser`), `fonts-liberation`, `jq`, `dbus-user-session`, and `python3-yaml`, installed with `--no-install-recommends`. Xwayland is disabled in the Sway config. `seatd` is only a reaction to a seat error, not a default package.

## Rejected assumptions

- Chromium cannot be given an absolute pixel position on Wayland. Sway places the windows.
- `--kiosk` fullscreens one surface and fights a 70/30 split.
- `--window-position`, `--window-size`, and `--class` are not the Wayland controls for this proof.
- Installing the Raspberry Pi desktop and hiding it does not meet the Lite requirement.
- A 32-bit Raspbian image is out of scope. `check.sh` requires `aarch64`.
- The spec's Pi 5 / 4K reference is a later measurement, not the sign-off for this phase.

## Deferred

Still out of this slice:

- Live reload of the YAML file
- Refreshing a single page on a timer, and any browser extension
- systemd user or system units, boot ordering, and crash recovery
- Display blanking beyond Sway's `hide_cursor`, and cursor policy as a product setting
- Percentage layouts, extra monitors, and portrait orientation
- Installer, uninstaller, and package builds
- GPU flags and 4K measurement
- labwc, unless Sway fails the tty1 checkpoint

The pane list is `config/kiosk.yaml`. The Odoo password stays in the Pi-local file described above. An Odoo API key does not sign in these web pages.

## Hardware results

Phase 1 sign-off, 28 Oct 2026 15:15, on the Pi 4 kiosk (`nxcmfg-kiosk`), Raspberry Pi OS Lite, user `kiosk-user`, TV VIZIO E65-E3. Nobody typed `swaymsg`. `last-run.txt` showed:

- HDMI-A-1 at 1920x1080
- left `0,0 1344x1080`, right `1344,0 576x1080`
- `profile_model=separate`, `same_pid=no` (pids 1223 and 1225)
- app ids `chrome-example.com__-Default` and `chrome-example.org__-Default`
- Raspberry Pi 4 Model B Rev 1.1, Sway 1.10.1, browser `chromium`
- memory: 3.7 GiB total, 601 MiB used, 3.1 GiB available, swap unused

Sway from apt opened the display. The labwc stop-gate was not hit. Console autologin on tty1 starts `session.sh`. The TV's preferred mode is 3840x2160 at 30 Hz, and that link is not up yet when Sway first starts, so the launcher waits for an active output and then requests 1920x1080. New Chromium windows open centered and stacked until placement runs. The `{"success": true}` lines in that sign-off file were `swaymsg` replies. The Phase 2 report leaves them out.

Those two pages were static. 601 MiB used and 3.1 GiB available does not say what four Odoo dashboards will cost. The Phase 2 launcher writes `free -h` into `last-run.txt` after the four panes start. That four-pane figure is not in this note until that file is copied back from the Pi. If the board starts swapping, a pane can be removed from the YAML without a code change.
