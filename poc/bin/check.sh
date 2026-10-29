#!/bin/sh
# Report whether this Raspberry Pi OS Lite machine can run the phase 1 proof.
# Does not install packages or change boot configuration.

set -u

fails=0
missing_packages=0

pass() {
    printf 'PASS %s\n' "$*"
}

fail() {
    printf 'FAIL %s\n' "$*"
    fails=$((fails + 1))
}

note() {
    printf 'NOTE %s\n' "$*"
}

if [ "$(id -u)" -eq 0 ]; then
    echo "FAIL run check.sh as the console login user, not as root" >&2
    exit 1
fi

printf 'user=%s\n' "$(id -un)"
printf 'groups=%s\n' "$(id -nG)"

if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    printf 'os=%s\n' "${PRETTY_NAME:-unknown}"
else
    note "os-release is missing"
fi

machine=$(uname -m)
printf 'arch=%s\n' "$machine"
if [ "$machine" = "aarch64" ]; then
    pass "architecture aarch64"
else
    fail "architecture is $machine; this proof requires the 64-bit Lite image"
fi

if [ -r /proc/device-tree/model ]; then
    model=$(tr -d '\0' < /proc/device-tree/model)
    printf 'model=%s\n' "$model"
    case $model in
        *"Raspberry Pi 4"*)
            pass "board is Raspberry Pi 4"
            ;;
        *)
            note "board is not a Raspberry Pi 4; the proof can still be attempted"
            ;;
    esac
else
    note "device-tree model is not available"
fi

if [ -r /proc/meminfo ]; then
    mem_kb=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
    printf 'mem_total_kb=%s\n' "${mem_kb:-unknown}"
    if [ -n "$mem_kb" ] && [ "$mem_kb" -lt 3000000 ]; then
        note "visible RAM is under about 3 GB; this proof expects a 4 GB Pi 4"
    fi
fi

printf '\n'
free -h || true
printf '\n'

dri_found=0
for card in /dev/dri/card*; do
    if [ -e "$card" ]; then
        dri_found=1
        pass "drm node $card"
    fi
done
if [ "$dri_found" -eq 0 ]; then
    fail "no /dev/dri/card* node. Sway needs KMS (vc4-kms-v3d). Do not install a desktop and do not raise gpu_mem"
fi

for group in render video; do
    case " $(id -nG) " in
        *" $group "*)
            pass "group $group"
            ;;
        *)
            fail "user is not in group $group (sudo usermod -aG render,video $(id -un), then log in again)"
            ;;
    esac
done

if [ -n "${XDG_RUNTIME_DIR:-}" ] && [ -d "$XDG_RUNTIME_DIR" ] && [ -w "$XDG_RUNTIME_DIR" ]; then
    pass "XDG_RUNTIME_DIR $XDG_RUNTIME_DIR"
else
    fail "XDG_RUNTIME_DIR is missing or not writable. Install dbus-user-session and log in again"
fi

if dpkg -s dbus-user-session >/dev/null 2>&1; then
    pass "package dbus-user-session"
else
    fail "package dbus-user-session is not installed"
    missing_packages=1
fi

if dpkg -s fonts-liberation >/dev/null 2>&1; then
    pass "package fonts-liberation"
else
    fail "package fonts-liberation is not installed"
    missing_packages=1
fi

if dpkg -s python3-yaml >/dev/null 2>&1; then
    pass "package python3-yaml"
else
    fail "package python3-yaml is not installed"
    missing_packages=1
fi

for cmd in sway swaymsg jq python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
        pass "command $cmd"
    else
        fail "missing command: $cmd"
        missing_packages=1
    fi
done

if command -v chromium >/dev/null 2>&1; then
    pass "command chromium"
    browser=chromium
elif command -v chromium-browser >/dev/null 2>&1; then
    pass "command chromium-browser"
    browser=chromium-browser
else
    fail "missing command: chromium (or chromium-browser)"
    missing_packages=1
    browser=
fi

if command -v sway >/dev/null 2>&1; then
    sway --version || true
fi
if [ -n "$browser" ] && command -v timeout >/dev/null 2>&1; then
    timeout 20 "$browser" --version || note "$browser --version did not finish"
fi

if command -v systemctl >/dev/null 2>&1; then
    target=$(systemctl get-default 2>/dev/null || true)
    printf 'default_target=%s\n' "$target"
    if [ "$target" = "multi-user.target" ]; then
        pass "default target multi-user.target"
    else
        fail "default target is ${target:-unknown}. Console boot should stay on multi-user.target"
    fi
else
    fail "systemctl is not available"
fi

if [ "$missing_packages" -eq 1 ]; then
    printf '\nInstall only:\n'
    printf '  sudo apt update\n'
    printf '  sudo apt install --no-install-recommends sway chromium fonts-liberation jq dbus-user-session python3-yaml\n'
    printf 'If the chromium package name is rejected, install chromium-browser instead.\n'
    printf 'Do not install rpd-wayland-core, raspberrypi-ui-mods, lightdm, greetd, or a panel.\n'
fi

printf '\n'
if [ "$fails" -eq 0 ]; then
    echo "check passed"
    exit 0
fi

echo "$fails check(s) failed"
exit 1
