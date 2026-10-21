# Backend :8080 + frontend :3000 (Windows).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ServerDir = Join-Path $RepoRoot "myrm-agent-server"
$FrontendDir = Join-Path $RepoRoot "myrm-agent-frontend"
if (-not (Test-Path (Join-Path $ServerDir "run.py"))) {
    $ServerDir = Join-Path $RepoRoot "myrm-agent\myrm-agent-server"
    $FrontendDir = Join-Path $RepoRoot "myrm-agent\myrm-agent-frontend"
}

& (Join-Path (Split-Path -Parent $PSScriptRoot) "dev.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$StateDir = if ($env:MYRM_DEV_STATE_DIR) { $env:MYRM_DEV_STATE_DIR } else { Join-Path $env:USERPROFILE ".local\state\myrm-dev" }
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$fpid = Join-Path $StateDir "frontend.pid"
$flog = Join-Path $StateDir "frontend.log"

if (Test-Path $fpid) {
    $old = Get-Content $fpid -ErrorAction SilentlyContinue
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
        Write-Host "Open http://localhost:3000"
        exit 0
    }
    Remove-Item $fpid -Force -ErrorAction SilentlyContinue
}
Remove-Item (Join-Path $FrontendDir ".myrm-dev-frontend.pid") -Force -ErrorAction SilentlyContinue

Set-Location $FrontendDir
if (Test-Path $flog) {
    Clear-Content $flog
}
$p = Start-Process -FilePath "bun" -ArgumentList "run", "dev" -RedirectStandardOutput $flog -RedirectStandardError $flog -PassThru -WindowStyle Hidden
$p.Id | Set-Content $fpid
Write-Host "Frontend starting. Open http://localhost:3000 (log: $flog)"
