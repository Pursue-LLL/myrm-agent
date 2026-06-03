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
    Write-Host "  start | stop | status | update"
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

function Start-Server {
    Set-Location $ServerDir
    $env:DEPLOY_MODE = "local"
    $env:WEBUI_MODE = "true"
    $venvPy = Join-Path $ServerDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        Write-Host "Starting server via $venvPy"
        & $venvPy run.py --webui
        exit $LASTEXITCODE
    }
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Write-Host "Starting server via uv run run.py"
        uv run run.py --webui
        exit $LASTEXITCODE
    }
    Write-Error "No .venv python or uv found. Re-run scripts/install.ps1"
    exit 1
}

Resolve-AgentPaths -Root $ProjectRoot
$composeFile = Join-Path $ServerDir "docker-compose.yaml"

switch ($Command) {
    "start" { Start-Server }
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
