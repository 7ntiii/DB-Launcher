#!/bin/bash
# runmix.sh: one 2-game match that judges as many open items as possible. TEST RIG ONLY. Built from runkd.sh / runcd.sh.
# Groups are applied in the hub only:
#   KINRECALL_CAVE, KINRECALL_HOOK (kinrecall_b_live.py)
#   CRYSTAL_GUEST_CAVE, CRYSTAL_GUEST (crystal_live.py)
# Order (easiest first, within what each phase allows):
#   round 1 (Phase I):  drain_test v3 A; then arm the Bloodsac Gala (force_event 1220) and cut Phase I.
#   round 2 (Phase II): kin_summon B; kin_recall B (kin7 fix, applied first if missing); crystal_test A; crystal_test B.
#   kin circles exist only from round 2 (runkd.sh), and the Gala must be armed in Phase I (crystal_test.py header),
#   so drain runs before kin.
# Each step: a timeout and ONE "RESULT <step> ..." line in diag/twin/runmix.log. A failed / NOT JUDGED / timed-out
# step never stops the next one.
# Expected time: hub about 6 min, match start up to 5, round 1 wait about 3, drain up to 7, round 2 wait about 3,
# kin_summon up to 7 (2 tries), kin_recall up to 5, crystal A and B up to 9 each.
# About 40 min typical, 55 min worst case.
cd <WORKSPACE>
LOG=diag/twin/runmix.log
say() { echo "[$(date +%T)] $*"; }
result() { echo "[$(date +%T)] RESULT $1 rc=$2 | $3" | cut -c1-700 | tee -a "$LOG"; }
stop_hc() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*hold_clock*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
echo "=== runmix $(date '+%F %T') ===" >> "$LOG"

# runmix_review (2026-11-16): nothing starts while the user's own game / launcher runs or another rig run (run4.sh)
# owns lichii.exe of build/lichii/bin: go_hub.sh would close those games.
other=$(timeout 60 python diag/twin/run3_check.py userrun 2>/dev/null | tr -d '\r')
[ -n "$other" ] && { result guard 2 "the user's game or launcher is running ($other): nothing started"; exit 2; }
rig=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='lichii.exe'\" | Where-Object { \$_.ExecutablePath -match 'DuskbloodsWorkspace.build.lichii.bin' }).Count" 2>/dev/null | tr -d '\r')
[ "${rig:-0}" = 0 ] || { result guard 2 "$rig rig lichii.exe running (another run?): nothing started"; exit 2; }
# A `timeout` kill ends a Windows python at once: its finally blocks (no-dead bit, AllNoMove, AI hold) never run.
# After a step that timed out, put the engine bits back to stock (AllNoMove 0 = off; no-dead bit off on each player).
cleanup_after() {   # cleanup_after STEP RC
  [ "$2" = 124 ] || return 0
  for w in A B; do timeout 40 python diag/twin/nodeath.py $w off >/dev/null 2>&1; done
  for w in A B; do timeout 40 python diag/twin/mem.py $w w8 main+0x5B84548 0 >/dev/null 2>&1; done
  result cleanup_$1 0 "time-out: no-dead bit off on A / B, AllNoMove 0 on A / B (an AI-hold bit on the picked sac may stay: that sac only)"
}

# ---- kin7 fix (regress_small.py must not be running here; this script is the only user)
if grep -q "kin7 (2026-11-17)" diag/twin/regress_small.py; then
  result kin7_apply 0 "already applied"
else
  out=$(python diag/twin/kin7_apply.py 2>&1 | tail -1)
  # runmix_review: kin7_apply.py stops on a failed assert WITHOUT writing, and the old file still compiles: so
  # "applied" needs its marker too
  if grep -q "kin7 (2026-11-17)" diag/twin/regress_small.py && python -m py_compile diag/twin/regress_small.py 2>/dev/null; then
    result kin7_apply 0 "applied: $out (backup diag/twin/regress_small.pre_kin7.py)"
  else
    cp diag/twin/regress_small.pre_kin7.py diag/twin/regress_small.py 2>/dev/null
    result kin7_apply 1 "not applied (assert or compile failed), backup restored: kin_recall runs without the fix ($out)"
  fi
fi

# ---- hub
(DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 nohup bash diag/twin/go_hub.sh > diag/twin/go.log 2>&1 &)
n=0; until grep -q "hub-ready" diag/twin/go.log || [ $n -ge 45 ]; do sleep 8; n=$((n+1)); done
say "hub: $(grep -c TIMEOUT diag/twin/go.log) timeouts"
for g in KINRECALL_CAVE KINRECALL_HOOK; do PATCH_FILE=diag/net/kinrecall_b_live.py python diag/twin/apply_groups.py AB $g 2>&1 | tail -1; done
for g in CRYSTAL_GUEST_CAVE CRYSTAL_GUEST; do PATCH_FILE=diag/net/crystal_live.py python diag/twin/apply_groups.py AB $g 2>&1 | tail -1; done
DUSK_WAIT_LONGPOLL=3600 TO_MATCH_ONE_PRESS=1 timeout 300 python diag/twin/to_match2.py 2>&1 | tail -1
n=0; until timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -q "step 6 round 1" || [ $n -ge 25 ]; do sleep 8; n=$((n+1)); done; sleep 22
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)

# ---- round 1: drain
say "DRAIN A"
out=$(timeout 400 python diag/twin/drain_test.py A 2>&1); rc=$?
result drain_A $rc "$(echo "$out" | grep "^DRAIN_TEST " | tail -1)$( [ $rc = 124 ] && echo ' TIMEOUT 400 s')"
cleanup_after drain_A $rc
echo "$out" | grep -E "ATTACK CHOSEN|no input lowered" | head -2
bash diag/twin/alive.sh | tail -3

# ---- arm the Gala, cut Phase I
(nohup python diag/twin/force_event.py A 1220 arm B > diag/twin/fe.txt 2>&1 &); sleep 8
stop_hc; timeout 40 python diag/twin/clock.py 5 AB >/dev/null 2>&1
n=0; until timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round 2" || [ $n -ge 25 ]; do sleep 6; n=$((n+1)); done; sleep 22
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)
say "event: $(tail -1 diag/twin/fe.txt)"

# ---- round 2: kin
say "KIN summon"
for t in 1 2; do
  out=$(timeout 200 python diag/twin/regress_small.py kin_summon actor=B 2>&1); rc=$?
  r=$(echo "$out" | grep "RESULT [a-z]" | tail -1 | cut -c1-300)
  echo "$r" | grep -q PASS && break
done
result kin_summon_B $rc "try $t: $r$( [ $rc = 124 ] && echo ' TIMEOUT 200 s')"
say "KIN recall"
out=$(timeout 300 python diag/twin/regress_small.py kin_recall actor=B 2>&1); rc=$?
result kin_recall_B $rc "$(echo "$out" | grep "RESULT [a-z]" | tail -1 | cut -c1-600)$( [ $rc = 124 ] && echo ' TIMEOUT 300 s')"
cleanup_after kin_recall_B $rc
echo "$out" | grep -E "TEST ONLY owner|no-dead bit (off|NOT)" | head -2
bash diag/twin/alive.sh | tail -3

# ---- round 2: crystals (Gala)
for w in A B; do
  say "CRYSTAL $w"
  # runmix_review: crystal_test's own limits are a 150 s phase wait + the 8-minute cap + the after-kill reads
  # (offers 15 s, rewards.py up to 90 s each): 520 s could kill it in the fight. 900 s lets its own exit run.
  out=$(timeout 900 python diag/twin/crystal_test.py $w 2>&1); rc=$?
  result crystal_$w $rc "$(echo "$out" | grep "VERDICT" | tail -1)$( [ $rc = 124 ] && echo ' TIMEOUT 900 s')"
  cleanup_after crystal_$w $rc
  echo "$out" | grep -E "current env event|AI hold.*(NOT cleared|STILL)" | head -3
  bash diag/twin/alive.sh | tail -3
done

stop_hc
bash diag/twin/alive.sh | tail -3
say "runmix done: $(grep -c "RESULT" "$LOG") RESULT lines in $LOG (all runs)"
