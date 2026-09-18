#!/usr/bin/env bash
# The spruce window: ./spruce_window.sh on [minutes] | off | status (house_window.sh).
exec "$(dirname "$0")/house_window.sh" spruce "$@"
