# [INPUT] install.ps1 output (.venv, uv, docker compose)
# [OUTPUT] myrm start|stop|status|update|searxng *
# [POS] Windows CLI; registered as %USERPROFILE%\.local\bin\myrm.cmd
#Requires -Version 5.1
param(
    [Parameter(Position = 0)]
    [string]$Command,
    [Parameter(Position = 1)]
    [string]$SubCommand
)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

function Resolve-AgentPaths {
    param([string]$Root)
    if (Test-Path (Join-Path $Root "myrm-agent-server\run.py")) {
        $script:AgentRoot = $Root
    }
    elseif (Test-Path (Join-Path $Root "myrm-agent\myrm-agent-server\run.py")) {
        $script:AgentRoot = Join-Path $Root "myrm-agent"
    }
    else {
        Write-Error "myrm-agent-server not found under $Root"
        exit 1
    }
    $script:ServerDir = Join-Path $AgentRoot "myrm-agent-server"
    $script:FrontendDir = Join-Path $AgentRoot "myrm-agent-frontend"
}

function Show-Help {
    Write-Host "MyrmAgent CLI" -ForegroundColor Cyan
    Write-Host "Usage: myrm <command>"
    Write-Host "  setup    First-time install"
    Write-Host "  dev      Backend only (:8080)"
    Write-Host "  start    Backend + frontend (:8080 + :3000)"
    Write-Host "  stop | status | update"
    Write-Host "  doctor   Browser & environment diagnostics"
    Write-Host "  searxng start | stop | status"
}

function Test-CnNetwork {
    if ($env:MYRM_USE_CN_MIRROR -eq "1") { return $true }
    if ($env:MYRM_NO_CN_MIRROR -eq "1") { return $false }
    if ($env:UV_DEFAULT_INDEX) { return $false }
    $tz = [System.TimeZoneInfo]::Local.Id
    $cnZones = @("China Standard Time", "Asia/Shanghai", "Asia/Chongqing")
    if ($cnZones -notcontains $tz) { return $false }
    try {
        $null = Invoke-WebRequest -Uri "https://pypi.org/simple/" -TimeoutSec 3 -UseBasicParsing -Method Head
        return $false
    }
    catch {
        return $true
    }
}

function Set-CnMirrors {
    $env:UV_DEFAULT_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
    $env:BUN_CONFIG_REGISTRY = "https://registry.npmmirror.com"
    $env:PLAYWRIGHT_DOWNLOAD_HOST = "https://cdn.npmmirror.com/binaries/playwright"
    Write-Host "[CN] Using domestic mirrors for acceleration" -ForegroundColor Cyan
}

function Require-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "Docker required"
        exit 1
    }
    $compose = Join-Path $ServerDir "docker-compose.yaml"
    if (-not (Test-Path $compose)) {
        Write-Error "Missing compose file"
        exit 1
    }
}

function Get-MyrmProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match 'myrm-agent-server[\\/].*run\.py' -or
                $_.CommandLine -match 'next dev' -or
                $_.CommandLine -match 'bun run dev'
            )
        }
}

Resolve-AgentPaths -Root $ProjectRoot
$composeFile = Join-Path $ServerDir "docker-compose.yaml"

switch ($Command) {
    "setup" {
        $setup = Join-Path $ScriptDir "dev\setup.ps1"
        if (-not (Test-Path $setup)) {
            Write-Error "Missing $setup"
            exit 1
        }
        & $setup
        exit $LASTEXITCODE
    }
    "dev" {
        $dev = Join-Path $ScriptDir "dev\dev.ps1"
        if (-not (Test-Path $dev)) { Write-Error "Missing $dev"; exit 1 }
        & $dev
        exit $LASTEXITCODE
    }
    "start" {
        $start = Join-Path $ScriptDir "dev\start.ps1"
        if (-not (Test-Path $start)) { Write-Error "Missing $start"; exit 1 }
        & $start
        exit $LASTEXITCODE
    }
    "stop" {
        $StateDir = if ($env:MYRM_DEV_STATE_DIR) { $env:MYRM_DEV_STATE_DIR } else { Join-Path $env:USERPROFILE ".local\state\myrm-dev" }
        $fpid = Join-Path $StateDir "frontend.pid"
        $bpid = Join-Path $StateDir "backend.pid"
        if (Test-Path $fpid) {
            $fp = Get-Content $fpid -ErrorAction SilentlyContinue
            if ($fp) { Stop-Process -Id $fp -Force -ErrorAction SilentlyContinue }
            Remove-Item $fpid -Force -ErrorAction SilentlyContinue
        }
        if (Test-Path $bpid) {
            $bp = Get-Content $bpid -ErrorAction SilentlyContinue
            if ($bp) { Stop-Process -Id $bp -Force -ErrorAction SilentlyContinue }
            Remove-Item $bpid -Force -ErrorAction SilentlyContinue
        }
        Remove-Item (Join-Path $FrontendDir ".myrm-dev-frontend.pid") -Force -ErrorAction SilentlyContinue
        Remove-Item (Join-Path $ServerDir ".myrm-dev-backend.pid") -Force -ErrorAction SilentlyContinue
        $port = if ($env:PORT) { $env:PORT } else { "8080" }
        try { Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/v1/system/shutdown" -Method Post -TimeoutSec 3 -UseBasicParsing 2>$null; Start-Sleep -Seconds 3 } catch {}
        $procs = Get-MyrmProcesses
        if ($procs) {
            $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 2
            $procs = Get-MyrmProcesses
            if ($procs) {
                $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            }
            Write-Host "Stopped Myrm processes."
        }
        else {
            Write-Host "Not running."
        }
    }
    "status" {
        $procs = Get-MyrmProcesses
        if ($procs) {
            $procs | ForEach-Object { Write-Host "PID $($_.ProcessId): $($_.Name)" }
        }
        else {
            Write-Host "Not running."
        }
    }
    "update" {
        if (Test-CnNetwork) { Set-CnMirrors }
        Set-Location $ProjectRoot
        git pull --ff-only
        if ($LASTEXITCODE -ne 0) { Write-Error "git pull failed"; exit 1 }
        Set-Location $ServerDir
        uv sync --all-extras
        if ($LASTEXITCODE -ne 0) { Write-Error "Backend sync failed"; exit 1 }
        uv run patchright install chromium 2>$null
        Set-Location $FrontendDir
        bun install
        if ($LASTEXITCODE -ne 0) { Write-Error "bun install failed"; exit 1 }
        bun run build
        if ($LASTEXITCODE -ne 0) { Write-Error "Frontend build failed"; exit 1 }
        Write-Host "Update complete." -ForegroundColor Green
    }
    "doctor" {
        $py = Join-Path $ServerDir ".venv\Scripts\python.exe"
        if (-not (Test-Path $py)) {
            Write-Error ".venv not found. Run: myrm setup"
            exit 1
        }
        & $py -c "import asyncio; from myrm_agent_harness.toolkits.browser.doctor import run_doctor, format_report; r = asyncio.run(run_doctor()); print(format_report(r)); exit(0 if r.overall_healthy else 1)"
        exit $LASTEXITCODE
    }
    "searxng" {
        Require-Docker
        Set-Location $ServerDir
        switch ($SubCommand) {
            "start" {
                docker compose --profile search up -d
                Write-Host "SearXNG: http://127.0.0.1:8081" -ForegroundColor Green
            }
            "stop" { docker compose --profile search down }
            "status" { docker compose --profile search ps }
            default { Show-Help; exit 1 }
        }
    }
    default {
        if ($Command -in @("", "help", "-h", "--help")) {
            Show-Help
        }
        else {
            Show-Help
            exit 1
        }
    }
}
