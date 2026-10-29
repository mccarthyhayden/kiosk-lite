#!/bin/sh
# Start the YAML layout. Sway runs this script; the Python program replaces it.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m kiosk_lite --config "$root/config/kiosk.yaml"
