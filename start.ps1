# Start TFT Assistant: sync the Python core, then build and start the shell.
# The shell runs as a tray app and starts the core itself.
$ErrorActionPreference = 'Stop'
# Handle native failures explicitly, including when the caller enables this preference.
$PSNativeCommandUseErrorActionPreference = $false
$root = $PSScriptRoot

uv sync --project "$root/core" --quiet
if ($LASTEXITCODE -ne 0) {
    $code = $LASTEXITCODE
    Write-Error "uv sync failed (exit $code)" -ErrorAction Continue
    exit $code
}

if (-not (Test-Path "$root/ui/node_modules")) {
    npm ci --prefix "$root/ui"
    if ($LASTEXITCODE -ne 0) {
        $code = $LASTEXITCODE
        Write-Error "npm ci failed (exit $code)" -ErrorAction Continue
        exit $code
    }
}

# npm ci does not download the Electron binary; its own installer does. It
# exits at once when the matching binary is already present.
npm --prefix "$root/ui" run electron:install
if ($LASTEXITCODE -ne 0) {
    $code = $LASTEXITCODE
    Write-Error "Electron binary install failed (exit $code)" -ErrorAction Continue
    exit $code
}

npm --prefix "$root/ui" run build
if ($LASTEXITCODE -ne 0) {
    $code = $LASTEXITCODE
    Write-Error "UI build failed (exit $code)" -ErrorAction Continue
    exit $code
}

npm --prefix "$root/ui" run start
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Error "UI start failed (exit $code)" -ErrorAction Continue
}
exit $code
