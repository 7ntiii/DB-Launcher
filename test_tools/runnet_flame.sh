#!/bin/bash
# runnet_flame.sh: hands-free 2-game test of the taken-state message (side type 12, V400-2: 7 sends over about
# 16 s) at LARGE Flame corpses (pay once for everybody), on a bad simulated network and as a control without it.
# Written 2026-11-16 as static work; never run. TEST RIG ONLY. Notes: diag/net/runnet_flame_notes.md.
# Style and checks as runnet.sh (helper 3); helper per corpse: diag/twin/flamerace.py.
#
#   bash diag/twin/runnet_flame.sh       (Git Bash, from anywhere; log diag/twin/runnet_flame.log, rows also
#                                         appended to diag/twin/runnet_flame_results.txt, logs in runnet_flame_logs/)
# Options (environment):
#   RUNFLAME_ONLY="control bad"   profiles in this order (default both: control first, it proves the tools)
#   RUNFLAME_SIM=50,30,3,45,2000  the bad profile's LICHII_NET_SIM, on BOTH games (the simulator only holds /
#                                 drops SENDS, so A and B together impair both directions; netsim_notes.md)
#   RUNFLAME_PLAN="same:20 ab:0.3 ba:20"   the three corpses: MODE:AT (flamerace.py). MODE same = both press at
#                                 the same moment (two threads released by one barrier, a few ms apart), ab / ba =
#                                 the first game, then the second RUNFLAME_GAP s later. AT = the first press at
#                                 unix time % PERIOD == AT. The simulator's stall windows START at multiples of the
#                                 period in unix time (netsim_notes.md "Stall"), so AT 0.3 = 0.3 s into a 2 s stall
#                                 (both games' sends held until 2.0 s, then sent in one burst), AT 20 = far from one.
#                                 The control uses the same plan and the same phase.
#   RUNFLAME_GAP=3.5              s between the two presses in ab / ba: past the stall end (2.0 s) + 50 + 30 ms
#                                 delay + the assist's 250 ms poll, so the second game MUST already know the take
#   RUNNET_SEED=1                 LICHII_NET_SIM_SEED (B gets seed + 1)
#   RUN_KEEP=1                    leave the last rig running at the end
# Rows per profile P: PStart (cold start, simulator where asked and nowhere in the control), PF1 PF2 PF3 (one per
# corpse, flamerace.py's verdict), and after the corpses the V400-2 counts from both dusk_lan.txt (printed).
# PASS per corpse (ab / ba): exactly one player got the Flame Virtue (FlameL counter +1 on the first presser,
#   +0 on the second), taken.py's data shows used = 1 and the same players on both games within 20 s, no counter
#   +2. A same-moment press (mode same) is judged by the design (taken_share_notes "Same-moment race"): both games
#   may grant inside one network delay + 250 ms, then BOTH must log "first-taker race" and agree; a strict
#   "exactly one" there is a design question, not this fix (notes 2).
# A corpse SKIP "no unused large Flame corpse" in Phase I (99281 appears from round 2 on some maps; 99282 was the
# proven one in Phase I): the phase is cut and the corpse tried once more in the next round.
# Rules (as runnet.sh): every step at most 10 minutes (STEP_MAX 600 s, python calls with time-outs); health
# between steps; a frozen game, a gone process or C: < 10 GB stops the run; the user's game / launcher running =
# nothing is started; at the end only the rig's processes are stopped (run3_check.py cleanup).
# Exit 0 = no FAIL, 1 = a FAIL, 2 = stopped early.

G=AB
RUN_NAME=runnet_flame
PROFILES=${RUNFLAME_ONLY:-control bad}
PLAN=${RUNFLAME_PLAN:-same:20 ab:0.3 ba:20}
GAP=${RUNFLAME_GAP:-3.5}
ROWS=
for p in $PROFILES; do ROWS="$ROWS ${p}Start ${p}F1 ${p}F2 ${p}F3"; done
source <WORKSPACE>/diag/twin/run_lib.sh
declare -A SIM=([control]="" [bad]="${RUNFLAME_SIM:-50,30,3,45,2000}")
for p in $PROFILES; do
    [ -n "${SIM[$p]+x}" ] || { echo "unknown profile '$p' (control bad)"; exit 2; }
done
for k in $ROWS; do RR[$k]="SKIP not reached"; done
# the stall period: 4th field of the bad profile (also used to time the control's presses the same way)
PERIOD=$(echo "${SIM[bad]}" | cut -d, -f4); PERIOD=${PERIOD:-45}
LOGS=diag/twin/runnet_flame_logs
mkdir -p "$LOGS"
LOG_A="$(cygpath -u "$APPDATA")/eden/log"
LOG_B=diag/twin/userB/log
export GO4_PHASE1=1 GO4_PHASE1_WAIT=420

precheck
say "profiles: $PROFILES; simulator ${SIM[bad]} on A and B in 'bad'; plan $PLAN (period $PERIOD s, gap $GAP s)"

wait_go() {   # wait_go FILE : 0 "nav done", 1 "FAILED:", 2 nothing in STEP_MAX s or go4b gone
    local t0 last= l
    t0=$(date +%s)
    while :; do
        grep -q '^nav done' "$1" 2>/dev/null && return 0
        grep -q '^FAILED:' "$1" 2>/dev/null && return 1
        [ $(( $(date +%s) - t0 )) -ge $STEP_MAX ] && return 2
        kill -0 "$GO_PID" 2>/dev/null || { grep -q '^nav done' "$1" && return 0; return 2; }
        l=$(tail -1 "$1" 2>/dev/null | cut -c1-150)
        [ "$l" != "$last" ] && { last=$l; say "  go4b: $l"; }
        sleep 10
    done
}
stop_rig() {
    [ -n "$GO_PID" ] || return 0
    hold_off
    say "rig stopped before the next cold start: $(PY 90 diag/twin/run3_check.py cleanup | tail -1)"
    kill "$GO_PID" 2>/dev/null
    GO_PID=
    unset LASTLOG LASTT; declare -gA LASTLOG LASTT
    sleep 15
}
simcounts() {   # simcounts GAME : the simulator's own lines in that game's emulator log
    local f
    if [ "$1" = A ]; then f="$LOG_A/eden_log.txt"; else f="$LOG_B/eden_log.txt"; fi
    [ -f "$f" ] || { echo "$1: no eden_log.txt"; return; }
    echo "$1: start '$(grep -m1 'NET SIM (TEST ONLY)' "$f" | sed 's/.*NET SIM (TEST ONLY): //' | cut -c1-160)'," \
         "errors $(grep -c "NET SIM: LICHII_NET_SIM=.*not understood" "$f")," \
         "stalls $(grep -c 'NET SIM: stall #' "$f")"
}
v400_counts() {   # the type-12 (V400-2) and type-13 (V400-1) lines of both games' dusk_lan.txt of this run
    local w f
    for w in A B; do
        if [ "$w" = A ]; then f="$LOG_A/dusk_lan.txt"; else f="$LOG_B/dusk_lan.txt"; fi
        [ -f "$f" ] || { say "v400 $w: no dusk_lan.txt"; continue; }
        cp "$f" "$LOGS/${1}_${w}_dusk_lan.txt" 2>/dev/null
        say "v400 $w: taken changes sent x7 $(grep -c 'sent to the others (x7' "$f"), sent x3 (old build)" \
            "$(grep -c 'sent to the others (x3' "$f"), applied from the other $(grep -c 'taken: .* from player .*applied' "$f")," \
            "first-taker races $(grep -c 'first-taker race' "$f"), holder races $(grep -c 'holder race' "$f")," \
            "cut-list answers $(grep -c 'cut check (V400-1): round' "$f") | $(grep 'sent to the others (x7' "$f" | grep -E 'flameL' | tail -3 | cut -c1-150 | tr '\n' ';')"
        echo "    (one 'sent' line per change: the assist does not log each of the 7 sends; cutcheck.py's health" \
             "section counts them per change the same way)"
    done
}
corpse() {   # corpse PROFILE N MODE AT
    local p=$1 n=$2 out l
    step "$p corpse $n ($3, first press at unix % $PERIOD = $4)"
    hold_on 300
    out=$(PY $STEP_MAX diag/twin/flamerace.py "$n" "$3" "period=$PERIOD" "at=$4" "gap=$GAP" games=AB)
    echo "$out" > "$LOGS/${p}_corpse$n.txt"
    echo "$out" | grep -E '^[0-9:]+ (corpse|presses)' | cut -c1-300
    l=$(echo "$out" | grep '^FLAME ' | tail -1)
    if [ -z "$l" ]; then
        row "${p}F$n" FAIL "flamerace.py: no result line (time-out or crash): $(echo "$out" | tail -2 | tr '\n' ' ' | cut -c1-200)"
        return
    fi
    row "${p}F$n" "$(echo "$l" | awk '{print $2}')" "$(echo "$l" | cut -d' ' -f3- | cut -c1-1200)"
}
next_round() {   # cut the phase (nothing usable left here) and wait for the next one
    local r
    r=$(steps | awk '{print $3}')
    hold_off
    cut_phase
    if ! wait_round $(( ${r:-1} + 1 )); then return 1; fi
    sleep 25                                          # the 20-second teleport rule
}

run_profile() {   # run_profile KEY
    local p=$1 sim=${SIM[$1]} gl=diag/twin/runnet_flame_go_$1.txt rc w n=0 item mode at
    say "==================== profile $p: LICHII_NET_SIM=${sim:-off} ${sim:+on A and B}"
    stop_rig
    STARTED=1
    hold_off
    local -a cmd=(env -u TWIN_NET_SIM_A -u TWIN_NET_SIM_B -u TWIN_NET_SIM_SEED_A -u TWIN_NET_SIM_SEED_B)
    [ -n "$sim" ] && cmd+=("TWIN_NET_SIM_A=$sim" "TWIN_NET_SIM_SEED_A=${RUNNET_SEED:-1}"
                           "TWIN_NET_SIM_B=$sim" "TWIN_NET_SIM_SEED_B=$(( ${RUNNET_SEED:-1} + 1 ))")
    "${cmd[@]}" TWIN_GAMES=AB bash diag/twin/go4b.sh > "$gl" 2>&1 &
    GO_PID=$!
    say "go4b.sh started (pid $GO_PID), output $gl"
    wait_go "$gl"; rc=$?
    case $rc in
        0) ;;
        1) row "${p}Start" FAIL "start: $(grep '^FAILED:' "$gl" | tail -1 | cut -c1-300)"; return 1;;
        *) row "${p}Start" FAIL "start: no nav done in $STEP_MAX s ($(tail -1 "$gl" | cut -c1-200))"; return 1;;
    esac
    local tw sa sb
    tw=$(grep '^twin4: game . LICHII_NET_SIM=' diag/twin/twin_console.log 2>/dev/null | tr '\n' ' ')
    sa=$(simcounts A); sb=$(simcounts B)
    if [ -n "$sim" ]; then
        for w in "$sa" "$sb"; do
            case "$w" in
                *"start ''"*) row "${p}Start" SKIP "no NET SIM start line ($w; twin4 '$tw'): build without netsim, or the variable did not arrive"; return 1;;
                *"errors 0"*) ;;
                *) row "${p}Start" SKIP "LICHII_NET_SIM='$sim' not understood ($w)"; return 1;;
            esac
        done
    else
        case "$sa$sb" in *"start ''"*"start ''"*) ;; *) row "${p}Start" FAIL "control run with a simulator on ($sa | $sb)"; return 1;; esac
    fi
    row "${p}Start" PASS "$(grep '^nav done' "$gl" | tail -1) | simulator: ${tw:-none} | $sa | $sb"
    sleep 25                                          # the 20-second teleport rule after Phase I starts
    for item in $PLAN; do
        n=$((n + 1)); [ $n -gt 3 ] && break
        mode=${item%%:*}; at=${item#*:}
        corpse "$p" "$n" "$mode" "$at"
        case "${RR[${p}F$n]}" in
            "SKIP"*"no unused large Flame corpse"*)
                say "nothing usable here: next phase, corpse $n once more"
                next_round || { say "next round not reached"; break; }
                corpse "$p" "$n" "$mode" "$at";;
        esac
    done
    hold_off
    say "simulator after the corpses: $(simcounts A) | $(simcounts B)"
    v400_counts "$p"
    return 0
}

for p in $PROFILES; do
    run_profile "$p"
    if [ -n "$GO_PID" ] && kill -0 "$GO_PID" 2>/dev/null; then health "after profile $p"; fi
done
finish 0
