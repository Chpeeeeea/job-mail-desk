param(
  [string]$OutputDirectory = ".\docs\assets",
  [int]$ScaleFactor = 2
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$uiRoot = Join-Path $repoRoot "src\job_mail_desk\ui"
$outputRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputDirectory))
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) "jobmaildesk-readme-preview"
$edgeCandidates = @(
  "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
  "C:\Program Files\Google\Chrome\Application\chrome.exe"
)
$browser = $edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $browser) {
  throw "Microsoft Edge or Google Chrome is required to capture README previews."
}

New-Item -ItemType Directory -Force -Path $outputRoot, $tempRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $uiRoot "style.css") -Destination $tempRoot -Force
Copy-Item -LiteralPath (Join-Path $uiRoot "app.js") -Destination $tempRoot -Force

$demoJson = Get-Content -LiteralPath (Join-Path $repoRoot "docs\assets\readme-demo.json") -Raw -Encoding UTF8
$mockApi = @"
    <script>
      const demoPayload = $demoJson;
      const cloneDemo = () => JSON.parse(JSON.stringify(demoPayload));
      window.pywebview = { api: {
        get_dashboard: async () => cloneDemo(),
        get_app_settings: async () => ({
          credential_configured: true,
          email: "demo@example.com",
          poll_minutes: 10,
          lookback_days: 3,
          obsidian_enabled: true,
          obsidian_output: "D:\\Obsidian\\job-tasks.md",
          progress_enabled: true,
          progress_output: "D:\\Obsidian\\job-progress.md",
          progress_source: "D:\\Obsidian\\application-ledger.md",
          updates_enabled: false,
          update_channel: "preview",
          app_version: "0.6.0"
        }),
        get_dictionary_status: async () => ({
          counts: { companies: 520, programs: 129, roles: 2825, mail_templates: 4 },
          user_dictionary_enabled: false
        }),
        get_update_status: async () => ({ state: "idle", current_version: "0.6.0" }),
        maybe_check_for_updates: async () => null,
        set_editor_mode: async () => null,
        set_capsule: async () => null,
        update_status: async () => cloneDemo(),
        snooze: async () => cloneDemo(),
        open_source: async () => null,
        open_obsidian: async () => null,
        open_research: async () => null,
        trigger_scan: async () => null
      }};
    </script>
"@

$viewScript = @'
    <script>
      setTimeout(() => {
        const requested = new URLSearchParams(location.search).get("view") || "today";
        const tab = document.querySelector(`[data-view="${requested}"]`);
        if (tab) tab.click();
        if (requested === "progress") {
          setTimeout(() => document.querySelector(".progress-overview button")?.click(), 120);
        }
        if (requested === "settings") {
          setTimeout(() => window.openSettingsDialog?.(false), 120);
        }
      }, 900);
    </script>
'@

$source = Get-Content -LiteralPath (Join-Path $uiRoot "index.html") -Raw -Encoding UTF8
$source = $source.Replace('    <script src="app.js"></script>', "$mockApi`n    <script src=`"app.js`"></script>`n$viewScript")
[IO.File]::WriteAllText(
  (Join-Path $tempRoot "index.html"),
  $source,
  [Text.UTF8Encoding]::new($false)
)

$pageUri = ([Uri](Join-Path $tempRoot "index.html")).AbsoluteUri
$captures = @(
  @{ View = "today"; File = "jobmaildesk-today.png"; Height = 620 },
  @{ View = "progress"; File = "jobmaildesk-progress.png"; Height = 900 },
  @{ View = "review"; File = "jobmaildesk-review.png"; Height = 620 },
  @{ View = "week"; File = "jobmaildesk-week.png"; Height = 760 },
  @{ View = "month"; File = "jobmaildesk-calendar.png"; Height = 760 }
  @{ View = "settings"; File = "jobmaildesk-settings.png"; Height = 1080 }
)

foreach ($capture in $captures) {
  $target = Join-Path $outputRoot $capture.File
  $browserArguments = @(
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--force-device-scale-factor=$ScaleFactor",
    "--window-size=720,$($capture.Height)",
    "--virtual-time-budget=2500",
    "--screenshot=$target",
    "${pageUri}?view=$($capture.View)"
  )
  & $browser @browserArguments | Out-Null
  if (-not (Test-Path -LiteralPath $target)) {
    throw "Preview capture failed: $target"
  }
}

$obsidianDemo = Join-Path $repoRoot "docs\assets\obsidian-progress-demo.html"
$obsidianTarget = Join-Path $outputRoot "jobmaildesk-obsidian-progress.png"
& $browser @(
  "--headless=new",
  "--disable-gpu",
  "--hide-scrollbars",
  "--force-device-scale-factor=1",
  "--window-size=1440,900",
  "--screenshot=$obsidianTarget",
  ([Uri]$obsidianDemo).AbsoluteUri
) | Out-Null
if (-not (Test-Path -LiteralPath $obsidianTarget)) {
  throw "Obsidian progress preview capture failed: $obsidianTarget"
}

Write-Host "README previews written to $outputRoot"
