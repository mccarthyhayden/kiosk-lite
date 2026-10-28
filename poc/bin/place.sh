#!/bin/sh
# Place the two marked proof windows in a 70/30 split of the first active output.
# Coordinates are Sway logical pixels. Run again to restore the same geometry.

set -u

if ! swaymsg -t get_version >/dev/null 2>&1; then
    echo "Sway is not running. Start the tty1 session, or set SWAYSOCK, then retry." >&2
    exit 1
fi

json=$(swaymsg -t get_outputs)
active_count=$(printf '%s' "$json" | jq '[.[] | select(.active == true)] | length')
name=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].name // empty')
width=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].rect.width // empty')
height=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].rect.height // empty')
origin_x=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].rect.x // empty')
origin_y=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].rect.y // empty')
mode=$(printf '%s' "$json" | jq -r '[.[] | select(.active == true)][0].current_mode | if . == null then "unknown" else "\(.width)x\(.height)" end')

if [ -z "$name" ] || [ -z "$width" ] || [ -z "$height" ] || [ -z "$origin_x" ] || [ -z "$origin_y" ]; then
    echo "No active Sway output to place windows on." >&2
    exit 1
fi

if [ "$active_count" -gt 1 ]; then
    echo "NOTE $active_count outputs are active. Placing on $name." >&2
fi

left_w=$((width * 70 / 100))
right_w=$((width - left_w))
right_x=$((origin_x + left_w))

place_one() {
    mark=$1
    px=$2
    py=$3
    w=$4
    h=$5
    swaymsg "[con_mark=\"$mark\"] fullscreen disable, floating enable, border none, resize set $w $h, move absolute position $px $py"
}

if ! place_one kiosk-left "$origin_x" "$origin_y" "$left_w" "$height"; then
    echo "Could not place kiosk-left. Launch the proof windows first." >&2
    exit 1
fi
if ! place_one kiosk-right "$right_x" "$origin_y" "$right_w" "$height"; then
    echo "Could not place kiosk-right. Launch the proof windows first." >&2
    exit 1
fi

printf 'output=%s mode=%s\n' "$name" "$mode"
printf 'left=%s,%s %sx%s\n' "$origin_x" "$origin_y" "$left_w" "$height"
printf 'right=%s,%s %sx%s\n' "$right_x" "$origin_y" "$right_w" "$height"
