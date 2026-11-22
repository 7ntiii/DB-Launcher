#!/bin/bash
# run2.sh: hands-free 2-game programme in the order of diag/net/fasttests_v393.md section 2, from a cold start.
# Written 2026-11-16 as static work; never run yet. TEST RIG ONLY.
#
#   bash diag/twin/run2.sh            (Git Bash, from anywhere; log diag/twin/run2.log, rows also appended to
#                                      diag/twin/run2_results.txt; RUN_KEEP=1 leaves the rig running at the end)
# Shared parts: diag/twin/run_lib.sh (health, tagged clock hold, rows, cleanup). Helper: diag/twin/run3_check.py.
#
# Programme (games A B, A = host):
#   start        go_hub.sh (background: old rig stopped, twin.py, both games to the hub) until "hub-ready"
#   hub          pick_sigil.py B 600040 (Samir with the sigil)                        -> row hub (setup for 33b-ii)
#                then to_match2.py, then Phase I on both games
#   Phase I      sigils.py AB + virtue.py AB, love_accept.py B A                       -> row 33b-ii
#                regress_small.py markers pin_place games=AB actor=B (MANUAL shots) + mapdiff.py of the pin
#                shots                                                                  -> row 54
#   intermission cut, then at once regress_small.py start_area actor=B, startarea.py AB -> row 14
#   Phase II     regress_small.py kin_summon kin_recall actor=B, kinstate.py AB nocircles -> row 28r
#   logs         cutcheck.py on both dusk_lan.txt (copies in diag/twin/run2_logs/)     -> row cut
# Rules (as run3.sh): every step first stops any hold_clock.py that is not the current tagged holder, and every
# holder before a cut; no step waits more than 10 minutes (timeouts everywhere); alive.sh between steps; a frozen
# game, a gone process or C: < 10 GB free stops the run (rows left SKIP); the user's game / launcher running =
# nothing is started; at the end only the rig's processes are stopped. Note: go_hub.sh itself stops every
# lichii.exe at its start (that is why the user's-game check comes first).
# Exit 0 = no FAIL, 1 = a FAIL, 2 = stopped early.

G=AB
RUN_NAME=run2
ROWS="start hub 33b-ii 54 14 28r cut"
source <WORKSPACE>/diag/twin/run_lib.sh
RR[start]="SKIP go_hub start: not reached"
RR[hub]="SKIP pick_sigil B 600040: not reached"
RR[33b-ii]="SKIP love_accept B A: not reached"
RR[54]="SKIP markers + pin_place: not reached"
RR[14]="SKIP start_area: not reached"
RR[28r]="SKIP kin_summon + kin_recall: not reached"
RR[cut]="SKIP cutcheck: not reached"

precheck

# ------------------------------------------------------------------ 1. cold start to the hub
STARTED=1
hold_off
GL=diag/twin/run2_go.txt
DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 \
    bash diag/twin/go_hub.sh > "$GL" 2>&1 &
GO_PID=$!
say "go_hub.sh started (pid $GO_PID), output $GL"
wait_log "$GL" '^hub-ready' '^FAILED|Traceback' $STEP_MAX
case $? in
    0) row start PASS "go_hub: hub-ready | $(grep -i 'hub in' "$GL" | tr '\n' ' ' | cut -c1-200)";;
    *) row start FAIL "go_hub: no hub-ready in $STEP_MAX s ($(tail -2 "$GL" | tr '\n' ' ' | cut -c1-200))"
       finish 2 "the cold start failed";;
esac

# ------------------------------------------------------------------ 2. hub: Bloodsworn with the sigil, then the match
step "hub: pick_sigil B 600040"
OUTH=$(PY 300 diag/twin/pick_sigil.py B 600040)
RCH=$?
LH=$(echo "$OUTH" | grep -E 'DONE|NOT DONE|already chosen|STOP' | tail -2 | tr '\n' ' ')
if [ $RCH = 0 ]; then row hub PASS "pick_sigil: $LH"; else row hub FAIL "pick_sigil rc $RCH: ${LH:-$(echo "$OUTH" | tail -2 | tr '\n' ' ')}"; fi
step "to_match2"
OUTM=$(TWIN_GAMES=$G PY $STEP_MAX diag/twin/to_match2.py)
RCM=$?
echo "$OUTM" | tail -3
[ $RCM = 0 ] || finish 2 "to_match2 rc $RCM: not every game joined ($(echo "$OUTM" | tail -1 | cut -c1-200))"
wait_round 1 || finish 2 "Phase I not on every game"

# ------------------------------------------------------------------ 3. Phase I: love accept (33b-ii), markers + pins (54)
hold_on 300
sleep 25                                              # no teleport in the first ~20 s of a phase
step "Phase I: love_accept B A"
say "sigils: $(PY 90 diag/twin/sigils.py $G | grep -E '240|250|list' | tr '\n' ';' | cut -c1-400)"
say "virtue before: $(PY 90 diag/twin/virtue.py $G | grep -iE 'total|banked' | head -6 | tr '\n' ';' | cut -c1-400)"
if [ "${RR[hub]%% *}" = PASS ]; then
    OUTL=$(PY 300 diag/twin/love_accept.py B A)
    LL=$(echo "$OUTL" | grep -E '^RESULT|^SETUP FAIL' | tail -1)
    VL=$(echo "$OUTL" | grep -i 'virtue' | tail -2 | tr '\n' ' ' | cut -c1-300)
    case "$LL" in
        "RESULT PASS"*)    row 33b-ii PASS "love_accept: ${LL#RESULT PASS: } | $VL";;
        "RESULT PARTIAL"*) row 33b-ii PARTIAL "love_accept: ${LL#RESULT PARTIAL: } | $VL";;
        "SETUP FAIL"*)     row 33b-ii SKIP "love_accept: $LL | $VL";;
        "")                row 33b-ii FAIL "love_accept: no RESULT line (timeout or crash): $(echo "$OUTL" | tail -2 | tr '\n' ' ' | cut -c1-200)";;
        *)                 row 33b-ii FAIL "love_accept: ${LL#RESULT } | $VL";;
    esac
else
    row 33b-ii SKIP "love_accept: the hub pick of B 600040 did not succeed"
fi
say "virtue after: $(PY 90 diag/twin/virtue.py $G | grep -iE 'total|banked' | head -6 | tr '\n' ';' | cut -c1-400)"

step "Phase I: markers pin_place"
OUTP=$(PY $STEP_MAX diag/twin/regress_small.py markers pin_place games=$G actor=B)
MK=$(echo "$OUTP" | grep "^RESULT markers " | tail -1 | awk '{print $3}')
PP=$(echo "$OUTP" | grep "^RESULT pin_place " | tail -1 | awk '{print $3}')
# pin_place / markers judge per game with mapdiff.py themselves (menus_notes.md 6: pins personal, rivals never see
# them; the host must see the moved actor's marker). Row 54 = both RESULT statuses.
V54="markers ${MK:-none}: $(echo "$OUTP" | grep "^RESULT markers " | tail -1 | cut -d: -f2- | cut -c1-250) || pin_place ${PP:-none}: $(echo "$OUTP" | grep "^RESULT pin_place " | tail -1 | cut -d: -f2- | cut -c1-250)"
if [ "$MK" = FAIL ] || [ "$PP" = FAIL ]; then
    row 54 FAIL "$V54"
elif [ "$MK" = PASS ] && [ "$PP" = PASS ]; then
    row 54 PASS "$V54"
elif [ -z "$MK$PP" ]; then
    row 54 FAIL "markers + pin_place: no RESULT line (timeout or crash): $(echo "$OUTP" | tail -2 | tr '\n' ' ' | cut -c1-200)"
else
    row 54 SKIP "$V54"
fi

# ------------------------------------------------------------------ 4. intermission: start-area pick (14)
step "cut Phase I"
cut_phase
say "=== step: intermission start_area (right after the cut: no health check in between)"
OUTS=$(PY $STEP_MAX diag/twin/regress_small.py start_area games=$G actor=B)
rs_row 14 start_area "$OUTS"
health "after start_area"

# ------------------------------------------------------------------ 5. Phase II: kin summon + recall (28r)
if wait_round 2; then
    hold_on 300
    sleep 25
    say "startarea in Phase II: $(PY 90 diag/twin/startarea.py $G | tail -4 | tr '\n' ';' | cut -c1-400)"
    step "Phase II: kin_summon kin_recall"
    # two calls: kin_summon (240) + kin_recall (240) + two settles could pass STEP_MAX in one process
    OUTK=$(PY $STEP_MAX diag/twin/regress_small.py kin_summon games=$G actor=B)
    KS=$(echo "$OUTK" | grep "^RESULT kin_summon " | tail -1 | awk '{print $3}')
    if [ "$KS" = PASS ]; then
        OUTK="$OUTK
$(PY $STEP_MAX diag/twin/regress_small.py kin_recall games=$G actor=B)"
    fi
    say "kinstate: $(PY 90 diag/twin/kinstate.py $G nocircles | tr '\n' ';' | cut -c1-500)"
    if [ "$KS" = PASS ] || [ "$KS" = SETUP ]; then
        rs_row 28r kin_recall "$OUTK"
        RR[28r]="${RR[28r]} (kin_summon $KS)"
    else
        row 28r SKIP "kin_recall: no kin (kin_summon ${KS:-no RESULT}): $(echo "$OUTK" | grep '^RESULT' | tr '\n' ' ' | cut -c1-300)"
    fi
    step "end of Phase II"
    hold_off
else
    row 28r SKIP "kin_summon + kin_recall: Phase II not reached on every game in $STEP_MAX s ($(steps))"
fi

# ------------------------------------------------------------------ 6. the dusk_lan logs so far
say "=== step: cutcheck (logs only)"
hc_stray
cutcheck_row cut

finish 0
