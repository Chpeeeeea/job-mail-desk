$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$outputRoot = "D:\WrokSpace\Obsidian-Workspace\Vibe\output\JobMailDesk"

Push-Location $projectRoot
try {
    uv sync --group dev
    uv run pytest
    & (Join-Path $PSScriptRoot "secret-scan.ps1")
    uv run pyinstaller --noconfirm --clean JobMailDesk.spec
    New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot "dist\JobMailDesk.exe") -Destination (Join-Path $outputRoot "JobMailDesk.exe") -Force
    Write-Output (Join-Path $outputRoot "JobMailDesk.exe")
}
finally {
    Pop-Location
}
