param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath,
    [string]$Version = "0.3.0",
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$resolvedExe = [System.IO.Path]::GetFullPath($ExePath)
if (-not (Test-Path -LiteralPath $resolvedExe -PathType Leaf)) {
    throw "JobMailDesk.exe not found: $resolvedExe"
}
if (-not $OutputDirectory) {
    $OutputDirectory = Split-Path -Parent $resolvedExe
}
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null

$packageName = "JobMailDesk-Core-v$Version-win-x64"
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "jobmaildesk-package-" + [guid]::NewGuid().ToString("N")
)
$packageRoot = Join-Path $temporaryRoot $packageName
$zipPath = Join-Path $resolvedOutput "$packageName.zip"
$checksumPath = "$zipPath.sha256"

try {
    New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null
    Copy-Item -LiteralPath $resolvedExe -Destination (Join-Path $packageRoot "JobMailDesk.exe")
    # Keep script literals ASCII-only for Windows PowerShell 5.1, which may
    # decode UTF-8-without-BOM source files using the active ANSI code page.
    Copy-Item -LiteralPath (Join-Path $projectRoot "docs\CORE_QUICKSTART.md") -Destination (Join-Path $packageRoot "QUICKSTART.zh-CN.md")
    Copy-Item -LiteralPath (Join-Path $projectRoot "docs\DEPENDENCIES.md") -Destination (Join-Path $packageRoot "DEPENDENCIES.zh-CN.md")
    Copy-Item -LiteralPath (Join-Path $projectRoot "docs\ACCEPTANCE_v0.3.0.md") -Destination (Join-Path $packageRoot "ACCEPTANCE.zh-CN.md")
    Copy-Item -LiteralPath (Join-Path $projectRoot "CHANGELOG.md") -Destination $packageRoot
    Copy-Item -LiteralPath (Join-Path $projectRoot "PRIVACY.md") -Destination $packageRoot
    Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $packageRoot
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "install-shortcuts.ps1") -Destination (Join-Path $packageRoot "install-shortcuts.ps1")
    Compress-Archive -LiteralPath $packageRoot -DestinationPath $zipPath -Force
    $hash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $packageName.zip" | Set-Content -LiteralPath $checksumPath -Encoding ascii
    Write-Output $zipPath
    Write-Output $checksumPath
}
finally {
    $resolvedTemporary = [System.IO.Path]::GetFullPath($temporaryRoot)
    $systemTemporary = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    if ($resolvedTemporary.StartsWith($systemTemporary) -and (Test-Path -LiteralPath $resolvedTemporary)) {
        Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
    }
}
