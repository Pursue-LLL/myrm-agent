# Windows runtime smoke for a built desktop bundle: start the bundled Python sidecar (a PyInstaller
# one-folder tree) and the Next standalone server the way the Tauri shell does, then probe both over HTTP.
# Usage:
#   .\smoke-launch-runtime.ps1 -Dev
#   .\smoke-launch-runtime.ps1 -BundleDir <installed app dir>

[CmdletBinding()]
param (
    [switch]$Dev,
    [string]$BundleDir = "",
    [int]$ApiPort = 8080,
    [int]$WebuiPort = 3000,
    [string]$HostName = "127.0.0.1",
    [double]$PollIntervalSec = 0.5,
    # Same startup budget as the shell (BACKEND_STARTUP_TIMEOUT in python_backend.rs).
    [int]$ReadyTimeoutSec = 120,
    [int]$MinBinaryBytes = 1048576 # 1MB min threshold for the sidecar executable
)

$ErrorActionPreference = 'Stop'

function Fail {
    param ([string]$Message)
    Write-Error "[launch-smoke-win] FAIL: $Message"
    exit 1
}

if (-not $Dev -and [string]::IsNullOrWhiteSpace($BundleDir)) {
    Fail "Specify either -Dev or -BundleDir <path>"
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "../../..")

$BackendBin = $null
$FrontendDir = $null
$DataDir = $null
$BackendProc = $null
$FrontendProc = $null

function Assert-NonEmptyFile {
    param (
        [string]$Path,
        [string]$Label,
        [int]$MinBytes
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "$Label missing at $Path"
    }
    $size = (Get-Item -LiteralPath $Path).Length
    if ($size -lt $MinBytes) {
        Fail "$Label is too small ($size bytes < $MinBytes bytes): $Path"
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
        [string]$Label,
        [System.Diagnostics.Process]$Proc
    )
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    while ($watch.Elapsed.TotalSeconds -lt $ReadyTimeoutSec) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Host ("[launch-smoke-win] {0} ready in {1:N0}s ({2}) - Status: {3}" -f $Label, $watch.Elapsed.TotalSeconds, $Url, $response.StatusCode)
                return
            }
        } catch {
            # Not listening yet; keep polling until the process exits or the budget runs out.
        }
        if ($Proc.HasExited) {
            Fail "$Label process exited (code $($Proc.ExitCode)) before becoming ready ($Url)"
        }
        Start-Sleep -Milliseconds ([int]($PollIntervalSec * 1000))
    }
    Fail "$Label not ready after ${ReadyTimeoutSec}s ($Url)"
}

try {
    if ($Dev) {
        $BinariesDir = Join-Path $RepoRoot "myrm-agent-desktop/src-tauri/binaries"
        $BackendBin = Join-Path $BinariesDir "myrmagent-backend/myrmagent-backend.exe"
        $FrontendDir = Join-Path $RepoRoot "myrm-agent-frontend/.next/standalone/myrm-agent-frontend"
    } else {
        $ResolvedBundle = Resolve-Path $BundleDir -ErrorAction Stop
        # The resource layout is the contract: <resources>\binaries\myrmagent-backend\ and <resources>\frontend\.
        # Locating the sidecar folder first keeps this independent of where the installer puts resources.
        $SidecarDirs = @(Get-ChildItem -Path $ResolvedBundle -Recurse -Directory -Filter "myrmagent-backend" -ErrorAction SilentlyContinue |
            Where-Object { $_.Parent.Name -eq "binaries" })
        if ($SidecarDirs.Count -ne 1) {
            Fail "expected one binaries\myrmagent-backend folder under $ResolvedBundle, found $($SidecarDirs.Count)"
        }
        $ResourcesDir = $SidecarDirs[0].Parent.Parent.FullName
        $BackendBin = Join-Path $SidecarDirs[0].FullName "myrmagent-backend.exe"

        $ServerJs = Get-ChildItem -Path (Join-Path $ResourcesDir "frontend") -Recurse -Filter "server.js" -File -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $ServerJs) {
            Fail "Next standalone server.js not found under $ResourcesDir\frontend"
        }
        $FrontendDir = $ServerJs.DirectoryName
    }

    Write-Host "[launch-smoke-win] Checking sidecar and standalone runtime..."
    Assert-NonEmptyFile -Path $BackendBin -Label "Python Backend Sidecar (.exe)" -MinBytes $MinBinaryBytes
    if (-not (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $BackendBin) "_internal") -PathType Container)) {
        Fail "Backend sidecar has no _internal folder next to it (not a one-folder build): $BackendBin"
    }

    # A fresh data dir makes this the first launch of a new profile, the slowest path a user hits.
    $DataDir = Join-Path ([System.IO.Path]::GetTempPath()) ("myrm-smoke-" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $DataDir | Out-Null

    Write-Host "[launch-smoke-win] Starting backend: $BackendBin on port $ApiPort"
    # The shell is a GUI process without console handles, so the --noconsole sidecar starts with Python's standard
    # streams set to None. Start-Process (ShellExecute) hands down no handles either; a launch that inherited this
    # console's handles would hide every crash that depends on them.
    $env:DEPLOY_MODE = "local"
    $env:PORT = [string]$ApiPort
    $env:HOST = $HostName
    $env:MYRM_DATA_DIR = $DataDir
    try {
        $BackendProc = Start-Process -FilePath $BackendBin -WindowStyle Hidden -PassThru
    } finally {
        # The child has taken its environment; keep it out of the frontend launched below.
        Remove-Item Env:DEPLOY_MODE, Env:PORT, Env:HOST, Env:MYRM_DATA_DIR -ErrorAction SilentlyContinue
    }
    Write-Host "[launch-smoke-win] Backend spawned with PID: $($BackendProc.Id)"

    Wait-HttpOk -Url "http://${HostName}:${ApiPort}/health" -Label "Backend /health" -Proc $BackendProc

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

    Wait-HttpOk -Url "http://${HostName}:${WebuiPort}/" -Label "Next standalone WebUI" -Proc $FrontendProc

    Write-Host "[launch-smoke-win] All Windows runtime smoke checks passed successfully!"
} finally {
    if ($FrontendProc -and -not $FrontendProc.HasExited) {
        Kill-ProcessTree -ProcessId $FrontendProc.Id
    }
    if ($BackendProc -and -not $BackendProc.HasExited) {
        Kill-ProcessTree -ProcessId $BackendProc.Id
    }
    if ($DataDir -and (Test-Path -LiteralPath $DataDir)) {
        Remove-Item -LiteralPath $DataDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
