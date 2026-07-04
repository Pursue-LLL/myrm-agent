# Backend only :8080 (Windows).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ServerDir = Join-Path $RepoRoot "myrm-agent-server"
if (-not (Test-Path (Join-Path $ServerDir "run.py"))) {
    $ServerDir = Join-Path $RepoRoot "myrm-agent\myrm-agent-server"
}
$PidFile = Join-Path $ServerDir ".myrm-dev-backend.pid"
$LogFile = Join-Path $ServerDir ".myrm-dev-backend.log"
$HealthUrl = "http://127.0.0.1:8080/api/v1/health"

if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($oldPid -and (Get-Process -Id $oldPid -ErrorAction SilentlyContinue)) {
        Write-Host "Backend already running (pid $oldPid)"
        exit 0
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$py = Join-Path $ServerDir ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Run myrm setup first"
    exit 1
}

$env:DEPLOY_MODE = "local"
$env:HOST = "127.0.0.1"
$env:PORT = "8080"

$agentRoot = Split-Path $ServerDir -Parent
$monorepoRoot = Split-Path $agentRoot -Parent
$harnessSrc = Join-Path $monorepoRoot "myrm-agent-harness\src\myrm_agent_harness"
if (Test-Path $harnessSrc) {
    $expectedSrc = (Resolve-Path $harnessSrc).Path
    $check = & $py -c @"
import pathlib
import myrm_agent_harness
from myrm_agent_harness._distribution import get_distribution_mode
from myrm_agent_harness.agent.artifacts.ui_registry import bind_run_message_id  # noqa: F401
pkg = pathlib.Path(myrm_agent_harness.__file__).resolve().parent
print(get_distribution_mode().value)
print(pkg)
"@ 2>$null
    if ($check -and $check.Count -ge 2) {
        $mode = $check[0]
        $pkgDir = $check[1]
        if ($mode -ne "source" -or $pkgDir -ne $expectedSrc) {
            Write-Warning "Server venv harness is not monorepo editable source (mode=$mode)."
            Write-Warning "pytest may pass while live agent-stream misses ui_update. Fix: ./myrm harness install"
        }
    }
}

Set-Location $ServerDir
$p = Start-Process -FilePath $py -ArgumentList "run.py" -RedirectStandardOutput $LogFile -RedirectStandardError $LogFile -PassThru -WindowStyle Hidden
$p.Id | Set-Content $PidFile

for ($i = 0; $i -lt 45; $i++) {
    try {
        Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2 | Out-Null
        Write-Host "Backend http://127.0.0.1:8080"
        exit 0
    }
    catch { Start-Sleep -Seconds 1 }
}
Write-Error "Backend not ready. See $LogFile"
exit 1
