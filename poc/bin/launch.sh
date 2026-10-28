#!/bin/sh
# Open two chromeless Chromium windows and mark them for place.sh.
# Each page gets its own profile. On this Pi 4, one shared profile did not
# open a second window, and the TV's HDMI link comes up after Sway starts.

set -u
export LC_ALL=C

poc_bin=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
state_dir=${XDG_STATE_HOME:-"$HOME/.local/state"}/kiosk-lite
data_dir=${XDG_DATA_HOME:-"$HOME/.local/share"}/kiosk-lite
profile=$data_dir/chromium
profile_right=$data_dir/chromium-2
log=$state_dir/chromium.log
report=$state_dir/last-run.txt
left_url=${KIOSK_LEFT_URL:-https://example.com}
right_url=${KIOSK_RIGHT_URL:-https://example.org}
profile_model=separate
created_lock=0
keep_lock=0

if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
    echo "XDG_RUNTIME_DIR is unset. Run this from the Sway session." >&2
    exit 1
fi

lock=$XDG_RUNTIME_DIR/kiosk-lite-proof.lock

cleanup() {
    if [ "$created_lock" -eq 1 ] && [ "$keep_lock" -eq 0 ]; then
        rmdir "$lock" 2>/dev/null || true
    fi
}
trap cleanup EXIT

mkdir -p "$state_dir" "$data_dir"

if ! mkdir "$lock" 2>/dev/null; then
    echo "Proof already launched in this login session." >&2
    echo "Remove $lock only when you intend to launch again." >&2
    keep_lock=1
    exit 0
fi
created_lock=1
: > "$report"

log_line() {
    printf '%s\n' "$*" >> "$log"
}

report_line() {
    printf '%s\n' "$*" | tee -a "$report"
}

host_of() {
    printf '%s\n' "$1" | sed -e 's|^[a-zA-Z][a-zA-Z0-9+.-]*://||' -e 's|/.*||' -e 's|:.*||'
}

if ! swaymsg -t get_version >/dev/null 2>&1; then
    report_line "FAIL Sway is not running, so Chromium has no Wayland display."
    exit 1
fi

if command -v chromium >/dev/null 2>&1; then
    browser=chromium
elif command -v chromium-browser >/dev/null 2>&1; then
    browser=chromium-browser
else
    report_line "FAIL chromium is not installed."
    exit 1
fi

start_chromium() {
    url=$1
    dir=$2
    mkdir -p "$dir"
    # nohup keeps Chromium alive after this script exits. The sandbox stays enabled.
    nohup "$browser" \
        --ozone-platform=wayland \
        --user-data-dir="$dir" \
        --app="$url" \
        --password-store=basic \
        --no-first-run \
        --no-default-browser-check \
        --disable-translate \
        --disable-features=TranslateUI \
        --disable-infobars \
        --noerrdialogs \
        --autoplay-policy=no-user-gesture-required \
        --check-for-update-interval=31536000 \
        </dev/null >>"$log" 2>&1 &
    log_line "start pid=$! profile=$dir url=$url"
}

mark_window() {
    id=$1
    name=$2
    swaymsg "[con_id=$id] mark --replace $name, fullscreen disable, floating enable, border none" >>"$log" 2>&1
}

# The VIZIO link is often still down when Sway runs this script.
wait_for_output() {
    i=0
    while [ "$i" -lt 90 ]; do
        json=$(swaymsg -t get_outputs 2>/dev/null || true)
        name=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].name // empty' 2>/dev/null || true)
        if [ -n "$name" ]; then
            printf '%s\n' "$json"
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    return 1
}

prepare_output() {
    json=$(wait_for_output) || {
        report_line "FAIL no active display output after waiting."
        return 1
    }
    name=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].name // empty')
    has_1080=$(printf '%s' "$json" | jq -r --arg n "$name" '
        .[] | select(.name == $n) | .modes[]?
        | select(.width == 1920 and .height == 1080)
        | "yes"
    ' | head -n 1)
    if [ "$has_1080" != "yes" ]; then
        report_line "NOTE $name has no 1920x1080 mode; keeping the current mode"
        return 0
    fi
    if ! swaymsg "output \"$name\" mode 1920x1080" >>"$log" 2>&1; then
        report_line "WARN could not set 1920x1080 on $name"
        return 0
    fi
    log_line "requested 1920x1080 on $name"
    i=0
    while [ "$i" -lt 15 ]; do
        width=$(swaymsg -t get_outputs | jq -r --arg n "$name" '
            .[] | select(.name == $n) | .rect.width // empty
        ')
        if [ "$width" = "1920" ]; then
            sleep 1
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    report_line "WARN $name did not report 1920px after the mode change"
}

window_id_for() {
    needle=$1
    swaymsg -t get_tree | jq -r --arg needle "$needle" '
        first(
            .. | objects
            | select(.app_id != null and (.app_id | startswith($needle)))
            | .id
        ) // empty
    '
}

wait_for_windows() {
    left_needle=$1
    right_needle=$2
    i=0
    left_id=
    right_id=
    while [ "$i" -lt 180 ]; do
        if [ -z "$left_id" ]; then
            left_id=$(window_id_for "$left_needle")
        fi
        if [ -z "$right_id" ]; then
            right_id=$(window_id_for "$right_needle")
        fi
        if [ -n "$left_id" ] && [ -n "$right_id" ]; then
            printf '%s %s\n' "$left_id" "$right_id"
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    log_line "timeout left=${left_id:-missing} right=${right_id:-missing}"
    return 1
}

field_for_mark() {
    mark=$1
    field=$2
    swaymsg -t get_tree | jq -r --arg mark "$mark" --arg field "$field" '
        .. | objects
        | select(.marks != null and (.marks | index($mark)))
        | .[$field] // ""
    ' | head -n 1
}

log_line "---- $(date -Is) ----"

if ! prepare_output; then
    exit 1
fi

start_chromium "$left_url" "$profile"
start_chromium "$right_url" "$profile_right"

left_needle=$(printf 'chrome-%s' "$(host_of "$left_url")")
right_needle=$(printf 'chrome-%s' "$(host_of "$right_url")")
ids=$(wait_for_windows "$left_needle" "$right_needle") || {
    report_line "FAIL a Chromium window did not appear within 180 seconds."
    report_line "See $log"
    exit 1
}
left_id=${ids%% *}
right_id=${ids#* }

if ! mark_window "$left_id" kiosk-left; then
    report_line "FAIL could not mark the left window $left_id"
    exit 1
fi
if ! mark_window "$right_id" kiosk-right; then
    report_line "FAIL could not mark the right window $right_id"
    exit 1
fi
log_line "marked kiosk-left con_id=$left_id kiosk-right con_id=$right_id"

place_out=$(sh "$poc_bin/place.sh" 2>>"$log")
rc=$?
printf '%s\n' "$place_out" >> "$report"
printf '%s\n' "$place_out"
if [ "$rc" -ne 0 ]; then
    report_line "FAIL window placement failed."
    exit 1
fi

left_app=$(field_for_mark kiosk-left app_id)
right_app=$(field_for_mark kiosk-right app_id)
left_pid=$(field_for_mark kiosk-left pid)
right_pid=$(field_for_mark kiosk-right pid)
left_title=$(field_for_mark kiosk-left name)
right_title=$(field_for_mark kiosk-right name)

if [ -n "$left_pid" ] && [ "$left_pid" = "$right_pid" ]; then
    same_pid=yes
else
    same_pid=no
fi

{
    printf 'time=%s\n' "$(date -Is)"
    if [ -r /proc/device-tree/model ]; then
        printf 'model=%s\n' "$(tr -d '\0' < /proc/device-tree/model)"
    fi
    printf 'browser=%s\n' "$browser"
    sway --version 2>/dev/null || true
    printf 'profile_model=%s\n' "$profile_model"
    printf 'same_pid=%s\n' "$same_pid"
    printf 'left con_id=%s app_id=%s pid=%s title=%s\n' "$left_id" "$left_app" "$left_pid" "$left_title"
    printf 'right con_id=%s app_id=%s pid=%s title=%s\n' "$right_id" "$right_app" "$right_pid" "$right_title"
    printf 'memory:\n'
    free -h
    printf 'report=%s\n' "$report"
} | tee -a "$report"

keep_lock=1
exit 0
