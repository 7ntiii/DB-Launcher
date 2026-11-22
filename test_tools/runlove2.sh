#!/bin/bash
# runlove2.sh: which gate hides "Accept flowers" (Love Ephemeral) on the loved one's game, WITHOUT a debugger
# (runlove.sh's gdbstub kept game A suspended twice; breakpoints dropped). diag/net/love3_notes.md section 6.
# Written 2026-11-17 as static work; never run yet. TEST RIG ONLY, two games A B on this PC.
#
#   bash diag/twin/runlove2.sh         (Git Bash, from anywhere; log diag/twin/runlove2.log; RUN_KEEP=1 leaves the
#                                       rig running at the end)
# Flow: guard (user's game / launcher / another rig run -> nothing started) -> plain go_hub.sh (rig defaults,
# --no-watch, no gdbstub) -> both hub markers (a missing game driven once more, 600 s) -> pick_sigil.py B 600040
# (verified; by-hand sequence once) -> to_match2b -> Phase I, clock held -> love_accept.py B A dry -> love_poll.py
# B A (place A, emote on B, poll A at ~10 Hz for 30 s; a second try from the back spot if no offering was seen).
# Last line before the summary: "RESULT <gate> fix <n>: ...".
# Exit 0 = a RESULT, 2 = stopped early.

G=AB
RUN_NAME=runlove2
ROWS="start sigil match setup probe"
source <WORKSPACE>/diag/twin/run_lib.sh
RR[start]="SKIP go_hub start: not reached"
RR[sigil]="SKIP pick_sigil B 600040: not reached"
RR[match]="SKIP to_match2b + Phase I: not reached"
RR[setup]="SKIP love_accept dry: not reached"
RR[probe]="SKIP love_poll: not reached"
trap 'finish 2 "interrupted"' INT TERM
HEALTH_POLL=0          # hub / loading: liveness = emulator log still advancing (audio lines every 2 s)
lfinish() { finish "$@"; }

precheck
OTH=$(PY 60 diag/twin/runlove_check.py others | tr -d '\r')
[ -n "$OTH" ] && lfinish 2 "another rig run is active ($OTH): nothing started"

# ------------------------------------------------------------------ 1. cold start to the hub (plain, no gdbstub)
STARTED=1
hold_off
GL=diag/twin/runlove2_go.txt
DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 \
    bash diag/twin/go_hub.sh > "$GL" 2>&1 &
GO_PID=$!
say "go_hub.sh started (pid $GO_PID, no gdbstub), output $GL"
wait_log "$GL" '^hub-ready' '^FAILED|Traceback' $STEP_MAX
RC=$?
# Both hub markers, generously: a game go_hub's to_hub2.py missed is driven once more alone (to_hub2b, 600 s).
HUBF=diag/twin/runlove2_hub.txt
grep ' hub in ' "$GL" > "$HUBF"
for w in A B; do
    grep -q "^$w hub in" "$HUBF" && continue
    say "game $w is NOT in the hub after go_hub ($(grep "^$w " "$GL" | tail -1)): driving it once more (600 s)"
    TWIN_GAMES=$w TO_HUB_SECS=600 PY 1300 diag/twin/to_hub2b.py | tee -a "$HUBF" | tail -3
done
MISS=$(for w in A B; do grep -q "^$w hub in" "$HUBF" || echo -n "$w "; done)
if [ -z "$MISS" ]; then
    row start PASS "go_hub rc $RC: both games in the hub ($(tr '\n' ' ' < "$HUBF" | cut -c1-120))"
else
    row start FAIL "game(s) missing from the hub: $MISS($(for w in $MISS; do grep "^$w " "$GL" "$HUBF" | tail -1; done | tr '\n' ' ' | cut -c1-200))"
    lfinish 2 "not both games in the hub (missing: $MISS)"
fi

# ------------------------------------------------------------------ 2. B: Samir with the sigil
step "hub: pick_sigil B 600040"
sigil_ok() { PY 60 diag/twin/pick_bloodsworn.py B show | grep -q 'pgd+0xEC8 applied row = 600040'; }
OUTH=$(PY 300 diag/twin/pick_sigil.py B 600040)
echo "$OUTH" | tail -3
if sigil_ok; then
    row sigil PASS "pick_sigil: applied row 600040"
else
    say "pick_sigil did not apply 600040: by-hand sequence once"
    PY 120 diag/twin/runlove_check.py fallback
    if sigil_ok; then row sigil PASS "fallback sequence: applied row 600040"
    else row sigil FAIL "B's applied row is not 600040: $(PY 60 diag/twin/pick_bloodsworn.py B show | grep 'applied row' | cut -c1-120)"
         lfinish 2 "no sigil on B"
    fi
fi

# ------------------------------------------------------------------ 3. match, Phase I
step "to_match2b"
OUTM=$(TWIN_GAMES=$G PY $STEP_MAX diag/twin/to_match2b.py)
RCM=$?
echo "$OUTM" | tail -3
[ $RCM = 0 ] || { row match FAIL "to_match2b rc $RCM"; lfinish 2 "not every game joined"; }
wait_round 1 || { row match FAIL "Phase I not on every game"; lfinish 2 "Phase I not reached"; }
row match PASS "both games in Phase I"
HEALTH_POLL=1          # inside the match: the NIFM poll-age test is valid again
hold_on 300
sleep 25                                              # no teleport in the first ~20 s of a phase

# ------------------------------------------------------------------ 4. setup check (no write, no input)
step "love_accept dry"
OUTD=$(PY 120 diag/twin/love_accept.py B A dry)
echo "$OUTD" | grep -E 'bearer|logics|SETUP' | head -4
if echo "$OUTD" | grep -q 'SETUP FAIL'; then
    row setup FAIL "$(echo "$OUTD" | grep 'SETUP FAIL' | tail -1 | cut -c1-300)"
    lfinish 2 "quests / pairing not ready"
fi
row setup PASS "240 on B, 250 on A, paired"

# ------------------------------------------------------------------ 5. polling (no debugger, no presses)
step "love_poll B A"
PF=diag/twin/runlove2_poll.txt
PY 240 diag/twin/love_poll.py B A secs=30 hz=10 > "$PF"
V=$(grep '^RESULT' "$PF" | tail -1 | tr -d '\r')
if [ -z "$V" ] || echo "$V" | grep -q 'no offering seen'; then
    say "first poll: ${V:-no RESULT line}; again from the back spot"
    sleep 5
    PY 240 diag/twin/love_poll.py B A secs=30 hz=10 side=back >> "$PF"
    V=$(grep '^RESULT' "$PF" | tail -1 | tr -d '\r')
fi
sed -n '/^samples/,/^RESULT/p' "$PF" | tail -12
echo "$V"
case "$V" in
    "RESULT undecided"*) row probe FAIL "$V";;
    RESULT*)             row probe PASS "$V";;
    *)                   row probe FAIL "no RESULT line (timeout or crash): $(tail -2 "$PF" | tr '\n' ' ' | cut -c1-200)";;
esac
lfinish 0
