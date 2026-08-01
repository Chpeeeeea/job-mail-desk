param(
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $projectRoot "release"
}
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputRoot)

Push-Location $projectRoot
try {
    uv sync --group dev
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed with exit code $LASTEXITCODE" }
    uv run pytest
    if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }
    & (Join-Path $PSScriptRoot "secret-scan.ps1")
    if ($LASTEXITCODE -ne 0) { throw "secret scan failed with exit code $LASTEXITCODE" }
    uv run pyinstaller --noconfirm --clean JobMailDesk.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
    New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot "dist\JobMailDesk.exe") -Destination (Join-Path $resolvedOutput "JobMailDesk.exe") -Force
    Write-Output (Join-Path $resolvedOutput "JobMailDesk.exe")
}
finally {
    Pop-Location
}
