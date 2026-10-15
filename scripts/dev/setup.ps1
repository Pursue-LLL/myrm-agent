# First-time setup after cloning myrm-agent (Windows).
# The harness (myrm-agent-harness\) lives in this repository; uv sync installs it as an editable path source.
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

Set-Location $ServerDir
uv python install 3.13

Write-Host "Server: uv sync (editable in-repo harness)..."
# Match scripts/lib/server_sync_flags.sh (PowerShell has no shared source; keep in sync manually).
uv sync --all-extras --no-extra matrix-e2ee --no-extra voice-tts --no-extra wechat-silk

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
