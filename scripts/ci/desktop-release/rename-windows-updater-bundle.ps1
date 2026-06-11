# Rename Tauri nsis updater zip to stable OTA name (GHA Windows; Git Bash cannot glob D:/ paths).
$ErrorActionPreference = 'Stop'

$Root = if ($args.Count -ge 1 -and $args[0]) { $args[0] } else { 'myrm-agent-desktop/src-tauri/target' }
$NsisDir = Join-Path $Root 'release/bundle/nsis'

if (-not (Test-Path -LiteralPath $NsisDir)) {
    Write-Error "[rename-windows-updater-bundle] Directory not found: $NsisDir"
}

$Src = Get-ChildItem -Path $NsisDir -Filter '*-setup.nsis.zip' -File -ErrorAction SilentlyContinue |
    Select-Object -First 1

if (-not $Src) {
    Write-Error "[rename-windows-updater-bundle] No *-setup.nsis.zip under $NsisDir"
}

$Dst = Join-Path $NsisDir 'MyrmAgent_x64.nsis.zip'
if (Test-Path -LiteralPath $Dst) {
    Write-Error "[rename-windows-updater-bundle] Destination already exists: $Dst"
}

Move-Item -LiteralPath $Src.FullName -Destination $Dst

$SigSrc = "$($Src.FullName).sig"
$SigDst = "$Dst.sig"
if (Test-Path -LiteralPath $SigSrc) {
    Move-Item -LiteralPath $SigSrc -Destination $SigDst
}

Write-Host "[rename-windows-updater-bundle] $($Src.Name) -> MyrmAgent_x64.nsis.zip"
