#!/bin/bash
# GUARD 2026-11-16: the user allows at most TWO games on this PC (a 4-game run froze it). Do not remove.
if [ "${USER_SAID_MORE_THAN_TWO_GAMES:-0}" != "1" ]; then echo "REFUSED: more than two games on this PC is not allowed (user rule 2026-11-16)"; exit 9; fi
# run3.sh: the whole 3-game programme (diag/net/fasttests_v39.md "RUN 2") hands-free from a cold start.
# Written 2026-11-15, revised 2026-11-16 with the lead's manual run; never run as a script yet. TEST RIG ONLY.
#
#   bash diag/twin/run3.sh            (Git Bash, from anywhere; log diag/twin/run3.log, rows also appended to
#                                      diag/twin/run3_results.txt; RUN_KEEP=1 leaves the rig running at the end)
# Shared parts: diag/twin/run_lib.sh (health, clock hold, rows, cleanup). Helper: diag/twin/run3_check.py.
#
# Programme (games A B C, A = host) and the timings of the manual run 2026-11-16:
#   start     TWIN_GAMES=ABC GO4_PHASE1=1 bash diag/twin/go4.sh (background) until "nav done" (380 s; cap 600 s)
#   Phase I   health only, plus regress_small arm_1300 games=ABC (bell event for Phase II), then the cut
#   Phase II  regress_small lever_bell games=ABC                                                 -> row 57
#   Phase III regress_small ally_form games=ABC actor=B (SETUP, counts 1 on all three, 73 s); then the Virtue
#             share: clock held at 95 s with nohp (the Ritual Site opens with under ~100 s left), run3_check.py
#             site A C B ABC = A kills C at a pledge pillar of the open site; B's counter 10040 must rise on
#             B and on A's and C's copies                                                         -> row 35 part
#   final     holder stopped, to_final.py 420 ("final reached" took 380 s), regress_small alliance_end -> row 18
#             30 s, regress_small spectate games=ABC, lives.py ABC, final_kills.py ABC, run3_check.py final C ABC
#             (stage 04050101, OUT bit, elimination once, others at step 6)                       -> row 19
#   logs      cutcheck.py on the three dusk_lan.txt (copies in diag/twin/run3_logs/)              -> row cut
# Every step first stops any hold_clock.py that is not the current tagged holder, and EVERY holder before a cut or
# to_final (a leftover holder kept resetting the clock in the manual run, so the phase never ended).
# No single step waits more than 10 minutes; health (alive.sh + C's log + pids + C: free) between steps; a frozen
# game, a gone process or C: < 10 GB free stops the run (rows left SKIP). At the end only the rig's processes are
# stopped (run3_check.py cleanup). The user's game / launcher running = nothing is started.
# Exit 0 = no FAIL, 1 = a FAIL, 2 = stopped early.

G=ABC
RUN_NAME=run3
ROWS="start 57 54p 35p 18 19 cut"
source <WORKSPACE>/diag/twin/run_lib.sh
RR[start]="SKIP go4 start: not reached"
RR[57]="SKIP lever_bell: not reached"
RR[54p]="SKIP pin_place + markers with an alliance: not reached"
RR[35p]="SKIP alliance Virtue share: not reached"
RR[18]="SKIP alliance_end: not reached"
RR[19]="SKIP spectate: not reached"
RR[cut]="SKIP cutcheck: not reached"

precheck

# ------------------------------------------------------------------ 1. cold start
STARTED=1
hold_off
GL=diag/twin/run3_go4.txt
GO4_PHASE1=1 bash diag/twin/go4.sh > "$GL" 2>&1 &
GO_PID=$!
say "go4.sh started (pid $GO_PID), output $GL"
wait_log "$GL" '^nav done' '^FAILED:' $STEP_MAX
case $? in
    0) row start PASS "go4: $(grep '^nav done' "$GL" | tail -1) | $(grep '^server match:' "$GL" | tail -1 | cut -c1-200)";;
    1) row start FAIL "go4: $(grep '^FAILED:' "$GL" | tail -1 | cut -c1-300)"; finish 2 "the cold start failed";;
    *) row start FAIL "go4: no nav done in $STEP_MAX s ($(tail -1 "$GL" | cut -c1-200))"; finish 2 "the cold start failed";;
esac

# ------------------------------------------------------------------ 2. Phase I: health + bell arming
wait_round 1 || finish 2 "Phase I not on every game"
hold_on 300
sleep 25                                              # no teleport / arming in the first ~20 s of a phase
step "Phase I: arm_1300"
OUT1=$(PY 300 diag/twin/regress_small.py arm_1300 games=$G)
echo "$OUT1" | grep "^RESULT" | cut -c1-400
ARM=$(echo "$OUT1" | grep "^RESULT arm_1300 " | awk '{print $3}')
[ "$ARM" = SETUP ] || say "arm_1300 gave '${ARM:-no RESULT}': lever_bell will SKIP if 1300 is not current"
step "cut Phase I"
cut_phase

# ------------------------------------------------------------------ 3. Phase II: bell (row 57)
if wait_round 2; then
    hold_on 300
    sleep 25
    step "Phase II: lever_bell"
    say "levers before: $(PY 60 diag/twin/levers.py $G | grep -i '#0' | tr '\n' ' ' | cut -c1-300)"
    OUT2=$(PY $STEP_MAX diag/twin/regress_small.py lever_bell games=$G)
    rs_row 57 lever_bell "$OUT2"
else
    row 57 SKIP "lever_bell: Phase II not reached on every game in $STEP_MAX s ($(steps))"
fi
step "cut Phase II"
cut_phase

# ------------------------------------------------------------------ 4. Phase III: alliance + Virtue share (row 35 part)
if wait_round 3; then
    hold_on 300
    sleep 25
    step "Phase III: ally_form"
    OUT3=$(PY $STEP_MAX diag/twin/regress_small.py ally_form games=$G actor=B)   # settle 75 + ally_test 180 + budget
    AF=$(echo "$OUT3" | grep "^RESULT ally_form " | tail -1)
    echo "$AF" | cut -c1-400
    if [ "$(echo "$AF" | awk '{print $3}')" = SETUP ]; then
        step "Phase III: pin_place markers (3-game variant: A+B allied, C rival)"
        OUT54=$(PY $STEP_MAX diag/twin/regress_small.py pin_place markers games=$G actor=B)
        P54=$(echo "$OUT54" | grep "^RESULT pin_place " | tail -1 | awk '{print $3}')
        M54=$(echo "$OUT54" | grep "^RESULT markers " | tail -1 | awk '{print $3}')
        V54="pin_place ${P54:-none}: $(echo "$OUT54" | grep "^RESULT pin_place " | tail -1 | cut -d: -f2- | cut -c1-250) || markers ${M54:-none}: $(echo "$OUT54" | grep "^RESULT markers " | tail -1 | cut -d: -f2- | cut -c1-250)"
        if [ "$P54" = FAIL ] || [ "$M54" = FAIL ]; then row 54p FAIL "$V54"
        elif [ "$P54" = PASS ] && [ "$M54" = PASS ]; then row 54p PASS "$V54"
        elif [ -z "$P54$M54" ]; then row 54p FAIL "pin_place + markers: no RESULT line: $(echo "$OUT54" | tail -2 | tr '\n' ' ' | cut -c1-200)"
        else row 54p SKIP "$V54"; fi
        hold_on 95 nohp                               # tagged holder replaces the 300 s one; nohp: C can die
        # hold_clock.py only RAISES the clock (writes 95 when it is under 65): after the 300 s holder the clock sat
        # at 270..300 and needed ~3 min to fall under ~100 s, longer than the 150 s wait. Set it to 95 once here.
        say "clock to 95: $(PY 60 diag/twin/clock.py 95 $G | tr '\n' ' ' | cut -c1-200)"
        sleep 5
        step "Phase III: alliance Virtue share"
        say "ritual before: $(PY 60 diag/twin/ritual.py $G | grep -E '^[ABC] step|10040' | tr '\n' ';' | cut -c1-400)"
        SITE=$(PY 400 diag/twin/run3_check.py site A C B $G wait=150)
        echo "$SITE" | grep -v '^SITE' | tail -3
        say "ritual after: $(PY 60 diag/twin/ritual.py $G | grep -E '^[ABC] step|10040' | tr '\n' ';' | cut -c1-400)"
        SL=$(echo "$SITE" | grep '^SITE ' | tail -1)
        if [ -n "$SL" ]; then
            row 35p "$(echo "$SL" | awk '{print $2}')" "site share: $(echo "$SL" | cut -d' ' -f3-)"
        else
            row 35p FAIL "site share: no SITE line (timeout or crash): $(echo "$SITE" | tail -2 | tr '\n' ' ' | cut -c1-200)"
        fi
    else
        row 35p SKIP "alliance not formed: ${AF:-no RESULT line}"
    fi
else
    row 35p SKIP "Phase III not reached on every game in $STEP_MAX s ($(steps))"
fi

# ------------------------------------------------------------------ 5. final: rows 18 + 19
step "to_final"
hold_off || finish 2 "a hold_clock could not be stopped: the final would never start"
say "to_final: $(PY 480 diag/twin/to_final.py 420 | tail -2 | tr '\n' ' ')"
if [ "$(steps)" = "$(want_round 4)" ]; then
    hold_on 200 nohp                                   # the final is only 240 s: spectate needs ~9 min; nohp: C must die
    step "final: alliance_end"
    OUT4=$(PY 300 diag/twin/regress_small.py alliance_end games=$G)
    rs_row 18 alliance_end "$OUT4"
    sleep 30
    step "final: spectate"
    # budget 1080: part 1 C killed twice (Outcome on C, others at step 6, listed once), part 2 B killed twice
    # (final ends, ranks A 1 / B 2 / C 3 equal everywhere; needs assist V402); spectate_notes.md 9
    OUT5=$(PY 1140 diag/twin/regress_small.py spectate games=$G)
    SP=$(echo "$OUT5" | grep "^RESULT spectate " | tail -1)
    say "lives: $(PY 90 diag/twin/lives.py $G | tr '\n' ';' | cut -c1-700)"
    say "final_kills: $(PY 90 diag/twin/final_kills.py $G | tr '\n' ';' | cut -c1-700)"
    FIN=$(PY 120 diag/twin/run4_check.py final $G | grep '^FINAL ' | tail -1)   # after part 2: result rows equal
    hold_off
    SPS=$(echo "$SP" | awk '{print $3}')
    FS=$(echo "$FIN" | awk '{print $2}')
    SPT=$(echo "$SP" | sed 's/^RESULT *[a-z_]* *[A-Z]* *//')
    if [ -z "$SP" ]; then
        row 19 FAIL "spectate: no RESULT line | ${FIN:-no FINAL line}"
    elif [ "$SPS" = PASS ] && [ "$FS" = PASS ]; then
        row 19 PASS "spectate + end of the final: $SPT || $FIN"
    elif [ "$SPS" = SKIP ] || [ "$SPS" = PARTIAL ]; then
        row 19 "$SPS" "spectate: $SPT || $FIN"
    else
        row 19 FAIL "spectate $SPS, checks ${FS:-none}: $SPT || $FIN"
    fi
else
    row 18 SKIP "alliance_end: the final (round 4) not reached on every game ($(steps))"
    row 19 SKIP "spectate: the final (round 4) not reached on every game ($(steps))"
fi

# ------------------------------------------------------------------ 6. the three dusk_lan logs
say "=== step: cutcheck (logs only: no health stop here, the match may be over)"
hc_stray
cutcheck_row cut

finish 0
