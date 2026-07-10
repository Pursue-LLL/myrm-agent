# First-time setup after cloning myrm-agent (Windows).
# Monorepo (sibling myrm-agent-harness): editable harness via install_harness.sh (Git Bash).
# OSS-only clone: PyPI harness via uv sync.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ServerDir = Join-Path $RepoRoot "myrm-agent-server"
$FrontendDir = Join-Path $RepoRoot "myrm-agent-frontend"
$MonorepoRoot = Split-Path $RepoRoot -Parent
$HarnessSrc = Join-Path $MonorepoRoot "myrm-agent-harness\src\myrm_agent_harness"
$HarnessInstaller = Join-Path $MonorepoRoot "scripts\maintainer\install_harness.sh"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv not found. Install from https://docs.astral.sh/uv/"
}
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
    Write-Error "bun not found. Install from https://bun.sh"
}

Set-Location $ServerDir
uv python install 3.13

if ((Test-Path $HarnessSrc) -and (Test-Path $HarnessInstaller)) {
    Write-Host "Server: monorepo harness detected -> editable install..."
    if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
        Write-Error "Monorepo requires Git Bash for harness install. Run from open-perplexity root: ./myrm setup"
    }
    bash $HarnessInstaller
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "Server: uv sync (PyPI harness)..."
    uv sync --all-extras
}

Write-Host "Installing browser runtime (patchright)..."
uv run patchright install chromium 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "Browser install failed (non-fatal). Run: uv run patchright install chromium" -ForegroundColor Yellow }

Write-Host "Frontend: bun install..."
Set-Location $FrontendDir
bun install

$EnsureSwc = Join-Path $RepoRoot "scripts\dev\ensure-next-native-swc.sh"
if ((Test-Path $EnsureSwc) -and (Get-Command bash -ErrorAction SilentlyContinue)) {
    bash $EnsureSwc
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "  Backend:  myrm start"
Write-Host "  Frontend: cd myrm-agent-frontend; bun run dev  (separate terminal)"
