#!/bin/sh
# Put the existing panes back at the rectangles in the home-directory layout.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
if [ -z "${SWAYSOCK:-}" ]; then
    sock=$(find "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" -name 'sway-ipc.*.sock' 2>/dev/null | head -n 1)
    if [ -n "$sock" ]; then
        SWAYSOCK=$sock
        export SWAYSOCK
    fi
fi
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m kiosk_lite --place-only
