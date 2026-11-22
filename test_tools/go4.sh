#!/bin/bash
# GUARD 2026-11-16: the user allows at most TWO games on this PC (a 4-game run froze it). Do not remove.
if [ "${USER_SAID_MORE_THAN_TWO_GAMES:-0}" != "1" ]; then echo "REFUSED: more than two games on this PC is not allowed (user rule 2026-11-16)"; exit 9; fi
# go4.sh: the 4-game version of go.sh (diag/twin/four_games_notes.md). Stops the old rig, clears the
# watcher logs, launches the games of TWIN_GAMES (default ABCD) with twin.py, drives every game to the
# hub (to_hub2.py) and into ONE match (to_match2.py), with checks and progress lines in between.
# Last line: "nav done HH:MM:SS" or "FAILED: reason". Everything is also appended to diag/twin/go4.log.
#
# Usage (Git Bash, any directory):
#   bash diag/twin/go4.sh                          Standard, games ABCD
#   GO4_RULE=4 bash diag/twin/go4.sh               Bloodbound: set_rule.py MASK 4 once all are in the hub
#   TWIN_GAMES=ABC bash diag/twin/go4.sh           3 games (DUSK_MATCH_MIN follows the game count)
# Defaults (each can be overridden from the environment; they are what four_games_notes.md says):
#   TWIN_GAMES=ABCD  DUSK_MATCH_MIN=<number of games>  DUSK_WAIT_LONGPOLL=3600  TO_MATCH_ONE_PRESS=1
#   TO_MATCH_WAIT=240  TWIN_ARGS=--no-watch  TWIN_P2P_FORMAT=self
# Own options:
#   GO4_RULE=MASK        rule-set menu mask written by set_rule.py in the hub (1 Standard, 2 No Alliances,
#                        4 Bloodbound); empty (default) = no write, the menu's own choice
#   GO4_RULE_GAMES=ABCD  games set_rule.py runs on (default: all games, because the host = player 1 =
#                        lowest member id, and which game that is with a fresh userD is not known)
#   GO4_PHASE1=1         after the join, also wait (max GO4_PHASE1_WAIT=420 s) until every game is in
#                        step 6 round 1 (Phase I) before "nav done"
#   GO4_FORCE=1          start even when a lichii.exe that is NOT the rig build is running (the user's game)
#   GO4_SERIAL=1         (default) drive the games to the hub one after another, GO4_STAGGER=30 s apart,
#                        so their hub texture loads never overlap; 0 = all at once (old behaviour)
#   SCREEN_TOLERANT=0|1  force screen.py's 1x-only / scale-tolerant check (default: per game's config)
# After each game's hub (and after the join, or on a failure) "vram X (...)" lines list that game's
# VRAM warnings from its emulator log (over budget, unbacked, host memory, failed, device lost).
# QW_* variables pass through to the watchers as in go.sh (only without --no-watch; A/B only).

WS=<WORKSPACE>
cd "$WS" || { echo "FAILED: workspace $WS not found"; exit 1; }
LOG=diag/twin/go4.log
log() { echo "$*" | tee -a "$LOG"; }
fail() { log "FAILED: $*"; exit 1; }

export TWIN_GAMES=${TWIN_GAMES:-ABCD}
GAMES=$TWIN_GAMES
N=${#GAMES}
[[ "$GAMES" =~ ^ABC?D?$ ]] || fail "TWIN_GAMES=$GAMES (twin.py always starts A and B; allowed: AB, ABC, ABD, ABCD)"
export DUSK_MATCH_MIN=${DUSK_MATCH_MIN:-$N}
export DUSK_WAIT_LONGPOLL=${DUSK_WAIT_LONGPOLL:-3600}
export TO_MATCH_ONE_PRESS=${TO_MATCH_ONE_PRESS:-1}
export TO_MATCH_WAIT=${TO_MATCH_WAIT:-240}
export TWIN_P2P_FORMAT=${TWIN_P2P_FORMAT:-self}
if [ -z "${TWIN_ARGS+x}" ]; then TWIN_ARGS=--no-watch; fi
IP_C=${TWIN_IP_C:-10.0.0.225}
IP_D=${TWIN_IP_D:-169.254.0.1}
LAN=${TWIN_LAN_IP:-192.168.1.11}
unset DUSK_BASE                     # mem.py would use ONE base for every game

log "=== go4 start $(date '+%F %T') games $GAMES ($N) DUSK_MATCH_MIN=$DUSK_MATCH_MIN LONGPOLL=$DUSK_WAIT_LONGPOLL" \
    "P2P=$TWIN_P2P_FORMAT TO_MATCH_WAIT=$TO_MATCH_WAIT TWIN_ARGS='$TWIN_ARGS' rule=${GO4_RULE:-menu}"
[ "$DUSK_MATCH_MIN" -lt "$N" ] && log "warning: DUSK_MATCH_MIN=$DUSK_MATCH_MIN < $N games: the server may start a match without the last game(s)"

# 1. The user's own game must not be closed by the rig (memory: check the user's game before the rig).
OTHER=$(python -c "
import psutil
rig = 'duskbloodsworkspace/build/lichii/bin/lichii.exe'
out = []
for p in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
    name = (p.info['name'] or '').lower()
    exe = (p.info['exe'] or '').replace(chr(92), '/').lower()
    cmd = ' '.join(p.info['cmdline'] or []).replace(chr(92), '/').lower()
    if name == 'lichii.exe' and not exe.endswith(rig):
        out.append('lichii pid %d (%s)' % (p.info['pid'], exe or '?'))
    elif name.startswith('python') and 'launcher' in cmd and 'diag/twin' not in cmd:
        out.append('launcher pid %d' % p.info['pid'])
print('; '.join(out))
" 2>/dev/null)
if [ -n "$OTHER" ]; then
    [ "$GO4_FORCE" = 1 ] || fail "the user's game or launcher is running ($OTHER); close it or set GO4_FORCE=1"
    log "warning: GO4_FORCE=1 with $OTHER running (taskkill below stops EVERY lichii.exe, this one too)"
fi

# 2. Per-game prerequisites: user folders and the local source addresses of C / D.
for w in $(echo "$GAMES" | sed 's/A//; s/./& /g'); do
    [ -d "diag/twin/user$w/config" ] || fail "diag/twin/user$w/config missing (four_games_notes.md: userD = copy of userC without online/log/cache)"
done
IPS=$(ipconfig | tr -d '\r')
echo "$IPS" | grep -q "$LAN" || fail "LAN address $LAN (TWIN_LAN_IP) is not on any adapter"
case "$GAMES" in *C*) echo "$IPS" | grep -q "$IP_C" || fail "game C address $IP_C (TWIN_IP_C, ZeroTier) is not on any adapter";; esac
case "$GAMES" in *D*) echo "$IPS" | grep -q "$IP_D" || fail "game D address $IP_D (TWIN_IP_D, Tailscale) is not on any adapter: pass TWIN_IP_D=<its IPv4>";; esac
log "addresses ok: A 127.0.0.1, B $LAN$(case $GAMES in *C*) echo ", C $IP_C";; esac)$(case $GAMES in *D*) echo ", D $IP_D";; esac)"

# 3. Memory: about 26 GB commit and 8.5 GB resident per game (more_players_notes.md 5). Warn only.
MEMLINE=$(powershell -NoProfile -Command '$o = Get-CimInstance Win32_OperatingSystem; $c = (Get-PSDrive C).Free / 1GB; [string]::Format([cultureinfo]::InvariantCulture, "{0:F1} {1:F1} {2:F1} {3:F1}", ($o.FreePhysicalMemory / 1MB), ($o.FreeVirtualMemory / 1MB), ($o.TotalVirtualMemorySize / 1MB), $c)' 2>/dev/null | tr -d '\r')
read -r FREE_RAM FREE_COMMIT COMMIT_LIMIT FREE_C <<< "$MEMLINE"
log "memory before start: free RAM ${FREE_RAM:-?} GB, free commit ${FREE_COMMIT:-?} of ${COMMIT_LIMIT:-?} GB, C: free ${FREE_C:-?} GB"
if [ -n "$FREE_C" ]; then
    NEED=$(( N * 26 ))
    python -c "import sys; sys.exit(0 if float('$FREE_COMMIT') + float('$FREE_C') >= $NEED else 1)" 2>/dev/null ||
        log "warning: free commit + C: free < ~$NEED GB for $N games: the last game may fail to allocate at boot (console_D.log / userD/log)"
fi
# 3b. Resolution per game (four_players2_notes.md 3, four_players3_notes.md): 4 games share ~7 GiB of
#     VRAM (run 05:22: D over the budget at its hub load, unbacked images, black, hung). screen.py
#     reads the same setting and uses its scale-tolerant check for a game that is not at 1x (run 03:29:
#     D at 0.5x "stuck:other" with the 1x-only check). resolution_setup\default=true (or missing)
#     means 1x whatever the value (frontend_common/config.cpp).
RES_NAMES=(1/4x 1/2x 3/4x 1x 5/4x 3/2x 2x 3x 4x)
cfg_of() { if [ "$1" = A ]; then echo "$APPDATA/eden/config/qt-config.ini"; else echo "diag/twin/user$1/config/qt-config.ini"; fi; }
RESLINE=""
for w in $(echo "$GAMES" | sed 's/./& /g'); do
    CFG=$(cfg_of $w)
    R=$(grep -m1 '^resolution_setup=' "$CFG" 2>/dev/null | cut -d= -f2 | tr -d '\r')
    DEF=$(grep -m1 '^resolution_setup\\default=' "$CFG" 2>/dev/null | cut -d= -f2 | tr -d '\r')
    [ "$DEF" = false ] || R=3
    NV=$(grep -m1 '^nvdec_emulation=' "$CFG" 2>/dev/null | cut -d= -f2 | tr -d '\r')
    RESLINE="$RESLINE $w=${RES_NAMES[${R:-3}]:-?}"
    NVLINE="$NVLINE $w=${NV:-?}"
done
log "resolution:$RESLINE (nvdec_emulation 0=off 2=gpu:$NVLINE)"
RES_KINDS=$(echo "$RESLINE" | tr ' ' '\n' | grep = | cut -d= -f2 | sort -u | wc -l)
[ "$RES_KINDS" -gt 1 ] && log "note: games at different resolutions: screen.py uses its scale-tolerant check for the games not at 1x"
[ "$N" -ge 4 ] && log "warning: $N games: VRAM is the limit (run 07:15: 3 games used 2.1-4.1 GiB dedicated each, card full, A partly paged out); a lower resolution does NOT free texture memory (four_players3_notes.md 2, 4)"

# Live VRAM per game process: Windows' "GPU Process Memory" counters (dedicated = on the card,
# shared = paged out to system RAM), pids from session.json; plus the card's total. Read only.
vram_live() {   # $1 = label
    GO4_LBL="$1" powershell -NoProfile -Command '
$s = Get-Content diag/twin/session.json -Raw | ConvertFrom-Json
$map = @{}; $s.pids.PSObject.Properties | ForEach-Object { $map[[string]$_.Value] = $_.Name }
$out = @{}
foreach ($k in "Dedicated Usage", "Shared Usage") {
  (Get-Counter "\GPU Process Memory(*)\$k" -ErrorAction SilentlyContinue).CounterSamples | ForEach-Object {
    $p = ($_.InstanceName -split "_")[1]
    if ($map.ContainsKey($p)) { $out["$($map[$p]) $k"] = [math]::Round($_.CookedValue / 1GB, 2) } } }
$card = ((Get-Counter "\GPU Adapter Memory(*)\Dedicated Usage" -ErrorAction SilentlyContinue).CounterSamples |
         Measure-Object CookedValue -Maximum).Maximum / 1GB
$games = ($map.Values | Sort-Object | ForEach-Object { "$_ {0}+{1}" -f $out["$_ Dedicated Usage"], $out["$_ Shared Usage"] }) -join ", "
[string]::Format([cultureinfo]::InvariantCulture, "  vram live ({0}): GiB on card+paged out: {1}; card total {2:F1} GiB", $env:GO4_LBL, $games, $card)
' 2>/dev/null | tr -d '\r' | tee -a "$LOG"
}

# VRAM warnings of one game's emulator log (A: the user's %APPDATA% log, read only; B/C/D: userX\log).
# Counts and the first / last time of each kind, the scale the game's upscaler runs at, and the
# texture collector's last thresholds.
log_of() { if [ "$1" = A ]; then echo "$APPDATA/eden/log/eden_log.txt"; else echo "diag/twin/user$1/log/eden_log.txt"; fi; }
vram_report() {   # $1 = game, $2 = label
    python - "$(log_of $1)" "$1" "$2" <<'PYEOF' 2>&1 | tee -a "$LOG"
import re, sys
path, who, label = sys.argv[1:4]
kinds = [('over budget', 'is over the memory budget'), ('unbacked', 'does not fit; using an unbacked'),
         ('host memory', 'placed in host memory'), ('failed', r'Image \d+x\d+x\d+ .* failed:'),
         ('OOM margin', 'Out of device memory: keeping'), ('RT unbacked', 'Render target in unbacked image'),
         ('device lost', 'DEVICE_LOST|device lost')]
hits = {k: [] for k, _ in kinds}
scale = thresholds = ''
try:
    f = open(path, encoding='utf-8', errors='replace')
except OSError:
    print(f'  vram {who} ({label}): no log {path}'); sys.exit()
for line in f:
    m = re.match(r'\[\s*([\d.]+)\]', line)
    t = '%.0f' % float(m.group(1)) if m else '?'
    for k, pat in kinds:
        if re.search(pat, line):
            hits[k].append(t)
    if 'render up to' in line:
        scale = line.split('render up to', 1)[1].strip()
    elif 'Texture cache thresholds' in line:
        thresholds = line.split('thresholds:', 1)[1].strip()
bad = {k: v for k, v in hits.items() if v}
summary = ', '.join(f'{k} {len(v)} ({v[0]}..{v[-1]} s)' for k, v in bad.items()) or 'no VRAM warnings'
print(f'  vram {who} ({label}): {summary}; upscaler {scale or "?"}; collector {thresholds or "?"}')
PYEOF
}

# 4. Stop the old rig (as go.sh) and the leftover watchers (four_games_notes: run kill_watchers.py first).
python tools/auto/kill_watchers.py 2>&1 | tee -a "$LOG"
taskkill //F //IM lichii.exe >/dev/null 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'quic_watch|npln_stub|frontdoor|twin.py|to_hub|to_match|set_rule|match4' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
rm -f diag/net/quic_watch.log diag/net/quic_watch_B.log diag/net/qw_st_*.txt diag/net/qw_stop_* diag/net/qw_cmd_*.txt
# (the assist keeps the last five dusk_lan logs itself: never delete them here, the user needs them)
sleep 2

# 5. Launch: servers + room registration + boots A 0 s, B +20 s, C +95 s, D +170 s (twin.py).
T0=$(date +%s)
el() { echo "$(( $(date +%s) - T0 ))s"; }
log "start $(date +%T)"
python diag/twin/twin.py $TWIN_ARGS > diag/twin/twin_console.log 2>&1 &
TWIN_PID=$!
for i in $(seq 1 30); do
    REG=$(grep -c '^room register' diag/twin/twin_console.log 2>/dev/null)
    [ "${REG:-0}" -ge "$N" ] && break
    kill -0 $TWIN_PID 2>/dev/null || fail "twin.py exited at once: $(tail -3 diag/twin/twin_console.log | tr '\n' ' ')"
    sleep 1
done
grep '^room register' diag/twin/twin_console.log | sed 's/^/  /' | tee -a "$LOG"
[ "${REG:-0}" -ge "$N" ] || fail "only ${REG:-0} of $N room registrations after 30 s (twin_console.log)"
grep '^room register' diag/twin/twin_console.log | grep -vq ' 200 ' && fail "a room registration was not 200 (see above)"
log "servers up, $N addresses in one room ($(el))"

# 6. Every game to the hub, ONE AT A TIME (GO4_SERIAL=1, default): the hub load is each game's
#    texture peak (run 05:22: D's 13 unbacked images all came at its hub load), so the next game
#    leaves its title screen only when the previous one is in the hub, plus GO4_STAGGER seconds
#    (default 30) for its textures to settle. The boots themselves are staggered by twin.py
#    (A 0 s, B +20 s, C +95 s, D +170 s); the games wait at their title screens meanwhile.
#    GO4_SERIAL=0: the old parallel drive (all games at once). to_hub2 waits up to 300 s for a
#    debug server, then 300 s for that game's hub. After each hub: that game's VRAM log warnings.
: > diag/twin/go4_hub.txt
if [ "${GO4_SERIAL:-1}" = 1 ]; then
    for w in $(echo "$GAMES" | sed 's/./& /g'); do
        log "to the hub: $w ($(el))"
        TWIN_GAMES=$w python diag/twin/to_hub2.py 2>&1 | tee -a "$LOG" >> diag/twin/go4_hub.txt
        grep -q "^$w hub in" diag/twin/go4_hub.txt || {
            vram_report $w "no hub"
            fail "game $w not in the hub ($(grep "^$w " diag/twin/go4_hub.txt | tail -1); see runs/<time>/console_$w.log)"
        }
        vram_report $w "hub"
        vram_live "$w in the hub"
        case "$GAMES" in *"$w") ;; *) sleep "${GO4_STAGGER:-30}";; esac
    done
else
    python diag/twin/to_hub2.py 2>&1 | tee -a "$LOG" >> diag/twin/go4_hub.txt
    for w in $(echo "$GAMES" | sed 's/./& /g'); do
        grep -q "^$w hub in" diag/twin/go4_hub.txt || {
            vram_report $w "no hub"
            fail "game $w not in the hub ($(grep "^$w " diag/twin/go4_hub.txt | tail -1); see runs/<time>/console_$w.log)"
        }
    done
    for w in $(echo "$GAMES" | sed 's/./& /g'); do vram_report $w "hub"; done
    vram_live "all in the hub"
fi
log "all $N games in the hub ($(el))"
ALIVE=$(python -c "
import json, psutil
s = json.load(open('diag/twin/session.json'))
print(' '.join('%s:%s' % (w, 'up' if psutil.pid_exists(p) else 'GONE') for w, p in sorted(s['pids'].items())))
" 2>&1)
log "processes: $ALIVE"
echo "$ALIVE" | grep -q GONE && fail "a game process ended: $ALIVE"

# 7. Optional rule set: set_rule.py rewrites the menu mask every 0.5 s until a match object exists
#    (max 420 s from its start), so start it now, in the hub, right before matchmaking.
if [ -n "$GO4_RULE" ]; then
    for w in $(echo "${GO4_RULE_GAMES:-$GAMES}" | sed 's/./& /g'); do
        python diag/twin/set_rule.py "$w" "$GO4_RULE" > "diag/twin/go4_rule_$w.txt" 2>&1 &
    done
    log "set_rule.py MASK $GO4_RULE started on ${GO4_RULE_GAMES:-$GAMES} (output diag/twin/go4_rule_<game>.txt)"
    sleep 2
fi

# 8. All games into one match. to_match2 exits 0 only when every game's log shows a new join.
python diag/twin/to_match2.py 2>&1 | tee -a "$LOG"
[ "${PIPESTATUS[0]}" = 0 ] || {
    for w in $(echo "$GAMES" | sed 's/./& /g'); do vram_report $w "no join"; done
    fail "to_match2: not every game joined (screens above; frontdoor.log in the run dir)"
}
RUN=$(python -c "import json; print(json.load(open('diag/twin/session.json'))['run'])" 2>/dev/null)
MATCH=$(python -c "
import json, sys
last = None
for line in open(sys.argv[1], encoding='utf8', errors='replace'):
    if '\"online_match\"' in line:
        try: last = json.loads(line)
        except ValueError: pass
print('%d %s %s' % (len(last['players']), last['players'], last['addresses']) if last else '0 none')
" "$RUN/frontdoor.log" 2>/dev/null)
log "server match: ${MATCH:-unreadable} (players, ids, addresses; $RUN/frontdoor.log)"
[ "${MATCH%% *}" = "$N" ] || log "warning: the last server match does not list $N players"

# 9. Optional: wait for Phase I on every game (what match4.py starts from).
if [ "$GO4_PHASE1" = 1 ]; then
    python diag/twin/match4.py "$GAMES" --phase1-only --start-wait "${GO4_PHASE1_WAIT:-420}" 2>&1 | tee -a "$LOG"
    [ "${PIPESTATUS[0]}" = 0 ] || {
        for w in $(echo "$GAMES" | sed 's/./& /g'); do vram_report $w "no Phase I"; done
        fail "not every game reached Phase I (step 6 round 1) in ${GO4_PHASE1_WAIT:-420} s"
    }
fi
for w in $(echo "$GAMES" | sed 's/./& /g'); do vram_report $w "after join"; done
vram_live "after join"

log "nav done $(date +%T) ($(el))"
wait
