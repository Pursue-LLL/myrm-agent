# Backend only :8080 (Windows).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ServerDir = Join-Path $RepoRoot "myrm-agent-server"
if (-not (Test-Path (Join-Path $ServerDir "run.py"))) {
    $ServerDir = Join-Path $RepoRoot "myrm-agent\myrm-agent-server"
}
$StateDir = if ($env:MYRM_DEV_STATE_DIR) { $env:MYRM_DEV_STATE_DIR } else { Join-Path $env:USERPROFILE ".local\state\myrm-dev" }
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
$PidFile = Join-Path $StateDir "backend.pid"
$LogFile = Join-Path $StateDir "backend.log"
$HealthUrl = "http://127.0.0.1:8080/api/v1/health"

function Test-MonorepoHarnessEditable {
    param([string]$ServerDirPath, [string]$PythonExe)

    if ($env:MYRM_SKIP_HARNESS_EDITABLE_CHECK -eq "1") {
        return
    }

    $agentRoot = Split-Path $ServerDirPath -Parent
    $monorepoRoot = Split-Path $agentRoot -Parent
    $harnessSrc = Join-Path $monorepoRoot "myrm-agent-harness\src\myrm_agent_harness"
    if (-not (Test-Path $harnessSrc)) {
        return
    }

    $expectedSrc = (Resolve-Path $harnessSrc).Path
    $check = & $PythonExe -c @"
import pathlib
import myrm_agent_harness
from myrm_agent_harness._distribution import get_distribution_mode
from myrm_agent_harness.agent.artifacts.ui_registry import bind_run_message_id  # noqa: F401
pkg = pathlib.Path(myrm_agent_harness.__file__).resolve().parent
print(get_distribution_mode().value)
print(pkg)
"@
    if (-not $check -or $check.Count -lt 2) {
        Write-Error @"
Monorepo harness source present but myrm_agent_harness import failed.
Run: myrm setup (or monorepo harness install) then retry.
If a stale backend is running:  myrm stop
"@
        exit 1
    }

    $mode = $check[0]
    $pkgDir = $check[1]
    if ($mode -ne "source" -or $pkgDir -ne $expectedSrc) {
        Write-Error @"
Server venv harness is not monorepo editable source (mode=$mode).
pytest may pass while live agent-stream misses ui_update (stale wheel).
Fix: monorepo harness install then myrm stop and restart.
PyPI consumer test only:  MYRM_SKIP_HARNESS_EDITABLE_CHECK=1 myrm dev
"@
        exit 1
    }
}

if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Host "Backend already running (pid $oldPid)"
        $pyRunning = Join-Path $ServerDir ".venv\Scripts\python.exe"
        if (Test-Path $pyRunning) {
            Test-MonorepoHarnessEditable -ServerDirPath $ServerDir -PythonExe $pyRunning
        }
        exit 0
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}
Remove-Item (Join-Path $ServerDir ".myrm-dev-backend.pid") -Force -ErrorAction SilentlyContinue

$py = Join-Path $ServerDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Run myrm setup first"
    exit 1
}

$env:DEPLOY_MODE = "local"
$env:HOST = "127.0.0.1"
$env:PORT = "8080"

Test-MonorepoHarnessEditable -ServerDirPath $ServerDir -PythonExe $py

Set-Location $ServerDir
if (Test-Path $LogFile) {
    Clear-Content $LogFile
}
$p = Start-Process -FilePath $py -ArgumentList "run.py" -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile -PassThru -WindowStyle Hidden
$p.Id | Set-Content $PidFile

for ($i = 0; $i -lt 45; $i++) {
    try {
        Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2 | Out-Null
        Write-Host "Backend http://127.0.0.1:8080 (log: $LogFile)"
        exit 0
    }
    catch { Start-Sleep -Seconds 1 }
}
Write-Error "Backend not ready. See $LogFile"
exit 1
