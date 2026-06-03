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
    Write-Host "  setup              First-time deps (uv sync + bun install)"
    Write-Host "  dev                Backend :8080 in background"
    Write-Host "  start              Dev backend :8080 (foreground)"
    Write-Host "  start -Standalone  All-in-one WebUI :25808"
    Write-Host "  stop | status | update"
    Write-Host "  searxng start | stop | status"
    Write-Host ""
    Write-Host "Typical dev: myrm start; cd myrm-agent-frontend; bun run dev"
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

function Start-Server {
    param([switch]$Standalone)

    Set-Location $ServerDir
    $env:DEPLOY_MODE = "local"
    $runArgs = @()
    if ($Standalone) {
        $runArgs += "--webui"
    }
    else {
        $env:HOST = "127.0.0.1"
        $env:PORT = "8080"
    }
    $venvPy = Join-Path $ServerDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        Write-Host "Starting server via $venvPy"
        & $venvPy run.py @runArgs
        exit $LASTEXITCODE
    }
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "Starting server via uv run --no-sync run.py"
        uv run --no-sync run.py @runArgs
        exit $LASTEXITCODE
    }
    Write-Error "No .venv python or uv found. Re-run scripts/install.ps1"
    exit 1
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
        $standalone = ($SubCommand -in @("--standalone", "--webui", "-Standalone"))
        if ($standalone) {
            Write-Host "Starting standalone WebUI (backend :25808)..."
            Start-Server -Standalone
        }
        else {
            Write-Host "Starting dev backend (http://127.0.0.1:8080)..."
            Write-Host "Frontend: cd myrm-agent-frontend; bun run dev  ->  http://localhost:3000"
            Start-Server
        }
    }
    "stop" {
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
        Set-Location $FrontendDir
        bun install
        bun run build
        Write-Host "Update complete."
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
