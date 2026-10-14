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

# The server venv must import the in-repo harness (editable path source); a stale venv that still
# holds an installed wheel would make tests pass while the live backend runs old harness code.
function Test-HarnessEditable {
    param([string]$ServerDirPath, [string]$PythonExe)

    $harnessSrc = Join-Path (Split-Path $ServerDirPath -Parent) "myrm-agent-harness\src\myrm_agent_harness"
    if (-not (Test-Path $harnessSrc)) {
        Write-Error "Harness source not found at $harnessSrc."
        exit 1
    }

    $expectedSrc = (Resolve-Path $harnessSrc).Path
    $pkgDir = & $PythonExe -c @"
import pathlib
import myrm_agent_harness
from myrm_agent_harness.api import create_skill_agent  # noqa: F401
print(pathlib.Path(myrm_agent_harness.__file__).resolve().parent)
"@
    if (-not $pkgDir) {
        Write-Error @"
myrm_agent_harness import failed in the server venv.
Run: myrm setup (or: cd myrm-agent-server; uv sync) then retry.
If a stale backend is running:  myrm stop
"@
        exit 1
    }

    if ($pkgDir -ne $expectedSrc) {
        Write-Error @"
Server venv harness is not the in-repo editable source.
pytest may pass while live agent-stream misses ui_update (stale wheel).
Fix: cd myrm-agent-server; uv sync then myrm stop and restart.
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
            Test-HarnessEditable -ServerDirPath $ServerDir -PythonExe $pyRunning
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

Test-HarnessEditable -ServerDirPath $ServerDir -PythonExe $py

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
