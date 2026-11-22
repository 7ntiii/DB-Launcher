# collect_logs.ps1 - copies the log files of every game on this PC into a new folder "DuskLogs_<PC>_<date-time>"
# next to the package folder, writes a summary line and opens the folder. Started by "Collect logs.cmd".
# It only COPIES: nothing is deleted, changed, uploaded or sent anywhere, and no Windows setting is touched.
# No Python and no admin rights needed (Windows PowerShell 5.1, part of Windows 10 / 11).
param([string]$Here = $PSScriptRoot)

$ErrorActionPreference = 'Continue'
# "Collect logs.cmd" passes "<its folder>\." (a trailing backslash would end the quoted argument): normalise it
try { $Here = (Resolve-Path -LiteralPath $Here -ErrorAction Stop).Path.TrimEnd('\') } catch { }

# The package folder is the one with Play.Duskbloods.exe: this script's folder or the one above (lan_fix).
$pkg = $Here
if (-not (Test-Path -LiteralPath (Join-Path $pkg 'Play.Duskbloods.exe'))) {
    $up = Split-Path -Parent $Here
    if ($up -and (Test-Path -LiteralPath (Join-Path $up 'Play.Duskbloods.exe'))) { $pkg = $up }
}

# Version: from READ ME FIRST.txt ("EVERY PLAYER MUST USE vX" names the full version; else the title line).
$version = 'unknown'
$readme = Join-Path $pkg 'READ ME FIRST.txt'
if (Test-Path -LiteralPath $readme) {
    $text = Get-Content -LiteralPath $readme -TotalCount 12 -ErrorAction SilentlyContinue
    $m = $text | Select-String -Pattern 'MUST USE (v[0-9][0-9.]*[0-9])' | Select-Object -First 1
    if ($m) { $version = $m.Matches[0].Groups[1].Value }
    else {
        $m = $text | Select-String -Pattern 'LAN online, (v[0-9][0-9.]*[0-9])' | Select-Object -First 1
        if ($m) { $version = $m.Matches[0].Groups[1].Value }
    }
    $b = $text | Select-String -Pattern 'commit ([0-9a-f]+)' | Select-Object -First 1
    if ($b) { $version = "$version (commit $($b.Matches[0].Groups[1].Value))" }
}

# Target: next to the package folder; if that place cannot be written, inside the package, then the Desktop.
$pcName = ($env:COMPUTERNAME -replace '[^A-Za-z0-9_-]', '_')
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$name = "DuskLogs_${pcName}_$stamp"
$out = $null
foreach ($base in @((Split-Path -Parent $pkg), $pkg, [Environment]::GetFolderPath('Desktop'))) {
    if (-not $base) { continue }
    $try = Join-Path $base $name
    try {
        New-Item -ItemType Directory -Path $try -ErrorAction Stop | Out-Null
        $out = $try
        break
    } catch { }
}
if (-not $out) {
    Write-Host 'Could not create a folder for the logs (next to the package, in it, or on the Desktop).'
    exit 1
}

$count = 0
$missing = @()
$seen = @{}
# One file into the new folder. Never overwrites (a name already there is skipped). A log the running game
# holds open for writing (eden_log.txt: opened deny-write, lobbysize_notes 5) can refuse Copy-Item's share
# mode; then it is read through a stream that shares read + write + delete, and written with CreateNew.
function Copy-One([string]$src, [string]$dst) {
    if (Test-Path -LiteralPath $dst) { return $false }
    try {
        Copy-Item -LiteralPath $src -Destination $dst -ErrorAction Stop
        return $true
    } catch {
        # only our own empty file of this failed try, in our own new folder
        $part = Get-Item -LiteralPath $dst -ErrorAction SilentlyContinue
        if ($part -and $part.Length -eq 0) { Remove-Item -LiteralPath $dst -ErrorAction SilentlyContinue }
    }
    $in = $null; $o = $null
    try {
        $in = [System.IO.File]::Open($src, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read,
                                     [System.IO.FileShare]'ReadWrite, Delete')
        $o = [System.IO.File]::Open($dst, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write,
                                    [System.IO.FileShare]::None)
        $in.CopyTo($o)
        return $true
    } catch {
        $script:missing += "$src (could not be read: $($_.Exception.Message))"
        return $false
    } finally {
        if ($o) { $o.Dispose() }
        if ($in) { $in.Dispose() }
    }
}
function Copy-Set([string]$from, [string[]]$patterns, [string]$sub) {
    if (-not (Test-Path -LiteralPath $from)) { $script:missing += $from; return }
    $dest = Join-Path $script:out $sub
    foreach ($p in $patterns) {
        foreach ($f in @(Get-ChildItem -LiteralPath $from -Filter $p -File -ErrorAction SilentlyContinue)) {
            $key = "$sub|$($f.FullName)"
            if ($script:seen.ContainsKey($key)) { continue }   # two patterns, one file: copied once
            $script:seen[$key] = $true
            if (-not (Test-Path -LiteralPath $dest)) { New-Item -ItemType Directory -Path $dest | Out-Null }
            if (Copy-One $f.FullName (Join-Path $dest $f.Name)) { $script:count++ }
        }
    }
}

# 1. the first game on this PC (the launcher's game): its data folder as the launcher picks it
#    (play_duskbloods.py data_dir_for: the first of eden, lichii, eglantine, yuzu in %APPDATA%)
$data1 = Join-Path $env:APPDATA 'eden'
foreach ($n in @('eden', 'lichii', 'eglantine', 'yuzu')) {
    $d = Join-Path $env:APPDATA $n
    if (Test-Path -LiteralPath $d) { $data1 = $d; break }
}
Copy-Set (Join-Path $data1 'log') @('dusk_lan*.txt', 'eden_log*.txt', 'dusk_lan_status.json',
                                    'dusk_lan_match.txt') 'game1'
# N10: the launcher's own run folders (<data>\duskbloods_test\runs\<time>): the match server and
# session server logs (frontdoor.log, server.log) and the game's console. Not server_data (accounts),
# not crash dumps (*.dmp: whole process memory; only their names go into SUMMARY.txt).
$dumps = @()
function Copy-Runs([string]$runs, [string]$sub) {
    if (-not (Test-Path -LiteralPath $runs)) { return }
    foreach ($r in @(Get-ChildItem -LiteralPath $runs -Directory -ErrorAction SilentlyContinue |
                     Sort-Object Name -Descending | Select-Object -First 3)) {
        Copy-Set $r.FullName @('*.log', '*.txt') ($sub + '\' + $r.Name)
        foreach ($d in @(Get-ChildItem -LiteralPath $r.FullName -Filter '*.dmp' -File -ErrorAction SilentlyContinue)) {
            $script:dumps += "$($d.FullName) ($([math]::Round($d.Length / 1MB)) MB)"
        }
    }
}
$test1 = Join-Path $data1 'test_data'
if (-not (Test-Path -LiteralPath $test1)) { $test1 = Join-Path $data1 'duskbloods_test' }
Copy-Runs (Join-Path $test1 'runs') 'game1\runs'
#    a portable first game (<package>\Lichii\user: its data folder wins over %APPDATA%, path_util.cpp:116)
$portable = Join-Path $pkg 'Lichii\user\log'
if (Test-Path -LiteralPath $portable) {
    Copy-Set $portable @('dusk_lan*.txt', 'eden_log*.txt', 'dusk_lan_status.json', 'dusk_lan_match.txt') 'game1_portable'
}
# 2. a second player on this PC ("Start second player.cmd")
$second = Join-Path $pkg 'SecondPlayer'
if (Test-Path -LiteralPath $second) {
    Copy-Set (Join-Path $second 'user\log') @('*') 'game2'
    Copy-Set $second @('second_player_log.txt') 'game2'
    Copy-Runs (Join-Path $second 'runs') 'game2\runs'
}
# 3. the host tools' own log ("Host a match (4 players).cmd")
#    and, from v3.9.5 on (lan_fix_host.py sets DUSK_MATCH_FILE), the match server's lobby-size file
#    N7/N10: the host window's own log and the older host_plus log
Copy-Set (Join-Path $pkg 'lan_fix') @('host_log.txt', 'host_plus_log.txt', 'host_plus_log.txt.prev',
                                      'dusk_lan_match.txt') 'host'

$line = "$count file(s) from this PC ($env:COMPUTERNAME), package $version, collected $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$notes = @($line, '',
           'These files contain the local network addresses of the PCs in the match and the player names.',
           'Nothing was uploaded or sent: share this folder only with the person you want to send it to.')
if ($missing.Count) { $notes += @('', 'Not found / not copied:') + $missing }
if ($dumps.Count) { $notes += @('', 'Crash dumps on this PC (NOT copied; send one only if asked):') + $dumps }
Set-Content -LiteralPath (Join-Path $out 'SUMMARY.txt') -Value $notes -Encoding UTF8
Write-Host $line
Write-Host "Folder: $out"
Write-Host 'The logs contain the PCs'' local network addresses and the player names. Nothing was sent.'
Start-Process explorer.exe -ArgumentList "`"$out`""
exit 0
