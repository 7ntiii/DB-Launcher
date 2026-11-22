#!/bin/bash
# GUARD 2026-11-16: the user allows at most TWO games on this PC (a 4-game run froze it). Do not remove.
if [ "${USER_SAID_MORE_THAN_TWO_GAMES:-0}" != "1" ]; then echo "REFUSED: more than two games on this PC is not allowed (user rule 2026-11-16)"; exit 9; fi
# runnet3.sh: one whole 3-game match on a simulated bad home network, hands-free. Written 2026-11-17 as static
# work; never run yet. TEST RIG ONLY. The 3-game companion of runnet.sh (2 games, five profiles).
#
#   bash diag/twin/runnet3.sh     (Git Bash, from anywhere; log diag/twin/runnet3.log, rows also appended to
#                                  diag/twin/runnet3_results.txt; logs + cutcheck in diag/twin/runnet3_logs/)
# Options (environment):
#   RUNNET3_SIM=50,30,3,45,2000   LICHII_NET_SIM for games B and C (default the "bad" profile: 50 ms, 30 ms
#                                 jitter, 3 % loss, a 2-s stall every 45 s); A (host) runs without it
#   RUNNET_SEED=1                 seed for B (C gets seed + 1: different packets lost)
#   RUN_KEEP=1                    leave the rig running at the end
# What it does (each step at most 10 minutes: STEP_MAX 600 s; the cold start: 600 s without a new go4b line,
# 1200 s in all for three boots and three hub loads):
#   1. cold start: go4b.sh with TWIN_GAMES=ABC (twin4.py: lazy commit + texture caps for C, one boot at a time;
#      crashC2_notes.md 4), TWIN_NET_SIM_B / _C set, every other TWIN_NET_SIM_* removed. Row start.
#   2. the simulator where it was asked for: run4_check.py netsim BC must PASS, netsim A must say "not active on
#      A". Row sim.
#   3. numbering (the audit's 3-player risk): every game's own player number read at the start
#      (run4_check.py nos ABC): all three known and all different. Row nums.
#   4. match4.py ABC in the background (whole match, hands-free) with --final-wait 300: in the final it waits
#      300 s before it cuts the clock, so step 5 can land an elimination first.
#   5. the final: 20 s in, A (host) kills C (a guest with the simulator) twice with real hits (run4_check.py
#      kill2 A C); 15 s later run4_check.py finalstate ABC C: C at its result screen, A and B still play the
#      final, both logged "player <C> is out of the final", no "review3 F1 bound" run-down. Row out.
#   6. match4 ends the final by the clock; its "match4 done" line, all four rounds, no game out before round 4,
#      ranks agree. Row match.
#   7. run4_check.py final ABC ABC: result ranks equal on all three, the "final placement" line present and
#      equal on all three, no run-down. Row final.
#   8. cutcheck.py with its health section on the three dusk_lan.txt (copies in runnet3_logs/). Row log
#      (PASS = 0 disagreements); the HEALTH lines go into the row, a HEALTH BAD alone does not fail it.
# Between steps: alive.sh / health (frozen game, gone process, C: < 10 GB free stop the run). The user's game /
# launcher running = nothing is started. At the end only the rig's processes are stopped.
# Exit 0 = no FAIL, 1 = a FAIL, 2 = stopped early.

G=ABC
RUN_NAME=runnet3
ROWS="start sim nums out match final log"
source <WORKSPACE>/diag/twin/run_lib.sh
for k in $ROWS; do RR[$k]="SKIP not reached"; done
SIM3=${RUNNET3_SIM:-50,30,3,45,2000}
SEED=${RUNNET_SEED:-1}
LOGS=diag/twin/runnet3_logs
mkdir -p "$LOGS"
R4() { PY "$1" diag/twin/run4_check.py "${@:2}"; }
M4OUT=diag/twin/runnet3_match4.txt
M4_PID=

precheck
say "LICHII_NET_SIM=$SIM3 on B (seed $SEED) and C (seed $((SEED + 1))); A clean"

# ------------------------------------------------------------------ 1. cold start
wait_go3() {   # wait_go3 FILE : 0 nav done, 1 FAILED line, 2 stall / total time-out / go4b gone
    local t0 tl n last=-1
    t0=$(date +%s); tl=$t0
    while :; do
        grep -q '^nav done' "$1" 2>/dev/null && return 0
        grep -q '^FAILED:' "$1" 2>/dev/null && return 1
        n=$(wc -l < "$1" 2>/dev/null)
        if [ "${n:-0}" != "$last" ]; then last=${n:-0}; tl=$(date +%s); say "  go4b: $(tail -1 "$1" | cut -c1-150)"; fi
        [ $(( $(date +%s) - tl )) -ge $STEP_MAX ] && return 2
        [ $(( $(date +%s) - t0 )) -ge $((2 * STEP_MAX)) ] && return 2
        kill -0 "$GO_PID" 2>/dev/null || { grep -q '^nav done' "$1" && return 0; return 2; }
        sleep 10
    done
}
gl=diag/twin/runnet3_go.txt
STARTED=1
hold_off
env -u TWIN_NET_SIM_A -u TWIN_NET_SIM_D -u TWIN_NET_SIM_SEED_A -u TWIN_NET_SIM_SEED_D \
    TWIN_NET_SIM_B="$SIM3" TWIN_NET_SIM_SEED_B="$SEED" TWIN_NET_SIM_C="$SIM3" TWIN_NET_SIM_SEED_C=$((SEED + 1)) \
    TWIN_GAMES=ABC DUSK_MATCH_MIN=3 bash diag/twin/go4b.sh > "$gl" 2>&1 &
GO_PID=$!
say "go4b.sh started (pid $GO_PID), output $gl"
wait_go3 "$gl"; rc=$?
case $rc in
    0) row start PASS "$(grep '^nav done' "$gl" | tail -1) | $(grep '^server match:' "$gl" | tail -1 | cut -c1-200)";;
    1) row start FAIL "$(grep '^FAILED:' "$gl" | tail -1 | cut -c1-300)"; finish 2 "cold start failed";;
    *) row start FAIL "no nav done (stall $STEP_MAX s / total $((2 * STEP_MAX)) s): $(tail -1 "$gl" | cut -c1-200)"
       finish 2 "cold start failed";;
esac

# ------------------------------------------------------------------ 2. simulator on B and C only
step "simulator check"
on=$(R4 60 netsim BC | grep '^NETSIM' | tail -1)
off=$(R4 60 netsim A | grep '^NETSIM' | tail -1)
case "$on|$off" in
    "NETSIM PASS"*"|NETSIM FAIL not active on A"*) row sim PASS "B, C: ${on#NETSIM PASS } || A off";;
    *) row sim FAIL "B, C: $on || A: $off"; finish 2 "the simulator is not where it should be";;
esac

# ------------------------------------------------------------------ 3. numbering
step "player numbers"
map=$(R4 90 nos ABC | tail -1 | tr -d '\r')
nums=$(echo "$map" | tr ' ' '\n' | cut -d= -f2)
known=$(echo "$nums" | grep -cE '^[1-9][0-9]*$')
uniq=$(echo "$nums" | grep -E '^[1-9][0-9]*$' | sort -u | wc -l)
if [ "$known" = 3 ] && [ "$uniq" = 3 ]; then
    row nums PASS "own player numbers $map: all known, all different"
else
    row nums FAIL "own player numbers '$map': $known known, $uniq different (want 3 and 3)"
fi
NO_C=$(echo "$map" | tr ' ' '\n' | grep '^C=' | cut -d= -f2)

# ------------------------------------------------------------------ 4. the whole match in the background
step "whole match (match4.py ABC, --final-wait 480: sleep 20 + kill2 up to 400 s must fit)"
python diag/twin/match4.py ABC --start-wait 420 --final-wait 480 --limit 2400 > "$M4OUT" 2>&1 &
M4_PID=$!
say "match4.py started (pid $M4_PID), output $M4OUT"
stop_m4() { [ -n "$M4_PID" ] && kill "$M4_PID" 2>/dev/null; M4_PID=; }
trap 'stop_m4; finish 2 "interrupted"' INT TERM

# Phases I-III are cut by match4 (10 s into each); wait for the final, in 10-minute steps, health in between.
for r in 1 2 3 4; do
    if ! wait_round "$r"; then
        grep -E '^match4 (done|FAILED)' "$M4OUT" | tail -1
        stop_m4
        row match FAIL "round $r not on every game in $STEP_MAX s ($(steps)) | $(tail -2 "$M4OUT" | tr '\n' ' ' | cut -c1-200)"
        finish 2 "round $r not reached"
    fi
    kill -0 "$M4_PID" 2>/dev/null || { row match FAIL "match4 ended before round $r: $(tail -1 "$M4OUT" | cut -c1-200)"; finish 2 "match4 gone"; }
done

# ------------------------------------------------------------------ 5. elimination in the final
step "final: A eliminates C"
sleep 20                                             # no teleport in the first ~20 s of the final
out=$(R4 400 kill2 A C)
say "kill2 A -> C: $(echo "$out" | grep '^KILL2' | tail -1 | cut -c1-300)"
case "$(echo "$out" | grep '^KILL2' | tail -1)" in
    "KILL2 PASS"*) sleep 15
                   l=$(R4 120 finalstate ABC C | grep '^OUT ' | tail -1)
                   if [ -n "$l" ]; then row out "$(echo "$l" | awk '{print $2}')" "$(echo "$l" | cut -d' ' -f3-)"
                   else row out FAIL "finalstate gave no OUT line"; fi;;
    *) row out FAIL "kill2 A C (player ${NO_C:-?}): $(echo "$out" | grep '^KILL2' | tail -1 | cut -c1-300)";;
esac
say "lives: $(PY 90 diag/twin/lives.py ABC | tr '\n' ';' | cut -c1-600)"

# ------------------------------------------------------------------ 6. match4 ends the final
step "end of the match (match4 cuts the final)"
t0=$(date +%s)
while kill -0 "$M4_PID" 2>/dev/null && [ $(( $(date +%s) - t0 )) -lt $STEP_MAX ]; do sleep 10; done
if kill -0 "$M4_PID" 2>/dev/null; then
    stop_m4
    row match FAIL "match4 still running $STEP_MAX s after the elimination: $(tail -1 "$M4OUT" | cut -c1-200)"
else
    M4_PID=
    m=$(grep -E '^match4 (done|FAILED)' "$M4OUT" | tail -1)
    rounds=$(echo "$m" | grep -o 'rounds \[[0-9, ]*\]' | head -1)
    agree=$(grep '^ranks agree on all games:' "$M4OUT" | tail -1 | awk '{print $NF}')
    # every game is marked "[left at step 36 round 4]" at the normal end; C leaves in round 4 by its
    # elimination; only a game out before round 4 left early
    early=$(grep -cE '\[left at step [0-9]+ round [1-3]\]' "$M4OUT")
    grep -E 'ranks \(|left the match|not in UpdatePhase any more' "$M4OUT" | tail -8
    v=PASS why=
    case "$rounds" in *1*2*3*4*) ;; *) v=FAIL; why="$why not all four rounds;";; esac
    [ "$early" = 0 ] || { v=FAIL; why="$why $early game(s) out before round 4;"; }
    [ "$agree" = yes ] || { v=FAIL; why="$why ranks ${agree:-unknown};"; }
    row match "$v" "${why:+$why }${m:-no match4 end line} | ranks agree ${agree:-?}"
fi

# ------------------------------------------------------------------ 7. final placement on all three
sleep 15
l=$(R4 120 final ABC ABC | grep '^FINAL ' | tail -1)
if [ -n "$l" ]; then row final "$(echo "$l" | awk '{print $2}')" "$(echo "$l" | cut -d' ' -f3- | cut -c1-500)"
else row final FAIL "run4_check.py final gave no FINAL line"; fi

# ------------------------------------------------------------------ 8. logs: cutcheck + health on three games
step "logs"
la="$(cygpath -u "$APPDATA")/eden/log"
for w in A B C; do
    if [ "$w" = A ]; then f=$la; else f=diag/twin/user$w/log; fi
    cp "$f/dusk_lan.txt" "$LOGS/${w}_dusk_lan.txt" 2>/dev/null || say "warning: $f/dusk_lan.txt missing"
    cp "$f/eden_log.txt" "$LOGS/${w}_eden_log.txt" 2>/dev/null
done
cc=$(PY 300 diag/twin/cutcheck.py "A:$LOGS/A_dusk_lan.txt" "B:$LOGS/B_dusk_lan.txt" "C:$LOGS/C_dusk_lan.txt" --quiet)
ccrc=$?
echo "$cc" > "$LOGS/cutcheck.txt"
echo "$cc" | grep '!!' | head -5
echo "$cc" | sed -n '/=== health/,/disagreement(s) flagged/p' | grep -v 'disagreement(s) flagged'
flagged=$(echo "$cc" | grep 'disagreement(s) flagged' | tail -1 | awk '{print $1}')
hb=$(echo "$cc" | grep 'HEALTH ' | sed 's/^ *//' | tr '\n' ' ' | cut -c1-500)
if [ "${flagged:-x}" = 0 ]; then row log PASS "cutcheck 0 flagged | $hb| $LOGS/cutcheck.txt"
else row log FAIL "cutcheck ${flagged:-rc $ccrc} flagged | $hb| $LOGS/cutcheck.txt"; fi
for w in B C; do
    f="$LOGS/${w}_eden_log.txt"
    [ -f "$f" ] && say "simulator $w: start lines $(grep -c 'NET SIM (TEST ONLY)' "$f"), stalls $(grep -c 'NET SIM: stall #' "$f")"
done

finish 0
