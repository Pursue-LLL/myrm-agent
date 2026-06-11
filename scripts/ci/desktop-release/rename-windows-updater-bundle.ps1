# Rename Tauri NSIS setup.exe to stable OTA name (GHA Windows; nsis.zip is ephemeral in Tauri v2).
$ErrorActionPreference = 'Stop'

$Root = if ($args.Count -ge 1 -and $args[0]) { $args[0] } else { 'myrm-agent-desktop/src-tauri/target' }
$NsisDir = Join-Path $Root 'release/bundle/nsis'

if (-not (Test-Path -LiteralPath $NsisDir)) {
    Write-Error "[rename-windows-updater-bundle] Directory not found: $NsisDir"
}

$Src = Get-ChildItem -Path $NsisDir -Filter '*-setup.exe' -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -ne 'MyrmAgent_x64-setup.exe' } |
    Select-Object -First 1

if (-not $Src) {
    Write-Error "[rename-windows-updater-bundle] No *-setup.exe under $NsisDir"
}

$Dst = Join-Path $NsisDir 'MyrmAgent_x64-setup.exe'
if (Test-Path -LiteralPath $Dst) {
    Write-Error "[rename-windows-updater-bundle] Destination already exists: $Dst"
}

Move-Item -LiteralPath $Src.FullName -Destination $Dst

$SigSrc = "$($Src.FullName).sig"
$SigDst = "$Dst.sig"
if (Test-Path -LiteralPath $SigSrc) {
    Move-Item -LiteralPath $SigSrc -Destination $SigDst
}

Write-Host "[rename-windows-updater-bundle] $($Src.Name) -> MyrmAgent_x64-setup.exe"
