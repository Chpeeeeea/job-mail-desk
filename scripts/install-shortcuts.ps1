param(
    [Parameter(Mandatory = $true)]
    [string]$ExePath
)

$ErrorActionPreference = "Stop"
$resolvedExe = [System.IO.Path]::GetFullPath($ExePath)
if (-not (Test-Path -LiteralPath $resolvedExe -PathType Leaf)) {
    throw "JobMailDesk.exe not found: $resolvedExe"
}

$shell = New-Object -ComObject WScript.Shell
$localizedName = -join @(
    [char]0x6C42,
    [char]0x804C,
    [char]0x5361,
    [char]0x7247
)
$shortcutName = "JobMailDesk $localizedName.lnk"
$targets = @(
    (Join-Path ([Environment]::GetFolderPath("Desktop")) $shortcutName),
    (Join-Path ([Environment]::GetFolderPath("Programs")) $shortcutName)
)

foreach ($target in $targets) {
    $shortcut = $shell.CreateShortcut($target)
    $shortcut.TargetPath = $resolvedExe
    $shortcut.Arguments = "show"
    $shortcut.WorkingDirectory = Split-Path -Parent $resolvedExe
    $shortcut.IconLocation = "$resolvedExe,0"
    $shortcut.Description = "Show JobMailDesk"
    $shortcut.Save()
    Write-Output $target
}
