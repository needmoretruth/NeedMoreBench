#!/bin/sh
# Start NeedMoreBench inside the Flatpak.
export PYTHONPATH=/app/share/needmorebench
exec python3 -P -m nmb "$@"
