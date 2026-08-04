$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$textExtensions = @(
    ".py", ".js", ".css", ".html", ".md", ".toml", ".json",
    ".yaml", ".yml", ".ps1", ".cmd", ".spec", ".txt"
)
$patterns = [ordered]@{
    "QQ email" = '(?i)\b[A-Z0-9._%+-]+@qq\.com\b'
    "Personal Windows path" = '(?i)C:\\Users\\(?!<当前用户>|<user>|username)[^\\\s]+'
    "Credential literal" = '(?i)(authorization_code|password|passwd|secret|api_key)\s*[:=]\s*["''][^"'']{8,}["'']'
    "Private URL token" = '(?i)https?://[^\s"'']+[?&](token|auth|code|session|ticket|key)=[^&\s"'']{8,}'
    "Standalone long number" = '(?<!local-role-)(?<!local-company-)(?<!local-program-)(?<![A-Za-z0-9_])\d{10,}(?![A-Za-z0-9_])'
}

Push-Location $projectRoot
try {
    # Include staged/tracked files and new release candidates. Scanning only
    # tracked files would miss secrets in files added by the current release.
    $tracked = git ls-files --cached --others --exclude-standard 2>$null
    if (-not $tracked) {
        $tracked = Get-ChildItem -Recurse -File |
            Where-Object {
                $_.FullName -notmatch '\\(\.git|\.venv|build|dist)\\' -and
                $textExtensions -contains $_.Extension
            } |
            ForEach-Object { $_.FullName.Substring($projectRoot.Length + 1) }
    }
    $findings = @()
    foreach ($relativePath in $tracked) {
        $path = Join-Path $projectRoot $relativePath
        if (-not (Test-Path -LiteralPath $path)) { continue }
        if ($textExtensions -notcontains [IO.Path]::GetExtension($path)) { continue }
        $content = Get-Content -Raw -Encoding utf8 -LiteralPath $path
        foreach ($entry in $patterns.GetEnumerator()) {
            foreach ($match in [regex]::Matches($content, $entry.Value)) {
                if (
                    $match.Value -match '@example\.invalid' -or
                    $match.Value -eq 'token=secret' -or
                    $match.Value -eq '13800138000' -or
                    $match.Value -match '^(.)\1{9,}$'
                ) {
                    continue
                }
                $findings += "$($entry.Key): $relativePath"
            }
        }
    }
    if ($findings.Count -gt 0) {
        $findings | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
        throw "Secret scan failed."
    }
    Write-Output "Secret scan passed: no QQ address, personal user path, credential literal, private token URL, or long private number."
}
finally {
    Pop-Location
}
