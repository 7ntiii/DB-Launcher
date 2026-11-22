#!/bin/bash
# runkr.sh: one 2-game match (A, B only) on the build with KIN4_* (kindeath4) and kinrecall_c BUILT IN: no live
# groups are applied. TEST RIG ONLY. Copy of runkd4.sh / runmix.sh.
# Order (round 2, kin circles exist from round 2): kin_summon B -> kin_recall B (kin12 edit: second direction, +0xC0 /
# +0xC8) -> kin_summon B again if the recall left the kin in (state 2) -> kin_death B (kd4 judge, merged into
# regress_small.py 2026-11-16; backup regress_small.pre_kr.py).
# Each step: a timeout and ONE "RESULT <step> ..." line in diag/twin/runkr.log. About 12 min after the hub (6 min).
cd <WORKSPACE>
LOG=diag/twin/runkr.log
say() { echo "[$(date +%T)] $*"; }
result() { echo "[$(date +%T)] RESULT $1 rc=$2 | $3" | cut -c1-700 | tee -a "$LOG"; }
stop_hc() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*hold_clock*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
cleanup_after() {   # a `timeout` kill skips the test's finally blocks: put the engine bits back
  [ "$2" = 124 ] || return 0
  for w in A B; do timeout 40 python diag/twin/nodeath.py $w off >/dev/null 2>&1; done
  for w in A B; do timeout 40 python diag/twin/mem.py $w w8 main+0x5B84548 0 >/dev/null 2>&1; done
  result cleanup_$1 0 "time-out: no-dead bit off on A / B, AllNoMove 0 on A / B"
}
trap 'stop_hc >/dev/null 2>&1' EXIT
echo "=== runkr $(date '+%F %T') ===" >> "$LOG"

# guards: the user's game / launcher, another rig run
other=$(timeout 60 python diag/twin/run3_check.py userrun 2>/dev/null | tr -d '\r')
[ -n "$other" ] && { result guard 2 "the user's game or launcher is running ($other): nothing started"; exit 2; }
rig=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='lichii.exe'\" | Where-Object { \$_.ExecutablePath -match 'DuskbloodsWorkspace.build.lichii.bin' }).Count" 2>/dev/null | tr -d '\r')
[ "${rig:-0}" = 0 ] || { result guard 2 "$rig rig lichii.exe running (another run?): nothing started"; exit 2; }
grep -q "kin12: the same press" diag/twin/regress_small.py || { result guard 2 "regress_small.py lacks the kin12 edit"; exit 2; }

# ---- hub
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
    out=$(timeout 200 python diag/twin/regress_small.py kin_summon actor=B 2>&1); rc=$?
    r=$(echo "$out" | grep "RESULT [a-z]" | tail -1 | cut -c1-300)
    echo "$r" | grep -q PASS && break
  done
  result $1 $rc "try $t: $r$( [ $rc = 124 ] && echo ' TIMEOUT 200 s')"
  cleanup_after $1 $rc
}

say "KIN summon"; summon kin_summon_B
say "KIN recall"
out=$(timeout 300 python diag/twin/regress_small.py kin_recall actor=B 2>&1); rc=$?
rr=$(echo "$out" | grep "RESULT [a-z]" | tail -1)
result kin_recall_B $rc "$(echo "$rr" | cut -c1-650)$( [ $rc = 124 ] && echo ' TIMEOUT 300 s')"
cleanup_after kin_recall_B $rc
echo "$rr" | grep -q PASS || { say "KIN summon again"; summon kin_summon2_B; }

say "KIN death (kd4 judge, built-in caves)"
out=$(timeout 560 python diag/twin/regress_small.py kin_death actor=B 2>&1); rc=$?
echo "$out" > diag/twin/kr_death_out.txt
result kin_death_B $rc "$(echo "$out" | grep "RESULT [a-z]" | tail -1 | cut -c1-600)$( [ $rc = 124 ] && echo ' TIMEOUT 560 s')"
cleanup_after kin_death_B $rc
echo "$out" | grep -E "ownership as the caves|kindeath4 cave" | cut -c1-300

stop_hc
bash diag/twin/alive.sh | tail -3
say "runkr done: see $LOG"
