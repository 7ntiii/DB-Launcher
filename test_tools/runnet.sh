#!/bin/bash
# runnet.sh: hands-free 2-game programme, one whole match three times on a simulated home network:
# clean (control), Wi-Fi-like, bad. Written 2026-11-16 as static work; never run yet. TEST RIG ONLY.
# Needs a build with diag/net/netsim.diff (LICHII_NET_SIM); without it the two impaired runs are SKIP.
#
#   bash diag/twin/runnet.sh          (Git Bash, from anywhere; log diag/twin/runnet.log, rows also appended to
#                                      diag/twin/runnet_results.txt, logs + cutcheck output in diag/twin/runnet_logs/)
# Options (environment):
#   RUNNET_ONLY="clean wifi bad"   the profiles to run, in this order (default all five: clean wifi bad
#                                  wifi_both bad_both; the _both ones put the simulator on A AND B)
#   RUNNET_SIM_GAMES=B             games that get the impairment (default B; AB = both directions: the simulator
#                                  only delays / drops SENDS, so B alone impairs B -> A only, netsim_notes.md)
#   RUNNET_SEED=1                  LICHII_NET_SIM_SEED (same seed = the same packets lost)
#   RUN_KEEP=1                     leave the last rig running at the end
# Profiles (LICHII_NET_SIM = delay_ms,jitter_ms,loss_percent[,stall_every_s,stall_ms]):
#   clean   no simulator (control; B's emulator log must have no NET SIM line)
#   wifi    20,10,1           20 ms delay, 10 ms jitter, 1 % loss
#   bad     50,30,3,45,2000   50 ms, 30 ms jitter, 3 % loss, a 2-s stall every 45 s
# How the variable reaches game B: go4b.sh starts twin4.py with the environment as it is; twin4.py turns
# TWIN_NET_SIM_<W> into LICHII_NET_SIM for game W only and prints "twin4: game B LICHII_NET_SIM=..."
# (twin4.py 89-95, netsim_notes.md "Giving it to game B only"). Checked here in twin_console.log and in B's
# eden_log.txt ("NET SIM (TEST ONLY)" at the first send).
#
# Per profile: cold start (go4b.sh, TWIN_GAMES=AB, until "nav done"), alive.sh / health, match4.py AB (whole match,
# hands-free), the two dusk_lan.txt copied, cutcheck.py on them (with its health section), the simulator's own
# counts from B's eden_log.txt, then the rig stopped (run3_check.py cleanup) before the next cold start.
# Printed after each: did both games finish all four rounds, do ranks agree, cutcheck's verdict, link health
# (ping range, timer gap, "not heard for 3 s" / "no side message" counts, timer corrections, network-clock moves,
# v400 resend counts when present). At the end a side-by-side table of the three.
# Rules (as run2.sh / run3.sh): no step waits more than 10 minutes (STEP_MAX 600 s); alive.sh / health between
# steps; a frozen game, a gone process or C: < 10 GB free stops the run; the user's game / launcher running =
# nothing is started; at the end only the rig's processes are stopped. go4b.sh itself stops every lichii.exe at
# its start (that is why the user's-game check comes first).
# Row per profile: PASS = 4 rounds on both games, ranks agree, cutcheck 0 flagged. Health BAD alone does not fail
# a row (it is what the impaired runs are for); it is printed. Exit 0 = no FAIL, 1 = a FAIL, 2 = stopped early.

G=AB
RUN_NAME=runnet
PROFILES=${RUNNET_ONLY:-clean wifi bad wifi_both bad_both}
ROWS="$PROFILES"
source <WORKSPACE>/diag/twin/run_lib.sh
declare -A SIM=([clean]="" [wifi]="20,10,1" [bad]="50,30,3,45,2000" [wifi_both]="20,10,1"
                [bad_both]="50,30,3,45,2000")
# the games that get the simulator per profile: the _both variants impair both directions (A and B);
# the others use RUNNET_SIM_GAMES (default B: B -> A only)
declare -A SIMG=([wifi_both]=AB [bad_both]=AB)
declare -A HSUM
for p in $PROFILES; do
    [ -n "${SIM[$p]+x}" ] || { echo "unknown profile '$p' (clean wifi bad wifi_both bad_both)"; exit 2; }
    RR[$p]="SKIP $p: not reached"
done
SIM_GAMES=${RUNNET_SIM_GAMES:-B}
LOGS=diag/twin/runnet_logs
mkdir -p "$LOGS"
LOG_A="$(cygpath -u "$APPDATA")/eden/log"
LOG_B=diag/twin/userB/log

precheck
say "profiles: $PROFILES; impairment on game(s) $SIM_GAMES (the _both profiles: AB), seed ${RUNNET_SEED:-1}"

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

stop_rig() {   # the rig's processes only, before the next cold start
    [ -n "$GO_PID" ] || return 0
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
         "stalls $(grep -c 'NET SIM: stall #' "$f")," \
         "last count '$(grep 'NET SIM: stall #' "$f" | tail -1 | sed 's/.*so far //' | cut -c1-120)'"
}

run_profile() {   # run_profile KEY
    local p=$1 sim=${SIM[$1]} gl=diag/twin/runnet_go_$1.txt envs="" w rc out rounds agree left four cc ccrc flagged
    local sg=${SIMG[$1]:-$SIM_GAMES}
    say "==================== profile $p: LICHII_NET_SIM=${sim:-off} on ${sim:+$sg}${sim:-no game}"
    stop_rig
    STARTED=1
    hold_off
    # Only the games of SIM_GAMES get TWIN_NET_SIM_<W>; every inherited one is removed first.
    local -a cmd=(env -u TWIN_NET_SIM_A -u TWIN_NET_SIM_B -u TWIN_NET_SIM_SEED_A -u TWIN_NET_SIM_SEED_B)
    if [ -n "$sim" ]; then
        for w in $(echo "$sg" | sed 's/./& /g'); do
            cmd+=("TWIN_NET_SIM_$w=$sim" "TWIN_NET_SIM_SEED_$w=${RUNNET_SEED:-1}")
            envs="$envs $w"
        done
    fi
    "${cmd[@]}" TWIN_GAMES=AB bash diag/twin/go4b.sh > "$gl" 2>&1 &
    GO_PID=$!
    say "go4b.sh started (pid $GO_PID), output $gl"
    wait_go "$gl"; rc=$?
    case $rc in
        0) say "start: $(grep '^nav done' "$gl" | tail -1) | $(grep '^server match:' "$gl" | tail -1 | cut -c1-160)";;
        1) row "$p" FAIL "start: $(grep '^FAILED:' "$gl" | tail -1 | cut -c1-300)"; return 1;;
        *) row "$p" FAIL "start: no nav done in $STEP_MAX s ($(tail -1 "$gl" | cut -c1-200))"; return 1;;
    esac
    # The simulator must be on exactly where it was asked for (and nowhere in the control run).
    local tw sc_a sc_b sc f
    tw=$(grep '^twin4: game . LICHII_NET_SIM=' diag/twin/twin_console.log 2>/dev/null | tr '\n' ' ')
    sc_a=$(simcounts A); sc_b=$(simcounts B)
    say "simulator: twin4 '${tw:-none}' | $sc_a | $sc_b"
    if [ -n "$sim" ]; then
        for w in $envs; do
            if [ "$w" = A ]; then sc=$sc_a; else sc=$sc_b; fi
            case "$sc" in
                *"start ''"*) row "$p" SKIP "game $w has no NET SIM start line: this build has no netsim.diff, or the variable did not arrive ($tw)"; return 1;;
                *"errors 0"*) ;;
                *) row "$p" SKIP "game $w: LICHII_NET_SIM='$sim' not understood (network NOT impaired)"; return 1;;
            esac
        done
    else
        case "$sc_a$sc_b" in *"start ''"*"start ''"*) ;; *) row "$p" FAIL "control run with a simulator on ($sc_a | $sc_b)"; return 1;; esac
    fi
    step "$p: whole match (match4.py AB)"
    out=$(PY $STEP_MAX diag/twin/match4.py AB --start-wait 420 --limit $((STEP_MAX - 20)))
    echo "$out" > "$LOGS/${p}_match4.txt"
    echo "$out" | grep -E 'round [0-9] snapshot|ranks|WARNING|FAILED|done' | tail -12
    rounds=$(echo "$out" | grep -E '^match4 (done|FAILED)' | tail -1 | grep -o 'rounds \[[0-9, ]*\]' | head -1)
    agree=$(echo "$out" | grep '^ranks agree on all games:' | tail -1 | awk '{print $NF}')
    # match4 marks EVERY game "[left at step 36 round 4]" at the normal end (the Outcome): only a game seen out
    # before round 4 left early (fixed 2026-11-17: the first run said "not all four rounds" with all four)
    left=$(echo "$out" | grep -cE '\[left at step [0-9]+ round [1-3]\]')
    four=no
    case "$rounds" in *1*2*3*4*) [ "$left" = 0 ] && four=yes;; esac
    # The logs of this run (the assist starts a new dusk_lan.txt per emulator run, so this is this run's).
    for w in A B; do
        if [ "$w" = A ]; then f="$LOG_A"; else f="$LOG_B"; fi
        cp "$f/dusk_lan.txt" "$LOGS/${p}_${w}_dusk_lan.txt" 2>/dev/null || say "warning: $f/dusk_lan.txt missing"
        cp "$f/eden_log.txt" "$LOGS/${p}_${w}_eden_log.txt" 2>/dev/null
    done
    cc=$(PY 300 diag/twin/cutcheck.py "A:$LOGS/${p}_A_dusk_lan.txt" "B:$LOGS/${p}_B_dusk_lan.txt" --quiet)
    ccrc=$?
    echo "$cc" > "$LOGS/${p}_cutcheck.txt"
    flagged=$(echo "$cc" | grep 'disagreement(s) flagged' | tail -1 | awk '{print $1}')
    say "result $p: four rounds on both games: $four (${rounds:-no rounds line}, $left game(s) left early);" \
        "ranks agree: ${agree:-no line}; cutcheck: ${flagged:-?} flagged (rc $ccrc)"
    echo "$cc" | grep '!!' | head -5
    echo "$cc" | sed -n '/=== health/,/disagreement(s) flagged/p' | grep -v 'disagreement(s) flagged'
    say "simulator after the match: $(simcounts A) | $(simcounts B)"
    HSUM[$p]=$(python - "$LOGS/${p}_A_dusk_lan.txt" "$LOGS/${p}_B_dusk_lan.txt" <<'PYEOF' 2>&1
import sys
sys.path.insert(0, 'diag/twin')
import cutcheck
out = []
for path, w in zip(sys.argv[1:], 'AB'):
    try:
        h = cutcheck.health_of(path)
    except OSError:
        out.append(f'{w}: no log')
        continue
    p = sorted(h['pings'])
    acks = '/'.join(str(n) for _, n, _ in h['acks']) or '-'
    out.append(f'{w}: ping {p[0] if p else "?"}-{p[-1] if p else "?"} gapmax {max(h["gaps"]) if h["gaps"] else 0:.2f} '
               f'silent {h["silent_play"]}+{h["silent_other"]} notheard {h["notheard_play"]}+{h["notheard_other"]} '
               f'corr #{h["corr_max"]} clk {len(h["netclk"])} taken {h["taken_out"]}/{h["taken_in"]} '
               f'acks {acks} ooo {h["old_dropped"]}')
print(' | '.join(out))
PYEOF
)
    local verdict=PASS why=""
    [ "$four" = yes ] || { verdict=FAIL; why="$why not all four rounds;"; }
    [ "$agree" = yes ] || { verdict=FAIL; why="$why ranks ${agree:-unknown};"; }
    [ "${flagged:-x}" = 0 ] || { verdict=FAIL; why="$why cutcheck ${flagged:-rc $ccrc} flagged;"; }
    local hb
    hb=$(echo "$cc" | grep 'HEALTH ' | sed 's/^ *//' | tr '\n' ' ')
    row "$p" "$verdict" "${why:+$why }${rounds:-?}, ranks ${agree:-?}, cutcheck ${flagged:-?} | $hb| $LOGS/${p}_cutcheck.txt"
    return 0
}

for p in $PROFILES; do
    run_profile "$p"
    # Health between programmes only while a rig runs (a failed start has none to check).
    if [ -n "$GO_PID" ] && kill -0 "$GO_PID" 2>/dev/null; then health "after profile $p"; fi
done

echo
echo "==================== link values side by side (A | B; ping ms, timer gap max s, silences in play+elsewhere," \
     "Virtue not-heard in play+elsewhere, highest timer correction, network-clock moves, taken sent/applied," \
     "cut-list sends per cut (v400), type-1 out of order (v400)) ===================="
for p in $PROFILES; do
    printf '%-9s %-16s %-3s %s\n' "$p" "${SIM[$p]:-off}" "${SIM[$p]:+${SIMG[$p]:-$SIM_GAMES}}" \
        "${HSUM[$p]:-not run}"
    echo "$(date '+%F %T') HEALTH $p ${SIM[$p]:-off} ${HSUM[$p]:-not run}" >> "$RES"
done
finish 0
