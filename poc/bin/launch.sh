#!/bin/sh
# Open two chromeless Chromium windows and mark them for place.sh.
# Prefers one profile. Uses a second profile only if the second window never appears.

set -u
export LC_ALL=C

poc_bin=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
state_dir=${XDG_STATE_HOME:-"$HOME/.local/state"}/kiosk-lite
data_dir=${XDG_DATA_HOME:-"$HOME/.local/share"}/kiosk-lite
profile=$data_dir/chromium
profile_fallback=$data_dir/chromium-2
log=$state_dir/chromium.log
report=$state_dir/last-run.txt
left_url=${KIOSK_LEFT_URL:-https://example.com}
right_url=${KIOSK_RIGHT_URL:-https://example.org}
profile_model=shared
tmp=
created_lock=0
keep_lock=0

if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
    echo "XDG_RUNTIME_DIR is unset. Run this from the Sway session." >&2
    exit 1
fi

lock=$XDG_RUNTIME_DIR/kiosk-lite-proof.lock

cleanup() {
    if [ -n "$tmp" ]; then
        rm -rf "$tmp"
    fi
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

container_ids() {
    swaymsg -t get_tree | jq -r '
        .. | objects
        | select(.type == "con" and .app_id != null and .app_id != "")
        | .id
    ' | sort
}

wait_for_new() {
    before=$1
    work=$2
    i=0
    while [ "$i" -lt 60 ]; do
        now=$(container_ids) || return 1
        printf '%s\n' "$before" | sed '/^$/d' | sort > "$work/before"
        printf '%s\n' "$now" | sed '/^$/d' | sort > "$work/now"
        new=$(comm -13 "$work/before" "$work/now")
        count=$(printf '%s\n' "$new" | sed '/^$/d' | wc -l | tr -d ' ')
        if [ "$count" -eq 1 ]; then
            printf '%s\n' "$new" | sed '/^$/d'
            return 0
        fi
        if [ "$count" -gt 1 ]; then
            log_line "more than one new window: $(printf '%s' "$new" | tr '\n' ' ')"
            return 2
        fi
        i=$((i + 1))
        sleep 1
    done
    return 1
}

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
    swaymsg "[con_id=$id] mark $name, floating enable, border none" >>"$log" 2>&1
}

prepare_output() {
    json=$(swaymsg -t get_outputs)
    name=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].name // empty')
    if [ -z "$name" ]; then
        report_line "FAIL no active display output."
        return 1
    fi
    has_1080=$(printf '%s' "$json" | jq -r --arg n "$name" '
        .[] | select(.name == $n) | .modes[]?
        | select(.width == 1920 and .height == 1080)
        | "yes"
    ' | head -n 1)
    if [ "$has_1080" = "yes" ]; then
        if swaymsg "output \"$name\" mode 1920x1080" >>"$log" 2>&1; then
            log_line "requested 1920x1080 on $name"
            sleep 1
        else
            report_line "WARN could not set 1920x1080 on $name"
        fi
    else
        report_line "NOTE $name has no 1920x1080 mode; keeping the current mode"
    fi
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

tmp=$(mktemp -d) || exit 1
log_line "---- $(date -Is) ----"

if ! prepare_output; then
    exit 1
fi

before=$(container_ids)
start_chromium "$left_url" "$profile"
left_id=$(wait_for_new "$before" "$tmp")
rc=$?
if [ "$rc" -ne 0 ]; then
    if [ "$rc" -eq 2 ]; then
        report_line "FAIL more than one window appeared for the left page."
    else
        report_line "FAIL the first Chromium window did not appear."
    fi
    report_line "See $log"
    exit 1
fi
if ! mark_window "$left_id" kiosk-left; then
    report_line "FAIL could not mark the left window $left_id"
    exit 1
fi
log_line "marked kiosk-left con_id=$left_id"

before=$(container_ids)
start_chromium "$right_url" "$profile"
right_id=$(wait_for_new "$before" "$tmp")
rc=$?
if [ "$rc" -eq 2 ]; then
    report_line "FAIL more than one window appeared for the right page."
    report_line "See $log"
    exit 1
fi
if [ "$rc" -ne 0 ]; then
    log_line "shared profile did not open a second window"
    report_line "NOTE shared profile did not open a second window. Using a separate profile."
    profile_model=separate
    before=$(container_ids)
    start_chromium "$right_url" "$profile_fallback"
    right_id=$(wait_for_new "$before" "$tmp")
    rc=$?
    if [ "$rc" -ne 0 ]; then
        report_line "FAIL the second Chromium window did not appear."
        report_line "See $log"
        exit 1
    fi
fi
if ! mark_window "$right_id" kiosk-right; then
    report_line "FAIL could not mark the right window $right_id"
    exit 1
fi
log_line "marked kiosk-right con_id=$right_id"

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
