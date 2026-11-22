# Fetches the newest game program (Lichii\lichii.exe and nx2_switches.txt) from the host PC of the home network
# and puts it into this package folder. The old program is kept as lichii.exe.old. Nothing else is touched:
# no saves, no settings, no Windows setting. It only talks to the host PC's address on port 18480.
param([string]$HostAddress = '', [switch]$TestSkipRunningCheck)
$ErrorActionPreference = 'Stop'
$pkg = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $pkg 'Lichii\lichii.exe'))) { $pkg = $PSScriptRoot }
$lichii = Join-Path $pkg 'Lichii'
if (-not (Test-Path (Join-Path $lichii 'lichii.exe'))) { Write-Host 'Lichii\lichii.exe not found next to this file.'; exit 1 }
if (-not $TestSkipRunningCheck -and (Get-Process -Name lichii -ErrorAction SilentlyContinue)) { Write-Host 'The game is running. Close it first, then run this again.'; exit 1 }

$saved = Join-Path $pkg 'lan_fix\update_host.txt'
if (-not $HostAddress -and (Test-Path $saved)) { $HostAddress = (Get-Content $saved -TotalCount 1).Trim() }
if (-not $HostAddress) {
    $HostAddress = Read-Host 'Address of the host PC (press Enter for 192.168.1.11)'
    if (-not $HostAddress) { $HostAddress = '192.168.1.11' }
}
$base = "http://${HostAddress}:18480"
Write-Host "Asking $base ..."
try { $info = (Invoke-WebRequest -UseBasicParsing "$base/version.txt" -TimeoutSec 10).Content | ConvertFrom-Json }
catch { Write-Host "No update server answers at $base (is the host ready?)."; exit 1 }
Set-Content -Path $saved -Value $HostAddress -Encoding ascii

$now = (Get-FileHash (Join-Path $lichii 'lichii.exe') -Algorithm SHA256).Hash.ToLower()
$want = $info.files.'lichii.exe'.sha256
if ($now -eq $want) { Write-Host ("Already on build " + $info.build + ". Nothing to do."); exit 0 }

foreach ($name in @('lichii.exe', 'nx2_switches.txt')) {
    $tmp = Join-Path $lichii ($name + '.new')
    Write-Host "Fetching $name ..."
    Invoke-WebRequest -UseBasicParsing "$base/$name" -OutFile $tmp -TimeoutSec 300
    $got = (Get-FileHash $tmp -Algorithm SHA256).Hash.ToLower()
    if ($got -ne $info.files.$name.sha256) { Remove-Item $tmp; Write-Host "$name did not arrive complete. Nothing was changed. Try again."; exit 1 }
}
Copy-Item (Join-Path $lichii 'lichii.exe') (Join-Path $lichii 'lichii.exe.old') -Force
foreach ($name in @('lichii.exe', 'nx2_switches.txt')) {
    Move-Item (Join-Path $lichii ($name + '.new')) (Join-Path $lichii $name) -Force
}
Write-Host ("Done. This folder is now on build " + $info.build + ". Start the game as usual.")
