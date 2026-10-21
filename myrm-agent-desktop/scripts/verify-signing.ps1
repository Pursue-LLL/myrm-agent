<#
.SYNOPSIS
    Post-build Windows Authenticode verifier for MyrmAgent installers.

.DESCRIPTION
    Runs inside the GitHub Actions release workflow after `tauri-action`
    produces .exe and .msi installers. For each artifact, executes:

        signtool verify /pa /v /tw <artifact>

    /pa  — use Default Authentication Verification Policy (the same policy
           Windows uses when actually launching the installer).
    /v   — verbose output: signer chain, timestamp, hash algorithm.
    /tw  — warn (not fail) if no timestamp; combined with manual check below
           we still fail when timestamp is absent, but get the warning context.

    Exits with non-zero status equal to failure count when any check fails;
    full verification log is also written to -LogPath for artifact upload.

.PARAMETER SearchRoot
    Directory roots to scan for .exe / .msi artifacts (can be repeated).

.PARAMETER Artifact
    Explicit artifact paths to verify (can be repeated, mutually exclusive
    with -SearchRoot semantics — both can coexist).

.PARAMETER LogPath
    File path for the full verification log (used as CI artifact).

.PARAMETER ListOut
    Optional file path receiving the list of discovered artifact paths.

.EXAMPLE
    pwsh ./scripts/verify-signing.ps1 -SearchRoot src-tauri/target -LogPath dist/verification.log
#>

[CmdletBinding()]
param(
    [string[]]$SearchRoot,
    [string[]]$Artifact,
    [string]$LogPath,
    [string]$ListOut
)

$ErrorActionPreference = 'Stop'

if (-not $IsWindows -and $env:OS -ne 'Windows_NT') {
    Write-Error 'verify-signing.ps1: Windows-only verifier, current OS is not Windows.'
    exit 65
}

function Resolve-SignTool {
    $signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($signtool) { return $signtool.Source }

    $candidates = @()
    $kits = @(
        [Environment]::GetEnvironmentVariable('ProgramFiles(x86)'),
        [Environment]::GetEnvironmentVariable('ProgramFiles')
    ) | Where-Object { $_ } | ForEach-Object { Join-Path $_ 'Windows Kits\10\bin' }

    foreach ($kit in $kits) {
        if (Test-Path $kit) {
            $candidates += Get-ChildItem -Path $kit -Filter 'signtool.exe' -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match 'x64\\signtool\.exe$' }
        }
    }
    if ($candidates.Count -gt 0) {
        $sorted = $candidates | Sort-Object -Property FullName -Descending
        return $sorted[0].FullName
    }

    throw 'signtool.exe not found in PATH or Windows SDK installation directories.'
}

function Write-Log {
    param([string]$Message)
    Write-Host $Message
    if ($LogPath) {
        Add-Content -Path $LogPath -Value $Message
    }
}

if ($LogPath) {
    $logDir = Split-Path -Parent $LogPath
    if ($logDir -and -not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    Set-Content -Path $LogPath -Value '' -NoNewline
}

$signtoolPath = Resolve-SignTool
Write-Log "signtool located at: $signtoolPath"

$artifacts = @()
if ($Artifact) {
    foreach ($a in $Artifact) {
        $artifacts += (Resolve-Path -LiteralPath $a).Path
    }
}
if ($SearchRoot) {
    foreach ($root in $SearchRoot) {
        if (-not (Test-Path $root)) { continue }
        $found = Get-ChildItem -Path $root -Recurse -Include '*.exe', '*.msi' -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match 'release\\bundle\\(nsis|msi)\\' }
        foreach ($f in $found) { $artifacts += $f.FullName }
    }
}

$artifacts = $artifacts | Sort-Object -Unique

if ($artifacts.Count -eq 0) {
    Write-Error 'verify-signing.ps1: no .exe / .msi artifacts found under search roots.'
    exit 66
}

if ($ListOut) {
    $listDir = Split-Path -Parent $ListOut
    if ($listDir -and -not (Test-Path $listDir)) {
        New-Item -ItemType Directory -Path $listDir -Force | Out-Null
    }
    $artifacts | Set-Content -Path $ListOut
}

$failures = 0

foreach ($art in $artifacts) {
    Write-Log '════════════════════════════════════════════════════════════════════'
    Write-Log "Artifact: $art"
    Write-Log '════════════════════════════════════════════════════════════════════'

    $output = & $signtoolPath verify /pa /v /tw $art 2>&1
    $exitCode = $LASTEXITCODE
    $outputText = $output -join [Environment]::NewLine
    Write-Log $outputText

    $hasTimestamp = $outputText -match 'The signature is timestamped'
    $successful = $outputText -match 'Successfully verified'

    if ($exitCode -ne 0 -or -not $successful) {
        Write-Log "✗ signtool verify FAILED (exit=$exitCode, successful=$successful)"
        $failures++
    } elseif (-not $hasTimestamp) {
        Write-Log '✗ signature lacks timestamp — installer will become invalid when cert expires'
        $failures++
    } else {
        Write-Log '✓ signtool verify OK (signed + timestamped)'
    }
}

Write-Log '════════════════════════════════════════════════════════════════════'
if ($failures -gt 0) {
    Write-Log "RESULT: $failures check(s) failed across $($artifacts.Count) artifact(s)"
    exit $failures
}
Write-Log "RESULT: all $($artifacts.Count) artifact(s) passed Authenticode verification"
exit 0
