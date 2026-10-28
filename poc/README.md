# Phase 1 proof

This directory proves that Raspberry Pi OS Lite can show two chromeless Chromium windows side by side without a desktop. The test machine is a Raspberry Pi 4 with 4 GB of RAM and the 64-bit CLI image.

Run the dependency check over SSH. Start Sway from the console on tty1. SSH cannot open the display.

## Packages

Lite does not include a compositor, Chromium, fonts, or a user D-Bus session. Install only:

```sh
sudo apt update
sudo apt install --no-install-recommends \
  sway \
  chromium \
  fonts-liberation \
  jq \
  dbus-user-session
```

If `chromium` is not the package name on that image, install `chromium-browser` instead.

Do not install `rpd-wayland-core`, `raspberrypi-ui-mods`, lightdm, greetd, wayfire, or a panel. Do not use `raspi-config`'s Wayland or desktop boot options. Those edit a display manager this image does not have.

`seatd` is not part of the install. Add it only if Sway later reports a seat or DRM permission error.

## Check

From the console login user, not root:

```sh
sh poc/bin/check.sh
```

The check does not install packages. It fails when the machine is 32-bit, when `/dev/dri/card*` is missing, when the user is outside the `render` or `video` groups, when `XDG_RUNTIME_DIR` is missing, when a required command is missing, or when systemd's default target is not `multi-user.target`.

A missing DRM node means the KMS overlay is not active. Do not raise `gpu_mem` and do not install a desktop to compensate.

If the group check fails:

```sh
sudo usermod -aG render,video "$USER"
```

Log out and back in before running the check again.

## Console session

Enable console autologin, not desktop autologin:

```sh
sudo raspi-config nonint do_boot_behaviour B2
```

Append this to `~/.bash_profile` if that file exists, otherwise to `~/.profile`. Change the path if the clone does not live in `$HOME/kiosk-lite`.

```sh
if [ "$(tty 2>/dev/null)" = "/dev/tty1" ]; then
    exec sh "$HOME/kiosk-lite/poc/bin/session.sh"
fi
```

Reboot. tty1 should start Sway: a black screen, no panel, and the pointer hidden after three seconds. A keyboard exits the session with Mod4+Shift+e.

If Sway exits immediately, read the message on the console. Do not install a desktop. If it could not open the DRM device, stop and switch this proof to labwc.

## What appears

`session.sh` starts Sway, which runs `launch.sh`.

1. If the connected display lists 1920x1080, Sway switches to that mode. Otherwise the current mode is kept and recorded.
2. The script waits up to 90 seconds for the TV to finish the HDMI handshake, then requests 1920x1080 when that mode is listed.
3. Chromium opens `https://example.com` from `~/.local/share/kiosk-lite/chromium` and `https://example.org` from `~/.local/share/kiosk-lite/chromium-2`. On the Pi 4, one shared profile did not create a second window.
4. The script waits up to 180 seconds for both windows. A cold Chromium start on this board can take longer than a minute.
5. Each window is marked `kiosk-left` or `kiosk-right`.
6. `place.sh` turns fullscreen off and sizes them to about 70% and 30% of the active output. Until that runs, both pages sit on top of each other at Chromium's default size.

Chromium is not started with `--kiosk`, `--no-sandbox`, `--class`, `--window-position`, or `--window-size`. Wayland clients do not place themselves. `--password-store=basic` avoids a keyring prompt that Lite cannot answer.

Override the pages for a later trial:

```sh
KIOSK_LEFT_URL=https://example.com KIOSK_RIGHT_URL=https://example.org
```

## Restore the layout

From another tty or from SSH, as the same user:

```sh
sock=$(find "$XDG_RUNTIME_DIR" -name 'sway-ipc.*.sock' | head -n 1)
SWAYSOCK=$sock sh poc/bin/place.sh
```

## Read the result

```sh
cat ~/.local/state/kiosk-lite/last-run.txt
cat ~/.local/state/kiosk-lite/chromium.log
```

Copy `last-run.txt` into the hardware results section of `docs/architecture.md`.

`profile_model=shared` means the second page used the first Chromium profile. `same_pid=yes` means Sway saw one process id for both windows. `profile_model=separate` means the shared profile did not create a second window and the fallback profile was used.

To launch again in the same login session, exit Sway or remove `$XDG_RUNTIME_DIR/kiosk-lite-proof.lock`, then run `sh poc/bin/launch.sh` with `SWAYSOCK` set.

## Pass

- `check.sh` exits 0.
- Two pages are visible at once, without an address bar or a desktop panel.
- The left page is about 70% of the width and the right page is the rest, both full height.
- Running `place.sh` again puts them back after a focus change.
- `last-run.txt` records the output mode, the profile model, both window ids, and `free -h`.
