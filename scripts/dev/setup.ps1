# First-time setup after cloning myrm-agent (Windows).
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ServerDir = Join-Path $RepoRoot "myrm-agent-server"
$FrontendDir = Join-Path $RepoRoot "myrm-agent-frontend"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv not found. Install from https://docs.astral.sh/uv/"
}
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
    Write-Error "bun not found. Install from https://bun.sh"
}

Write-Host "Server: uv sync..."
Set-Location $ServerDir
uv python install 3.13
uv sync --all-extras

Write-Host "Installing browser runtime (patchright)..."
uv run patchright install chromium 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "Browser install failed (non-fatal). Run: uv run patchright install chromium" -ForegroundColor Yellow }

Write-Host "Frontend: bun install..."
Set-Location $FrontendDir
bun install

Write-Host ""
Write-Host "Setup complete."
Write-Host "  Backend:  myrm start"
Write-Host "  Frontend: cd myrm-agent-frontend; bun run dev  (separate terminal)"
