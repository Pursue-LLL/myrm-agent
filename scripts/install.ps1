# [INPUT]
# - Git, network (uv/bun installers)
# - resolve_agent_root layout (standalone vs parent/myrm-agent nested paths)
#
# [OUTPUT]
# - Installs uv/bun, syncs server, builds frontend, registers myrm.cmd
#
# [POS]
# Windows-native OSS bundle installer. Pair with install-remote.ps1 for irm | iex.
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

function Write-Info($msg) { Write-Host "i  $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "OK $msg" -ForegroundColor Green }
function Write-WarnMsg($msg) { Write-Host "!! $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "ERR $msg" -ForegroundColor Red; exit 1 }

function Resolve-AgentPaths {
    param([string]$Root)
    if (Test-Path (Join-Path $Root "myrm-agent-server\run.py")) {
        $script:AgentRoot = $Root
    }
    elseif (Test-Path (Join-Path $Root "myrm-agent\myrm-agent-server\run.py")) {
        $script:AgentRoot = Join-Path $Root "myrm-agent"
    }
    else {
        throw "myrm-agent-server not found under $Root. Clone https://github.com/Pursue-LLL/myrm-agent.git"
    }
    $script:ServerDir = Join-Path $AgentRoot "myrm-agent-server"
    $script:FrontendDir = Join-Path $AgentRoot "myrm-agent-frontend"
}

function Ensure-ProjectRoot {
    try {
        Resolve-AgentPaths -Root $ProjectRoot
        if (Test-Path (Join-Path $ServerDir "run.py")) {
            return
        }
    }
    catch {
        # fall through to clone/update
    }
    $repoDir = if ($env:MYRM_INSTALL_DIR) { $env:MYRM_INSTALL_DIR } else { Join-Path $env:USERPROFILE ".myrm\myrm-agent" }
    $repoUrl = if ($env:MYRM_REPO_URL) { $env:MYRM_REPO_URL } else { "https://github.com/Pursue-LLL/myrm-agent.git" }
    Write-Info "Preparing install at $repoDir ..."
    if (Test-Path (Join-Path $repoDir "myrm-agent-server")) {
        Set-Location $repoDir
        if (Test-Path (Join-Path $repoDir ".git")) {
            git pull --ff-only 2>$null
        }
    }
    else {
        $parent = Split-Path -Parent $repoDir
        if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        git clone --depth 1 $repoUrl $repoDir
        Set-Location $repoDir
    }
    $script:ProjectRoot = (Get-Location).Path
    $script:ScriptDir = Join-Path $ProjectRoot "scripts"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.bun\bin;$env:Path"
    Resolve-AgentPaths -Root $ProjectRoot
}

function Add-UserPathEntry {
    param([string]$Dir)
    if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Force -Path $Dir | Out-Null }
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$Dir*") {
        [Environment]::SetEnvironmentVariable("Path", "$Dir;$userPath", "User")
        $env:Path = "$Dir;$env:Path"
        Write-WarnMsg "Added $Dir to user PATH (open a new terminal if myrm is not found)."
    }
}

function Install-PackageManagers {
    Write-Info "Checking uv and bun ..."
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Info "Installing uv ..."
        Invoke-Expression ((Invoke-WebRequest -UseBasicParsing https://astral.sh/uv/install.ps1).Content)
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        Write-Ok "uv installed"
    }
    else {
        Write-Ok "uv: $(& uv --version)"
    }
    if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
        Write-Info "Installing bun ..."
        Invoke-Expression ((Invoke-WebRequest -UseBasicParsing https://bun.sh/install.ps1).Content)
        $env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
        Write-Ok "bun installed"
    }
    else {
        Write-Ok "bun: $(& bun --version)"
    }
}

function Verify-HarnessInstall {
    $py = Join-Path $ServerDir ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        throw "Missing $py after uv sync."
    }
    & $py -c "from myrm_agent_harness._distribution import assert_distribution_ready; assert_distribution_ready()"
    if ($LASTEXITCODE -ne 0) {
        throw "Harness distribution check failed. Ensure PyPI has myrm-agent-harness-core for this platform (win32-x64/arm64)."
    }
    Write-Ok "Harness distribution OK."
}

function Setup-Backend {
    Write-Info "Backend ($ServerDir) ..."
    Set-Location $ServerDir
    uv python install 3.13
    if ($LASTEXITCODE -ne 0) { throw "uv python install 3.13 failed." }
    Write-Info "uv sync (core deps) ..."
    uv sync
    if ($LASTEXITCODE -ne 0) {
        throw "Backend dependency sync failed."
    }
    Verify-HarnessInstall
    Write-Info "Optional native extras ..."
    uv pip install -e ".[advanced-tools]"
    if ($LASTEXITCODE -ne 0) {
        Write-WarnMsg "Advanced native extras failed; core server still usable (install VS Build Tools for C extensions)."
    }
    Set-Location $ProjectRoot
    Write-Ok "Backend ready."
}

function Setup-Frontend {
    Write-Info "Frontend ($FrontendDir) ..."
    Set-Location $FrontendDir
    bun install
    if ($LASTEXITCODE -ne 0) { throw "bun install failed." }
    bun run build
    if ($LASTEXITCODE -ne 0) { throw "bun run build failed." }
    Set-Location $ProjectRoot
    Write-Ok "Frontend ready."
}

function Setup-Cli {
    Write-Info "Registering global myrm CLI ..."
    $binDir = Join-Path $env:USERPROFILE ".local\bin"
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    $myrmPs1 = Join-Path $ScriptDir "myrm.ps1"
    $cmdPath = Join-Path $binDir "myrm.cmd"
    @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "$myrmPs1" %*
"@ | Set-Content -Path $cmdPath -Encoding ASCII
    Add-UserPathEntry -Dir $binDir
    Write-Ok "myrm CLI registered ($cmdPath)."
}

function Try-StartSearxng {
    if ($env:MYRM_AUTO_START_SEARXNG -ne "1") {
        Write-Info "Skipping SearXNG (set MYRM_AUTO_START_SEARXNG=1 to auto-start)."
        return
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-WarnMsg "Docker not found; cannot start SearXNG."
        return
    }
    $compose = Join-Path $ServerDir "docker-compose.yaml"
    if (-not (Test-Path $compose)) { return }
    Set-Location $ServerDir
    docker compose --profile search up -d
    if ($LASTEXITCODE -ne 0) {
        Write-WarnMsg "SearXNG start failed — configure search in Settings."
    }
    Set-Location $ProjectRoot
}

Write-Host ""
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "             MyrmAgent OSS bundle installer (Windows)" -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Fail "Git is required. Install from https://git-scm.com/download/win"
}

Set-Location $ProjectRoot
Ensure-ProjectRoot
Write-Ok "Detected OS: windows"
Install-PackageManagers
Setup-Backend
if ($env:MYRM_INSTALL_SKIP_FRONTEND -ne "1") {
    Setup-Frontend
}
else {
    Write-Info "Skipping frontend (MYRM_INSTALL_SKIP_FRONTEND=1)."
}
Setup-Cli
Try-StartSearxng

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host "Run: myrm start  ->  http://localhost:3000" -ForegroundColor Cyan
