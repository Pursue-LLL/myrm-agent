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
        $fpid = Join-Path $FrontendDir ".myrm-dev-frontend.pid"
        if (Test-Path $fpid) {
            $fp = Get-Content $fpid -ErrorAction SilentlyContinue
            if ($fp) { Stop-Process -Id $fp -Force -ErrorAction SilentlyContinue }
            Remove-Item $fpid -Force -ErrorAction SilentlyContinue
        }
        $bpid = Join-Path $ServerDir ".myrm-dev-backend.pid"
        if (Test-Path $bpid) {
            $bp = Get-Content $bpid -ErrorAction SilentlyContinue
            if ($bp) { Stop-Process -Id $bp -Force -ErrorAction SilentlyContinue }
            Remove-Item $bpid -Force -ErrorAction SilentlyContinue
        }
        $procs = Get-MyrmProcesses
        if ($procs) {
            $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
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
        Set-Location $ProjectRoot
        git pull --ff-only
        Set-Location $ServerDir
        uv sync --all-extras
        uv run patchright install chromium 2>$null
        Set-Location $FrontendDir
        bun install
        bun run build
        Write-Host "Update complete."
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
