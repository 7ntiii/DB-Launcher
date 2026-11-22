#!/bin/bash
# runitem.sh: one 2-game match (A, B only) on the current build, nothing patched live, for row 53-other (Memorial
# Stake and other quick items, 0.5). TEST RIG ONLY. Written 2026-11-16 (helper 3). Not run yet.
# Hub as the passing runs (go_hub.sh with the four rig start settings; no groups). Phase I, clock held:
#   item_loop.py A B: every quick item of A once (Down; Right between items), then item_loop.py B A the same for B.
#   Per item ONE line "RESULT <A_|B_>item_<goods id> PASS|FAIL|NOT JUDGED":
#     PASS = count -1 on the user's game AND the effect on BOTH games: the same new effect row on the user's chr
#            on its own game and on the other game's copy, or HP up >= 10 on both (the user's HP is lowered to 60 %
#            before each use, TEST ONLY, and topped up at the end);
#     FAIL = the effect on one game only; NOT JUDGED = used, no readable effect (human card), or no use.
# Which items: whatever sits in the quick slots at the start of Phase I (the inventory is printed first); items
# whose effect is a placed object (Memorial Stake) or a throw need a reader this tool does not have: NOT JUDGED.
# Expected time: hub about 6 min, to Phase I about 2 min, each user at most 8 steps of about 15 s (2 min each):
# about 12-13 min in all (timeouts: 240 s per user).
cd <WORKSPACE>
LOG=diag/twin/runitem.log
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
echo "=== runitem $(date '+%F %T') ===" >> "$LOG"

# guards: the user's game / launcher, another rig run
other=$(timeout 60 python diag/twin/run3_check.py userrun 2>/dev/null | tr -d '\r')
[ -n "$other" ] && { result guard 2 "the user's game or launcher is running ($other): nothing started"; exit 2; }
rig=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='lichii.exe'\" | Where-Object { \$_.ExecutablePath -match 'DuskbloodsWorkspace.build.lichii.bin' }).Count" 2>/dev/null | tr -d '\r')
[ "${rig:-0}" = 0 ] || { result guard 2 "$rig rig lichii.exe running (another run?): nothing started"; exit 2; }

[ -f diag/twin/item_loop.py ] && [ -f diag/twin/use_item.py ] || { result guard 2 "item_loop.py / use_item.py missing"; exit 2; }

# ---- hub (two games only)
export TWIN_GAMES=AB
STARTED=1
rm -f diag/twin/go.log                    # review: a stale "hub-ready" from the last run would pass the wait at once
(DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 nohup bash diag/twin/go_hub.sh > diag/twin/go.log 2>&1 &)
n=0; until grep -q "hub-ready" diag/twin/go.log || [ $n -ge 45 ]; do sleep 8; n=$((n+1)); done
say "hub: $(grep -c TIMEOUT diag/twin/go.log) timeouts"
grep -q "hub-ready" diag/twin/go.log || { result hub 1 "hub not ready after 6 min: stopped (see go.log)"; bash diag/twin/alive.sh | tail -3; exit 1; }

# ---- match, Phase I (items are used there; the clock is held so the phase does not end)
DUSK_WAIT_LONGPOLL=3600 TO_MATCH_ONE_PRESS=1 timeout 300 python diag/twin/to_match2.py 2>&1 | tail -1
n=0; until timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -q "step 6 round 1" || [ $n -ge 25 ]; do sleep 8; n=$((n+1)); done
timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -q "step 6 round 1" || { result match 1 "not in Phase I after 3.5 min: stopped"; exit 1; }
sleep 22
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)

for pair in "A B" "B A"; do
  set -- $pair
  say "ITEMS of $1 (effects read on $1 and $2)"
  out=$(timeout 420 python diag/twin/item_loop.py $1 $2 steps 8 collect 6 tag ${1}_ 2>&1); rc=$?
  echo "$out" > diag/twin/runitem_$1.txt
  echo "$out" | grep -E "inventory:|gained:|HP baseline: .*criterion" | cut -c1-300 | tee -a "$LOG"
  echo "$out" | grep "^RESULT " | while IFS= read -r l; do
    nm=$(echo "$l" | awk '{print $2}'); rest=$(echo "$l" | cut -d' ' -f3-)
    result "$nm" $rc "$rest"
  done
  echo "$out" | grep -q "^RESULT " || result items_$1 $rc "no RESULT line$( [ $rc = 124 ] && echo ': TIMEOUT 420 s') (see diag/twin/runitem_$1.txt): $(echo "$out" | tail -2 | tr '\n' ' ' | cut -c1-300)"
done

stop_hc
bash diag/twin/alive.sh | tail -3
say "runitem done: see $LOG"
