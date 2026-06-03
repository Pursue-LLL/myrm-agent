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
