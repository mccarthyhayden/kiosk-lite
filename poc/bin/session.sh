#!/bin/sh
# Start the phase 1 Sway session on the physical console.
# SSH can run check.sh. SSH cannot show the windows.

set -u

if [ "$(id -u)" -eq 0 ]; then
    echo "Refusing to start the proof session as root." >&2
    exit 1
fi

tty_name=$(tty 2>/dev/null || true)
if [ "$tty_name" != "/dev/tty1" ]; then
    echo "The proof session only starts on /dev/tty1 (this is ${tty_name:-not a tty})." >&2
    echo "Run poc/bin/check.sh over SSH. Start the display from the console." >&2
    exit 1
fi

if [ -z "${XDG_RUNTIME_DIR:-}" ] || [ ! -d "$XDG_RUNTIME_DIR" ]; then
    echo "XDG_RUNTIME_DIR is unset. Install dbus-user-session and log in again." >&2
    exit 1
fi

poc_bin=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
poc_root=$(CDPATH= cd -- "$poc_bin/.." && pwd)

export WLR_LIBINPUT_NO_DEVICES=1
export XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=sway
export PATH="$poc_bin:$PATH"

runtime_config=$XDG_RUNTIME_DIR/kiosk-lite-sway.conf
cp "$poc_root/sway/config" "$runtime_config"
printf "exec sh '%s'\n" "$poc_bin/launch.sh" >> "$runtime_config"

echo "Starting Sway. Press Mod4+Shift+e to exit."
echo "If the display does not open, do not install a desktop."

sway -c "$runtime_config"
status=$?

echo "STOP: Sway exited with status $status." >&2
echo "Do not install rpd-wayland-core, raspberrypi-ui-mods, lightdm, greetd, or another desktop." >&2
echo "If Sway could not open the DRM device, stop and switch this proof to labwc." >&2
exit "$status"
