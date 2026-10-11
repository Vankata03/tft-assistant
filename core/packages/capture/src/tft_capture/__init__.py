"""Game-state capture and its process-start telemetry policy."""

import os as _os

# The POSIX provider latches this before creating its telemetry SDK. Package
# startup precedes the reader and training modules' optional runtime imports.
# An ORT environment initialized by a host before this import is already live.
_os.environ["ORT_DISABLE_TELEMETRY"] = "1"
