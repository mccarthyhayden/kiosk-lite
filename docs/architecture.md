# Architecture

Phase 1 is a shell proof on a Raspberry Pi 4 (4 GB) running Raspberry Pi OS Lite 64-bit, the CLI-only image. It exists to show two chromeless browser windows in a side-by-side layout before any application framework is added.

The spec's later performance pass still refers to a Pi 5. This phase does not.

## Decisions

**Language.** POSIX shell for the proof. From Phase 2, the application language is Python 3 with the standard library and PyYAML. No web framework and no Electron.

**License.** MIT, already in the repository.

**Compositor.** Sway. `swaymsg` can move and resize a window to explicit logical pixels, which is the placement the proof has to demonstrate. labwc is the fallback if the Sway package cannot open the display on this Lite image. It is not a second implementation in this phase. Cage is unused. `raspi-config`'s Wayland menu talks to a display manager and is not part of startup.

**Session.** Console autologin on tty1 runs `poc/bin/session.sh`, which starts Sway as the logged-in user. `WLR_LIBINPUT_NO_DEVICES=1` lets Sway start when the television has no keyboard. systemd-logind provides the seat through that login. A system service is not used, because a system unit does not own the DRM seat by itself. There is no display manager.

**Browser.** One Chromium process and one profile (`~/.local/share/kiosk-lite/chromium`) is the first attempt. The windows are `--app` pages on `--ozone-platform=wayland`. A second profile is used only when the shared profile does not create a second Sway container. Two processes must not be pointed at the same profile directory. The sandbox is left on.

**Window identity.** Pages on one host can share a Wayland `app_id`, and Chromium ignores `--class` on Wayland. The proof does not trust titles either: `example.com` and `example.org` both title themselves "Example Domain". `launch.sh` snapshots Sway's container ids, waits until one new window exists, and marks it `kiosk-left` or `kiosk-right`. Placement uses those marks.

**Coordinates.** Logical pixels from the first active Sway output. The split is 70/30 of that output's current rectangle, full height, origin at the output's top left. No HDMI name is hardcoded. When the display lists 1920x1080, the session requests that mode before Chromium starts. 4K is not part of this proof. A second connected output is ignored aside from a note naming which output was used.

**Dependencies.** `poc/bin/check.sh` is the preflight. The apt set is `sway`, `chromium` (or `chromium-browser`), `fonts-liberation`, `jq`, and `dbus-user-session`, installed with `--no-install-recommends`. Xwayland is disabled in the Sway config. `seatd` is only a reaction to a seat error, not a default package.

## Rejected assumptions

- Chromium cannot be given an absolute pixel position on Wayland. Sway places the windows.
- `--kiosk` fullscreens one surface and fights a 70/30 split.
- `--window-position`, `--window-size`, and `--class` are not the Wayland controls for this proof.
- Installing the Raspberry Pi desktop and hiding it does not meet the Lite requirement.
- A 32-bit Raspbian image is out of scope. `check.sh` requires `aarch64`.
- The spec's Pi 5 / 4K reference is a later measurement, not the sign-off for this phase.

## Deferred

These stay out until the hardware note below is filled in from a real run:

- YAML configuration, validation, and live reload
- Chrome DevTools Protocol refresh, and any browser extension
- systemd user or system units, boot ordering, and crash recovery
- Display blanking beyond Sway's `hide_cursor`, and cursor policy as a product setting
- Percentage layouts, extra monitors, and portrait orientation
- Credential storage or login automation
- Installer, uninstaller, and package builds
- GPU flags and 4K measurement
- labwc, unless Sway fails the tty1 checkpoint

Refreshing one page, recovering a crash, and persisting a login are Phase 2 and Phase 3. An interval of work that needs a password does not belong in the proof config.

## Hardware results

Not run from this workspace. This tree cannot open the Pi 4's display.

After a console run, copy `~/.local/state/kiosk-lite/last-run.txt` over the pending lines. Do not treat the proof as signed off while they stay pending.

```text
time: pending
model: pending
browser: pending
sway: pending
output mode: pending
profile_model: pending
same_pid: pending
left: pending
right: pending
memory: pending
```

How to read the process result:

- `profile_model=shared` and `same_pid=yes` means one Chromium process was enough to identify and place both windows.
- `profile_model=shared` and `same_pid=no` means both pages shared a profile, but Sway reported different process ids. Keep the shared profile and record the ids before deciding that separate processes are required.
- `profile_model=separate` means the shared profile never opened a second window. The right page used `chromium-2`. That result is the reason to prefer one process per window in Phase 2.

Also record whether Sway from apt opened the DRM device, or whether the labwc stop-gate was hit. The stop-gate is a failed Sway start. It is not a desktop install.
