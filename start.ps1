# Start TFT Assistant: sync the Python core, then build and start the shell.
# The shell runs as a tray app and starts the core itself.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot

uv sync --project "$root/core" --quiet
if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }

if (-not (Test-Path "$root/ui/node_modules")) {
    npm ci --prefix "$root/ui"
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
}

npm --prefix "$root/ui" run start
