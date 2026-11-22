#!/bin/bash
# runlove.sh: which gate hides "Accept flowers" (Love Ephemeral) on the loved one's game. diag/net/love3_notes.md
# sections 3-5. Written 2026-11-17 as static work; never run yet. TEST RIG ONLY, two games A B on this PC.
#
#   bash diag/twin/runlove.sh          (Git Bash, from anywhere; log diag/twin/runlove.log; RUN_KEEP=1 leaves the
#                                       rig running at the end)
# Flow: guard (user's game / launcher / another rig run -> nothing started) -> go_hub.sh with the rig defaults,
# --no-watch and TWIN_GDB_A=1 (gdbstub on A only, no QUIC watcher) -> pick_sigil.py B 600040 (Samir with the
# sigil; verified, by-hand fallback sequence once) -> to_match2b -> Phase I, clock held -> love_accept.py B A dry
# (quests 240 / 250, pairing) -> probes 1, 2, 3 on A, one offering window each, stop at the first conclusive one.
# Last line before the summary: "RESULT <gate> fix <n>: ...". Every breakpoint is removed by the probe itself
# (finally) and again by `runlove_check.py clearbp` after every probe and on every exit path.
# Exit 0 = a RESULT, 2 = stopped early.

G=AB
RUN_NAME=runlove
ROWS="start sigil match setup probe"
source <WORKSPACE>/diag/twin/run_lib.sh
RR[start]="SKIP go_hub start: not reached"
RR[sigil]="SKIP pick_sigil B 600040: not reached"
RR[match]="SKIP to_match2b + Phase I: not reached"
RR[setup]="SKIP love_accept dry: not reached"
RR[probe]="SKIP probes: not reached"
ALL_BP=19C9DD4,19C9DEC,19C9DA4,19C9DD0,19CA1B8,19CA2EC
BPSET=

lfinish() {   # every exit: breakpoints away first (only once the rig was started), then run_lib's finish
    trap - INT TERM
    if [ "$STARTED" = 1 ] && [ -n "$BPSET" ]; then
        PY 40 diag/twin/runlove_check.py clearbp "$ALL_BP"
        BPSET=
    fi
    finish "$@"
}
trap 'lfinish 2 "interrupted"' INT TERM

precheck
OTH=$(PY 60 diag/twin/runlove_check.py others | tr -d '\r')
[ -n "$OTH" ] && lfinish 2 "another rig run is active ($OTH): nothing started"

# ------------------------------------------------------------------ 1. cold start to the hub (A with gdbstub only)
STARTED=1
hold_off
GL=diag/twin/runlove_go.txt
DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 TWIN_GDB_A=1 \
    bash diag/twin/go_hub.sh > "$GL" 2>&1 &
GO_PID=$!
say "go_hub.sh started (pid $GO_PID, TWIN_GDB_A=1), output $GL"
# Run 1 (19:44): A stayed black 300 s: LICHII_GDBSTUB suspends the guest until a debugger continues
# (k_process.cpp). Release A as soon as its stub listens (connect, continue, close; as hp_watch.py does).
REL=$(PY 300 diag/twin/runlove_check.py release 280 | tr -d '\r')
say "$(echo "$REL" | tr '\n' ' ')"
echo "$REL" | grep -q 'A continued' || { row start FAIL "gdbstub release: $REL"; lfinish 2 "A never released"; }
wait_log "$GL" '^hub-ready' '^FAILED|Traceback' $STEP_MAX
RC=$?
# Both hub markers, generously: a game go_hub's to_hub2.py missed is driven once more alone (to_hub2b, 600 s).
HUBF=diag/twin/runlove_hub.txt
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

# ------------------------------------------------------------------ 5. probes, one offering window each
# probe_window N OFFS [FILTER]: love_accept.py B A presses=10 in the background; as soon as it shows the offering on
# A's copy, the filtered probe on A for 12 s; then wait for love_accept (max 150 s) and remove the breakpoints again.
probe_window() {
    local n=$1 offs=$2 flt=$3 LF=diag/twin/runlove_la$1.txt PF=diag/twin/runlove_p$1.txt t0 la
    step "probe $n ($offs${flt:+ $flt})"
    : > "$PF"
    timeout 200 python diag/twin/love_accept.py B A presses=10 > "$LF" 2>&1 &
    la=$!
    t0=$(date +%s)
    until grep -q 'copy on A: offering 1' "$LF" 2>/dev/null; do
        if ! kill -0 $la 2>/dev/null || [ $(( $(date +%s) - t0 )) -ge 90 ]; then
            say "probe $n: no offering on A's copy ($(grep -E '^RESULT|SETUP' "$LF" | tail -1 | cut -c1-160))"
            wait $la 2>/dev/null
            return 1
        fi
        sleep 0.5
    done
    BPSET=1
    # shellcheck disable=SC2086
    timeout -s INT 40 python diag/twin/runlove_check.py probe "$offs" 12 $flt > "$PF" 2>&1
    PY 40 diag/twin/runlove_check.py clearbp "$ALL_BP"
    BPSET=
    grep -E '^probe done|^bp ' "$PF" | sed 's/^/  /'
    wait $la 2>/dev/null
    say "probe $n love_accept: $(grep -E '^RESULT|^SETUP' "$LF" | tail -1 | cut -c1-200)"
    return 0
}
verdict() { PY 30 diag/twin/runlove_check.py judge "$@" | tr -d '\r'; }

probe_window 1 19C9DD4,19C9DEC || { row probe FAIL "probe 1: no offering window"; lfinish 2 "no offering"; }
V=$(verdict 1 diag/twin/runlove_p1.txt)
if [ "$V" = "NEXT 2" ]; then
    M=$(PY 60 diag/twin/runlove_check.py copym | tr -d '\r' | tail -1)
    say "bearer copy M on A: $M"
    if [ "$M" = none ] || [ -z "$M" ]; then
        V="RESULT undecided fix -: copy M unreadable"
    else
        probe_window 2 19C9DA4,19C9DD0 "x19=$M" || { row probe FAIL "probe 2: no offering window"; lfinish 2 "no offering"; }
        V=$(verdict 2 diag/twin/runlove_p2.txt "$M")
    fi
elif [ "$V" = "NEXT 3" ]; then
    probe_window 3 19CA1B8,19CA2EC "x21=186a0" || { row probe FAIL "probe 3: no offering window"; lfinish 2 "no offering"; }
    V=$(verdict 3 diag/twin/runlove_p3.txt)
fi
echo "$V"
case "$V" in
    "RESULT undecided"*) row probe FAIL "$V";;
    RESULT*)             row probe PASS "$V";;
    *)                   row probe FAIL "no verdict: $V";;
esac
lfinish 0
