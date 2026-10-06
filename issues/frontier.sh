#!/usr/bin/env bash
# Works with the macOS system Bash and on Windows Git Bash.
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$(dirname "$0")/frontier.py" "$@"
fi
exec python "$(dirname "$0")/frontier.py" "$@"
