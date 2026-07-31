$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    uv run jobmaildesk ui
}
finally {
    Pop-Location
}

