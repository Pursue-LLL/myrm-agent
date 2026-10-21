# Start myrm-agent-server on Windows (prefer .venv python over uv re-resolve).
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RunArgs
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ServerDir = Join-Path $RepoRoot "myrm-agent-server"
if (-not (Test-Path (Join-Path $ServerDir "run.py"))) {
    Write-Error "myrm-agent-server not found under $RepoRoot"
    exit 1
}
Set-Location $ServerDir

$Py = Join-Path $ServerDir ".venv\Scripts\python.exe"
if (Test-Path $Py) {
    Write-Host "Starting server via $Py (dev venv, no uv re-resolve)"
    & $Py run.py @RunArgs
    exit $LASTEXITCODE
}

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "No .venv yet — starting via uv run run.py"
    uv run run.py @RunArgs
    exit $LASTEXITCODE
}

Write-Error "Neither $Py nor uv found. Run: .\scripts\dev\setup.sh (Git Bash) or scripts\install.ps1"
exit 1
