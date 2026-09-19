#!/usr/bin/env bash
# The beech window: ./beech_window.sh on [minutes] [--debug] [--ltn] | off | status (house_window.sh).
exec "$(dirname "$0")/house_window.sh" beech "$@"
