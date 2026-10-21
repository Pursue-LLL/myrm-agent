# Windows post-build runtime smoke: assert sidecar integrity, start bundled Python + Next standalone, and probe /health.
# Usage:
#   .\smoke-launch-runtime.ps1 -Dev
#   .\smoke-launch-runtime.ps1 -BundleDir <path/to/target_or_bundle>

[CmdletBinding()]
param (
    [switch]$Dev,
    [string]$BundleDir = "",
    [int]$ApiPort = 8080,
    [int]$WebuiPort = 3000,
    [string]$HostName = "127.0.0.1",
    [double]$PollIntervalSec = 0.5,
    [int]$MaxAttempts = 120,
    [int]$MinBinaryBytes = 1048576 # 1MB min threshold for binary sidecars
)

$ErrorActionPreference = 'Stop'

if (-not $Dev -and [string]::IsNullOrWhiteSpace($BundleDir)) {
    Write-Error "[launch-smoke-win] Specify either -Dev or -BundleDir <path>"
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "../../..")

$BackendBin = $null
$AgentRunnerBin = $null
$FrontendDir = $null
$BackendProc = $null
$FrontendProc = $null

function Assert-NonEmptyFile {
    param (
        [string]$Path,
        [string]$Label,
        [int]$MinBytes
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Write-Error "[launch-smoke-win] $Label missing at $Path"
        exit 1
    }
    $size = (Get-Item -LiteralPath $Path).Length
    if ($size -lt $MinBytes) {
        Write-Error "[launch-smoke-win] $Label is too small ($size bytes < $MinBytes bytes): $Path"
        exit 1
    }
    Write-Host "[launch-smoke-win] OK: $Label ($size bytes) -> $Path"
}

function Kill-ProcessTree {
    param ([int]$ProcessId)
    if ($ProcessId -gt 0) {
        Write-Host "[launch-smoke-win] Terminating process tree PID $ProcessId..."
        try {
            taskkill.exe /F /T /PID $ProcessId 2>$null | Out-Null
        } catch {
            # Ignore if already exited
        }
    }
}

function Wait-HttpOk {
    param (
        [string]$Url,
        [string]$Label
    )
    $attempts = 0
    while ($attempts -lt $MaxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Host "[launch-smoke-win] $Label is ready ($Url) - Status: $($response.StatusCode)"
                return
            }
        } catch {
            # In progress
        }
        $attempts++
        Start-Sleep -Seconds $PollIntervalSec
    }
    Write-Error "[launch-smoke-win] $Label not ready after $MaxAttempts attempts ($Url)"
    exit 1
}

try {
    if ($Dev) {
        $BinariesDir = Join-Path $RepoRoot "myrm-agent-desktop/src-tauri/binaries"
        $BackendMatch = Get-ChildItem -Path $BinariesDir -Filter "myrmagent-backend*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($BackendMatch) {
            $BackendBin = $BackendMatch.FullName
        } else {
            $BackendBin = Join-Path $BinariesDir "myrmagent-backend-x86_64-pc-windows-msvc.exe"
        }

        $AgentRunnerMatch = Get-ChildItem -Path $BinariesDir -Filter "agent-runner*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($AgentRunnerMatch) {
            $AgentRunnerBin = $AgentRunnerMatch.FullName
        }

        $FrontendDir = Join-Path $RepoRoot "myrm-agent-frontend/.next/standalone/myrm-agent-frontend"
        if (-not (Test-Path -LiteralPath $FrontendDir)) {
            $FrontendDir = Join-Path $RepoRoot "myrm-agent-frontend/.next/standalone"
        }
    } else {
        $ResolvedBundle = Resolve-Path $BundleDir -ErrorAction Stop
        $BackendMatch = Get-ChildItem -Path $ResolvedBundle -Recurse -Filter "myrmagent-backend*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $BackendMatch) {
            Write-Error "[launch-smoke-win] No myrmagent-backend*.exe found under $ResolvedBundle"
            exit 1
        }
        $BackendBin = $BackendMatch.FullName

        $AgentRunnerMatch = Get-ChildItem -Path $ResolvedBundle -Recurse -Filter "agent-runner*.exe" -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($AgentRunnerMatch) {
            $AgentRunnerBin = $AgentRunnerMatch.FullName
        }

        $ServerJs = Get-ChildItem -Path $ResolvedBundle -Recurse -Filter "server.js" -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($ServerJs) {
            $FrontendDir = $ServerJs.DirectoryName
        }
    }

    Write-Host "[launch-smoke-win] Checking sidecar binaries and standalone runtime..."
    Assert-NonEmptyFile -Path $BackendBin -Label "Python Backend Sidecar (.exe)" -MinBytes $MinBinaryBytes

    if ($AgentRunnerBin -and (Test-Path -LiteralPath $AgentRunnerBin)) {
        Assert-NonEmptyFile -Path $AgentRunnerBin -Label "Agent Runner Sidecar (.exe)" -MinBytes $MinBinaryBytes
    }

    # Launch Backend Sidecar
    Write-Host "[launch-smoke-win] Starting backend: $BackendBin on port $ApiPort"
    $BackendPsi = New-Object System.Diagnostics.ProcessStartInfo
    $BackendPsi.FileName = $BackendBin
    $BackendPsi.UseShellExecute = $false
    $BackendPsi.EnvironmentVariables["DEPLOY_MODE"] = "local"
    $BackendPsi.EnvironmentVariables["PORT"] = [string]$ApiPort
    $BackendPsi.EnvironmentVariables["HOST"] = $HostName

    $BackendProc = [System.Diagnostics.Process]::Start($BackendPsi)
    Write-Host "[launch-smoke-win] Backend spawned with PID: $($BackendProc.Id)"

    Wait-HttpOk -Url "http://${HostName}:${ApiPort}/health" -Label "Backend /health"

    # Launch Frontend Standalone if present
    if ($FrontendDir -and (Test-Path -LiteralPath (Join-Path $FrontendDir "server.js"))) {
        $ServerJsPath = Join-Path $FrontendDir "server.js"
        Assert-NonEmptyFile -Path $ServerJsPath -Label "Next standalone server.js" -MinBytes 1024

        Write-Host "[launch-smoke-win] Starting Next.js standalone on port $WebuiPort"
        $FrontendPsi = New-Object System.Diagnostics.ProcessStartInfo
        $FrontendPsi.FileName = "node.exe"
        $FrontendPsi.Arguments = "server.js"
        $FrontendPsi.WorkingDirectory = $FrontendDir
        $FrontendPsi.UseShellExecute = $false
        $FrontendPsi.EnvironmentVariables["PORT"] = [string]$WebuiPort
        $FrontendPsi.EnvironmentVariables["HOSTNAME"] = $HostName
        $FrontendPsi.EnvironmentVariables["API_PORT"] = [string]$ApiPort

        $FrontendProc = [System.Diagnostics.Process]::Start($FrontendPsi)
        Write-Host "[launch-smoke-win] Frontend spawned with PID: $($FrontendProc.Id)"

        Wait-HttpOk -Url "http://${HostName}:${WebuiPort}/" -Label "Next standalone WebUI"
    } else {
        Write-Host "[launch-smoke-win] Note: Frontend standalone directory not found or skipped in this mode."
    }

    Write-Host "[launch-smoke-win] All Windows runtime smoke checks passed successfully!"
} finally {
    if ($FrontendProc -and -not $FrontendProc.HasExited) {
        Kill-ProcessTree -ProcessId $FrontendProc.Id
    }
    if ($BackendProc -and -not $BackendProc.HasExited) {
        Kill-ProcessTree -ProcessId $BackendProc.Id
    }
}
