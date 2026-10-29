# Shop-floor layout

Phase 1 showed two chromeless Chromium windows on Raspberry Pi OS Lite without a desktop. This directory now opens the four Odoo panes in `config/kiosk.yaml`. The test machine is a Raspberry Pi 4 with 4 GB of RAM and the 64-bit CLI image.

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
  dbus-user-session \
  python3-yaml
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

## Odoo password

The password is not in git and should not be pasted into chat. On the Pi, as `kiosk-user`:

```sh
mkdir -p ~/.config/kiosk-lite
cp "$HOME/kiosk-lite/config/odoo-login.example" ~/.config/kiosk-lite/odoo-login
chmod 600 ~/.config/kiosk-lite/odoo-login
```

Edit that file so `username=` and `password=` are the Odoo web login. The launcher reads it only when a pane is on the Odoo login page. A normal boot uses the cookies already in the profile. If the account asks for a second factor, the TV shows that challenge. `wayvnc` from another computer can finish it, and it stays off during normal display.

If the file is missing, the four panes still open and the report says the login file is missing.

## What appears

`session.sh` starts Sway, which runs `launch.sh`. That script starts the Python layout.

1. The program waits up to 90 seconds for the TV to finish the HDMI handshake, then requests 1920x1080 when that mode is listed.
2. One Chromium window opens the first pane. If Odoo shows the login form, the password file is submitted. The browser is then closed.
3. That profile is copied to one directory per pane. Two Chromium processes never share a directory.
4. The panes start one at a time. Each waits up to 180 seconds for its own new Sway window. All four URLs are on `odoo.nxcmfg.com`, so the app id is the same for each and cannot be used to tell them apart.
5. Each window is marked `kiosk-<pane-id>`, fullscreen is turned off, and the rectangle from `config/kiosk.yaml` is applied. Until that runs, a new page sits at Chromium's default size.
6. Panes with `hide_navbar: true` lose the Odoo web-client bar. The meeting-notes page has no such bar, so it looks the same. Set `hide_navbar: false` on a pane to keep the bar.

The starting rectangles are 640x540, 1280x540, 640x540, and 1280x540. Change them in the YAML after looking at the TV.

Chromium is not started with `--kiosk`, `--no-sandbox`, `--class`, `--window-position`, or `--window-size`. Wayland clients do not place themselves. `--password-store=basic` avoids a keyring prompt that Lite cannot answer.

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

`profile_model=separate` means each pane has its own profile directory. `same_pid=yes` means Sway saw one process id for more than one pane. `login_file=missing` means the password file was not on the Pi. The report does not contain the password.

To launch again in the same login session, exit Sway or remove `$XDG_RUNTIME_DIR/kiosk-lite.lock`, then run `sh poc/bin/launch.sh` with `SWAYSOCK` set. Quit any Chromium that is still using those profile directories first.

## Pass

- `check.sh` exits 0.
- Four Odoo panes are visible at once, without an address bar or a desktop panel.
- They sit on the rectangles in `config/kiosk.yaml`.
- Running `place.sh` again puts them back after a focus change.
- `last-run.txt` records the output mode, the profile model, each pane, and `free -h`, and does not contain the password.
