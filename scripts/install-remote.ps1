# [INPUT] Git, HTTPS (GitHub clone, uv/bun install scripts)
# [OUTPUT] Clones/updates repo, invokes scripts/install.ps1
# [POS] Windows one-liner entry (irm https://myrmagent.ai/install.ps1 | iex)
#
#   irm https://myrmagent.ai/install.ps1 | iex
#   irm https://raw.githubusercontent.com/Pursue-LLL/myrm-agent/main/scripts/install-remote.ps1 | iex
#
# Clones (or updates) the repo, then runs scripts/install.ps1.
#Requires -Version 5.1
$ErrorActionPreference = "Stop"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "Git is required. Install from https://git-scm.com/download/win"
    exit 1
}

$repoDir = if ($env:MYRM_INSTALL_DIR) { $env:MYRM_INSTALL_DIR } else { Join-Path $env:USERPROFILE ".myrm\myrm-agent" }
$repoUrl = if ($env:MYRM_REPO_URL) { $env:MYRM_REPO_URL } else { "https://github.com/Pursue-LLL/myrm-agent.git" }

if (Test-Path (Join-Path $repoDir "myrm-agent-server")) {
    Set-Location $repoDir
    if (Test-Path (Join-Path $repoDir ".git")) {
        git pull --ff-only 2>$null
    }
}
else {
    $parent = Split-Path -Parent $repoDir
    if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    if (Test-Path (Join-Path $repoDir ".git")) {
        Set-Location $repoDir
        git pull --ff-only 2>$null
    }
    else {
        git clone --depth 1 $repoUrl $repoDir
        Set-Location $repoDir
    }
}

$env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.bun\bin;$env:Path"
& (Join-Path $repoDir "scripts\install.ps1")
