#!/bin/bash
# runkr2.sh: one 2-game match (A, B only) on v3.9.6 (KIN4_* and kinrecall_c BUILT IN: no live groups) for the three kin
# cases UPDATE 14 left unproven, all with the HOST (A) as the kin's owner and B as the rival. TEST RIG ONLY. Copy of
# runkr.sh. Not run yet.
#   (c) kin_recall actor=A: Y + Down dismisses the host's kin (3 -> 4 -> 2) and summons it again (2 -> 3), every game.
#   (a) kin_death actor=A: the GUEST B kills the HOST's kin (real hits); PASS / PARTIAL / FAIL as in regress_small.py.
#   (b) the same kin_death run with KD_RESUMMON_INPUT=1: after the death the kin is summoned back with the owner's REAL
#       input (hold Y + D-pad, summon_out_input, the path kin_summon / kin_recall use) instead of the step+0xC8 write,
#       a round every 5 s up to 150 s; "RESUMMON-INPUT PASS" only when state 3 on every game, and the line gives how
#       long after the owner's state 2 the kin came out (the game's wait for a kin that died).
# Order: kin_summon A -> kin_recall A (c) -> kin_summon A again if the recall left no kin out -> kin_death A (a + b).
# Each case: a timeout and ONE "RESULT <case> ..." line in diag/twin/runkr2.log. About 6 min hub + 12-15 min.
cd <WORKSPACE>
LOG=diag/twin/runkr2.log
say() { echo "[$(date +%T)] $*"; }
result() { echo "[$(date +%T)] RESULT $1 rc=$2 | $3" | cut -c1-700 | tee -a "$LOG"; }
stop_hc() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*hold_clock*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
cleanup_after() {   # a `timeout` kill skips the test's finally blocks: put the engine bits back
  [ "$2" = 124 ] || return 0
  for w in A B; do timeout 40 python diag/twin/nodeath.py $w off >/dev/null 2>&1; done
  for w in A B; do timeout 40 python diag/twin/mem.py $w w8 main+0x5B84548 0 >/dev/null 2>&1; done
  result cleanup_$1 0 "time-out: no-dead bit off on A / B, AllNoMove 0 on A / B"
}
STARTED=0
final_cleanup() {   # review (helper 4): every exit after the guards, not only a `timeout` kill (idempotent)
  stop_hc >/dev/null 2>&1
  [ "$STARTED" = 1 ] || return 0
  for w in A B; do timeout 40 python diag/twin/nodeath.py $w off >/dev/null 2>&1; done
  for w in A B; do timeout 40 python diag/twin/mem.py $w w8 main+0x5B84548 0 >/dev/null 2>&1; done
}
trap final_cleanup EXIT
trap 'exit 130' INT TERM
echo "=== runkr2 $(date '+%F %T') ===" >> "$LOG"

# guards: the user's game / launcher, another rig run
other=$(timeout 60 python diag/twin/run3_check.py userrun 2>/dev/null | tr -d '\r')
[ -n "$other" ] && { result guard 2 "the user's game or launcher is running ($other): nothing started"; exit 2; }
rig=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='lichii.exe'\" | Where-Object { \$_.ExecutablePath -match 'DuskbloodsWorkspace.build.lichii.bin' }).Count" 2>/dev/null | tr -d '\r')
[ "${rig:-0}" = 0 ] || { result guard 2 "$rig rig lichii.exe running (another run?): nothing started"; exit 2; }
grep -q "def kd_prepare" diag/twin/regress_small.py || { result guard 2 "regress_small.py lacks the rival-safety fix (kd_prepare)"; exit 2; }
grep -q "KD_RESUMMON_INPUT" diag/twin/regress_small.py || { result guard 2 "regress_small.py lacks the runkr2 re-summon edit"; exit 2; }
grep -q "kin12: the same press" diag/twin/regress_small.py || { result guard 2 "regress_small.py lacks the kin12 edit"; exit 2; }

# ---- hub (two games only)
export TWIN_GAMES=AB
STARTED=1
rm -f diag/twin/go.log                    # review: a stale "hub-ready" from the last run would pass the wait at once
(DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 nohup bash diag/twin/go_hub.sh > diag/twin/go.log 2>&1 &)
n=0; until grep -q "hub-ready" diag/twin/go.log || [ $n -ge 45 ]; do sleep 8; n=$((n+1)); done
say "hub: $(grep -c TIMEOUT diag/twin/go.log) timeouts"
grep -q "hub-ready" diag/twin/go.log || { result hub 1 "hub not ready after 6 min: stopped (see go.log)"; bash diag/twin/alive.sh | tail -3; exit 1; }

# ---- built-in check (read only): KAUTH4 first word (kindeath4) and the kinrecall_c owner-test word (differs from b)
bad=""
for w in A B; do
  k4=$(timeout 40 python diag/twin/mem.py $w r main+0xC502CD0 4 2>/dev/null | tr -d '\r')
  kc=$(timeout 40 python diag/twin/mem.py $w r main+0xC502BD4 4 2>/dev/null | tr -d '\r')
  echo "$k4" | grep -q "10 b3 fc f0" || bad="$bad $w:KAUTH4($k4)"
  echo "$kc" | grep -q "10 12 40 f9" || bad="$bad $w:kinrecall_c($kc)"
done
if [ -n "$bad" ]; then
  result build_check 1 "not built in:$bad: stopped (this run applies no live groups)"
  bash diag/twin/alive.sh | tail -3; exit 1
fi
result build_check 0 "KIN4 and kinrecall_c words present on A and B"

# ---- match, cut Phase I (kin circles from round 2)
DUSK_WAIT_LONGPOLL=3600 TO_MATCH_ONE_PRESS=1 timeout 300 python diag/twin/to_match2.py 2>&1 | tail -1
n=0; until timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -q "step 6 round 1" || [ $n -ge 25 ]; do sleep 8; n=$((n+1)); done; sleep 22
timeout 40 python diag/twin/clock.py 5 AB >/dev/null 2>&1
n=0; until timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round 2" || [ $n -ge 25 ]; do sleep 6; n=$((n+1)); done; sleep 22
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)

summon() {   # summon TAG
  for t in 1 2; do
    out=$(timeout 200 python diag/twin/regress_small.py kin_summon actor=A 2>&1); rc=$?
    r=$(echo "$out" | grep "RESULT [a-z]" | tail -1 | cut -c1-300)
    echo "$r" | grep -q PASS && break
  done
  result $1 $rc "try $t: $r$( [ $rc = 124 ] && echo ' TIMEOUT 200 s')"
  cleanup_after $1 $rc
}

say "KIN summon (host A)"; summon kin_summon_A
if [ "${KR2_SKIP_RECALL:-0}" = 1 ]; then   # (c) passed at 15:15 (runkr2.log): KR2_SKIP_RECALL=1 runs only (a) + (b)
  say "KIN recall (c) skipped (KR2_SKIP_RECALL=1; PASS 2026-11-16 15:15)"
else
say "KIN recall (c): host A owner"
out=$(timeout 300 python diag/twin/regress_small.py kin_recall actor=A 2>&1); rc=$?
rr=$(echo "$out" | grep "RESULT [a-z]" | tail -1)
result c_kin_recall_hostA $rc "$(echo "$rr" | cut -c1-650)$( [ $rc = 124 ] && echo ' TIMEOUT 300 s')"
cleanup_after c_kin_recall_hostA $rc
echo "$rr" | grep -q PASS || { say "KIN summon again"; summon kin_summon2_A; }
fi

say "KIN death (a) host A owner, guest B rival; (b) re-summon by real input"
out=$(KD_CONTROL=0 KD_RESUMMON_INPUT=1 timeout 900 python diag/twin/regress_small.py kin_death actor=A budget=1.6 2>&1); rc=$?
echo "$out" > diag/twin/kr2_death_out.txt
rl=$(echo "$out" | grep "RESULT [a-z]" | tail -1)
result a_kin_death_hostA $rc "$(echo "$rl" | sed 's/RESUMMON-INPUT [^|]*| //' | cut -c1-600)$( [ $rc = 124 ] && echo ' TIMEOUT 900 s')"
rs=$(echo "$rl" | grep -o "RESUMMON-INPUT [^|]*")
result b_resummon_input_hostA $rc "${rs:-RESUMMON-INPUT NOT JUDGED: no line (kin_death ended before the re-summon: $(echo "$rl" | cut -c1-200))}"
cleanup_after kin_death_hostA $rc
echo "$out" | grep -E "ownership as the caves|kindeath4 cave" | cut -c1-300

stop_hc
bash diag/twin/alive.sh | tail -3
say "runkr2 done: see $LOG"
