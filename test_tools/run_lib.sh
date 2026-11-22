#!/bin/bash
# run_lib.sh: shared parts of the hands-free programmes diag/twin/run2.sh (2 games) and run3.sh (3 games).
# Sourced, never run on its own. Written 2026-11-16 as static work; TEST RIG ONLY.
# The caller sets before sourcing:  G (games, e.g. AB / ABC), RUN_NAME (run2 / run3), ROWS (row keys in order)
# and then fills RR[key] with "SKIP <what>: not reached" for every row.
# Provides: say, PY (python with a timeout), row / rs_row (one ROW line per row), hc_stray / hold_on / hold_off
# (clock hold with a tagged hold_clock.py; every OTHER hold_clock is stopped), cut_phase, health, steps,
# wait_round, step (stray-holder check + health before a step), precheck, cleanup + summary (finish).
# Rules: every wait has a deadline (STEP_MAX, 600 s), every python call a timeout; the only processes stopped
# before the end are hold_clock.py ones (a leftover holder keeps resetting the clock, so a cut never ends the
# phase: lead's manual run 2026-11-16); at the end only the rig's processes (run3_check.py cleanup).

cd <WORKSPACE> || { echo "workspace missing"; exit 2; }
export TWIN_GAMES=$G
STEP_MAX=${STEP_MAX:-600}
OUT=diag/twin/$RUN_NAME.log
RES=diag/twin/${RUN_NAME}_results.txt
: > "$OUT"
exec > >(tee -a "$OUT") 2>&1
T0=$(date +%s)
STARTED=
GO_PID=
declare -A RR LASTLOG LASTT

ts() { echo "[$(date +%T) +$(( $(date +%s) - T0 ))s]"; }
say() { echo "$(ts) $*"; }
PY() { local t=$1; shift; timeout "$t" python "$@" 2>&1; }

row() {   # row KEY STATUS TEXT
    RR[$1]="$2 $3"
    echo "ROW $1 $2 $3" | cut -c1-600
}
rs_row() {   # rs_row KEY TEST OUTPUT : the RESULT line of regress_small.py -> one ROW line
    local l st
    l=$(echo "$3" | grep "^RESULT $2 " | tail -1)
    if [ -z "$l" ]; then
        row "$1" FAIL "$2: no RESULT line (timeout or crash): $(echo "$3" | tail -2 | tr '\n' ' ' | cut -c1-200)"
        return
    fi
    st=$(echo "$l" | awk '{print $3}')
    row "$1" "$st" "$2: $(echo "$l" | sed 's/^RESULT *[a-z_0-9]* *[A-Z]* *//')"
}

# ------------------------------------------------------------------ clock hold
# Our holder carries a tag argument (hold_clock.py ignores extra arguments except 'nohp'), so a holder from an
# earlier step or an earlier run is told apart from ours and stopped. HC_TAG empty = no holder wanted.
HC_TAG=
hc_stray() {
    local r
    r=$(powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'hold_clock' -and ('$HC_TAG' -eq '' -or \$_.CommandLine -notmatch '$HC_TAG') } | ForEach-Object { 'stopped hold_clock pid ' + \$_.ProcessId; Stop-Process -Id \$_.ProcessId -Force }" 2>&1 | tr -d '\r')
    [ -n "$r" ] && say "$(echo "$r" | tr '\n' ' ')"
    local n=0 left
    while [ $n -lt 10 ]; do
        left=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'hold_clock' -and ('$HC_TAG' -eq '' -or \$_.CommandLine -notmatch '$HC_TAG') }).Count" 2>/dev/null | tr -d '\r')
        [ "${left:-0}" = 0 ] && return 0
        sleep 1; n=$((n + 1))
    done
    say "warning: $left hold_clock process(es) still running after the stop"
    return 1
}
hold_on() {   # hold_on SECONDS_LEFT [nohp]
    HC_TAG="${RUN_NAME}hc$(date +%s)"
    hc_stray
    (nohup python diag/twin/hold_clock.py "$G" "$1" 900 $2 "$HC_TAG" >> "diag/twin/${RUN_NAME}_hold.txt" 2>&1 &)
    say "clock held at $1 s on $G${2:+ ($2)}, tag $HC_TAG (ends by itself after 900 s)"
}
hold_off() { HC_TAG=; hc_stray; }
cut_phase() {
    hold_off || say "warning: a holder may still reset the clock"
    say "cut: $(PY 60 diag/twin/clock.py 5 "$G" | tr '\n' ' ')"
}

# ------------------------------------------------------------------ end / stop
finish() {   # finish EXIT_CODE [REASON]
    trap - INT TERM
    [ "$STARTED" = 1 ] && hold_off
    [ -n "$2" ] && say "STOP: $2"
    if [ "$STARTED" = 1 ] && [ "$RUN_KEEP" != 1 ]; then
        say "cleanup (rig processes only):"
        PY 90 diag/twin/run3_check.py cleanup
        [ -n "$GO_PID" ] && kill "$GO_PID" 2>/dev/null
    elif [ "$STARTED" = 1 ]; then
        say "RUN_KEEP=1: the rig keeps running"
    fi
    echo
    echo "==================== $RUN_NAME summary $(date '+%F %T') ($(( ($(date +%s) - T0) / 60 )) min) ===================="
    local fails=0 k
    for k in $ROWS; do
        echo "ROW $k ${RR[$k]}" | cut -c1-600
        echo "$(date '+%F %T') ROW $k ${RR[$k]}" | cut -c1-1500 >> "$RES"
        case "${RR[$k]}" in FAIL*) fails=$((fails + 1));; esac
    done
    [ -n "$2" ] && echo "stopped early: $2"
    local code=$1
    [ "$code" = 0 ] && [ $fails -gt 0 ] && code=1
    echo "$RUN_NAME done (exit $code)"
    exit "$code"
}
trap 'finish 2 "interrupted"' INT TERM

# ------------------------------------------------------------------ health
health() {   # health LABEL : stop on a frozen game, a gone game process or C: under 10 GB free
    local a c= p bad= now w age last free
    a=$(timeout 90 bash diag/twin/alive.sh 2>&1)
    for w in $(echo "$G" | sed 's/[AB]//g; s/./& /g'); do
        c="$c$(PY 60 diag/twin/run3_check.py cpoll "$w")
"
    done
    p=$(PY 30 diag/twin/run3_check.py procs)
    say "health ($1): $(printf '%s\n%s%s\n' "$a" "$c" "$p" | tr '\n' ';' | tr -d '\r')"
    now=$(date +%s)
    for w in $(echo "$G" | sed 's/./& /g'); do
        last=$(printf '%s\n%s\n' "$a" "$c" | grep "^$w last log" | sed 's/^. last log \([0-9-]*\) s.*/\1/')
        age=$(printf '%s\n%s\n' "$a" "$c" | grep "^$w last log" | sed 's/.*poll age \([0-9-]*\) s.*/\1/')
        if [ -z "$age" ]; then bad="$bad $w:no-log-line"; continue; fi
        # NIFM poll age is valid only inside a match: the game does not poll in the hub / while loading with
        # --no-watch (runlove2 run 1: false "frozen" at the hub). HEALTH_POLL=0 there: only the log-advance test.
        [ "${HEALTH_POLL:-1}" = 1 ] && [ "$age" -gt 6 ] && bad="$bad $w:poll-age-${age}s"
        if [ -n "${LASTLOG[$w]}" ] && [ "${LASTLOG[$w]}" = "$last" ] && [ $((now - ${LASTT[$w]})) -ge 50 ]; then
            bad="$bad $w:log-stopped-at-${last}s"
        fi
        if [ "${LASTLOG[$w]}" != "$last" ]; then LASTLOG[$w]=$last; LASTT[$w]=$now; fi
    done
    echo "$p" | grep -q GONE && bad="$bad process-gone($p)"
    free=$(echo "$a" | grep "C: free GB" | sed 's/.*C: free GB \([0-9.]*\).*/\1/' | tr -d '\r')
    if [ -z "$free" ]; then
        bad="$bad C:-free-unreadable"
    elif python -c "import sys; sys.exit(0 if float('$free') < 10 else 1)" 2>/dev/null; then
        bad="$bad C:-only-${free}GB"
    fi
    [ -n "$bad" ] && finish 2 "health check ($1):$bad"
}
step() {   # step NAME : before every step, stray holders away and the games healthy
    say "=== step: $1"
    hc_stray
    health "$1"
}

steps() { PY 40 diag/twin/run3_check.py steps "$G" | tail -1 | tr -d '\r'; }
want_round() { local w s=; for w in $(echo "$G" | sed 's/./& /g'); do s="$s$w 6 $1 "; done; echo "${s% }"; }
wait_round() {   # wait_round ROUND : every game in UpdatePhase (6) of ROUND, at most STEP_MAX s, health each minute
    local t0 h s want
    want=$(want_round "$1"); t0=$(date +%s); h=$t0
    while :; do
        s=$(steps)
        [ "$s" = "$want" ] && { say "round $1 on every game ($s)"; return 0; }
        [ $(( $(date +%s) - t0 )) -ge $STEP_MAX ] && { say "round $1 not reached in $STEP_MAX s ($s)"; return 1; }
        [ $(( $(date +%s) - h )) -ge 60 ] && { health "waiting for round $1"; h=$(date +%s); }
        sleep 10
    done
}
wait_log() {   # wait_log FILE OK_REGEX FAIL_REGEX LIMIT : 0 ok, 1 fail line, 2 time-out / starter gone
    local t0 l
    t0=$(date +%s)
    while :; do
        grep -Eq "$2" "$1" 2>/dev/null && return 0
        grep -Eq "$3" "$1" 2>/dev/null && return 1
        [ $(( $(date +%s) - t0 )) -ge "$4" ] && return 2
        [ -n "$GO_PID" ] && ! kill -0 "$GO_PID" 2>/dev/null && { grep -Eq "$2" "$1" 2>/dev/null && return 0; return 2; }
        l=$(tail -1 "$1" 2>/dev/null | cut -c1-140)
        [ "$l" != "$WL_LAST" ] && { WL_LAST=$l; say "  $l"; }
        sleep 10
    done
}

precheck() {   # nothing is started when the user's own game / launcher runs or C: is nearly full
    local other free0
    other=$(PY 60 diag/twin/run3_check.py userrun | tr -d '\r')
    [ -n "$other" ] && finish 2 "the user's game or launcher is running ($other): nothing started"
    free0=$(powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free/1GB,1)" 2>/dev/null | tr -d '\r')
    python -c "import sys; sys.exit(0 if float('${free0:-0}') >= 10 else 1)" 2>/dev/null ||
        finish 2 "C: has only ${free0:-?} GB free (< 10 GB): nothing started"
    say "$RUN_NAME start: games $G, C: free $free0 GB"
}

cutcheck_row() {   # cutcheck_row KEY : the games' dusk_lan.txt compared (copies in diag/twin/<run>_logs/)
    local la lb lc args= w f cc rc sum
    la="$(cygpath -m "$APPDATA")/eden/log/dusk_lan.txt"
    mkdir -p "diag/twin/${RUN_NAME}_logs"
    for w in $(echo "$G" | sed 's/./& /g'); do
        if [ "$w" = A ]; then f=$la; else f="$(pwd -W)/diag/twin/user$w/log/dusk_lan.txt"; fi
        [ -f "$f" ] || { row "$1" SKIP "cutcheck: $f missing"; return; }
        cp "$f" "diag/twin/${RUN_NAME}_logs/${w}_dusk_lan.txt"
        args="$args $w:$f"
    done
    # shellcheck disable=SC2086
    cc=$(PY 300 diag/twin/cutcheck.py $args)
    rc=$?
    echo "$cc" > "diag/twin/${RUN_NAME}_cutcheck.txt"
    sum=$(echo "$cc" | grep 'disagreement(s) flagged' | tail -1)
    if [ $rc = 0 ]; then
        row "$1" PASS "cutcheck: ${sum:-0 flagged} | diag/twin/${RUN_NAME}_cutcheck.txt"
    elif [ -n "$sum" ]; then
        row "$1" FAIL "cutcheck: $sum: $(echo "$cc" | grep '!!' | head -3 | tr '\n' ' ' | cut -c1-300)"
    else
        row "$1" FAIL "cutcheck rc $rc (timeout or crash): $(echo "$cc" | tail -2 | tr '\n' ' ' | cut -c1-200)"
    fi
}
