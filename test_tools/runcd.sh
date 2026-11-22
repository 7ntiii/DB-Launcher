#!/bin/bash
# runcd.sh: one 2-game match for blood drain (Phase I) and blood crystals host + guest (Phase II, Gala). TEST RIG ONLY.
cd <WORKSPACE>
say() { echo "[$(date +%T)] $*"; }
stop_hc() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*hold_clock*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
(DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 nohup bash diag/twin/go_hub.sh > diag/twin/go.log 2>&1 &)
n=0; until grep -q "hub-ready" diag/twin/go.log || [ $n -ge 45 ]; do sleep 8; n=$((n+1)); done
say "hub: $(grep -c TIMEOUT diag/twin/go.log) timeouts"
for g in CRYSTAL_GUEST_CAVE CRYSTAL_GUEST; do PATCH_FILE=diag/net/crystal_live.py python diag/twin/apply_groups.py AB $g 2>&1 | tail -1; done
DUSK_WAIT_LONGPOLL=3600 TO_MATCH_ONE_PRESS=1 timeout 300 python diag/twin/to_match2.py 2>&1 | tail -1
n=0; until timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -q "step 6 round 1" || [ $n -ge 25 ]; do sleep 8; n=$((n+1)); done; sleep 22
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)
say "DRAIN A"; timeout 400 python diag/twin/drain_test.py A 2>&1 | tail -6
bash diag/twin/alive.sh | tail -3
(nohup python diag/twin/force_event.py A 1220 arm B > diag/twin/fe.txt 2>&1 &); sleep 8
stop_hc; timeout 40 python diag/twin/clock.py 5 AB >/dev/null 2>&1
n=0; until timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round 2" || [ $n -ge 25 ]; do sleep 6; n=$((n+1)); done; sleep 22
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)
say "event: $(tail -1 diag/twin/fe.txt)"
say "CRYSTAL A"; timeout 520 python diag/twin/crystal_test.py A 2>&1 | tail -8
bash diag/twin/alive.sh | tail -3
say "CRYSTAL B"; timeout 520 python diag/twin/crystal_test.py B 2>&1 | tail -8
bash diag/twin/alive.sh | tail -3
say "KIN control"
for t in 1 2; do r=$(timeout 200 python diag/twin/regress_small.py kin_summon actor=B 2>&1 | grep "RESULT [a-z]" | cut -c1-140); echo "$r"; echo "$r" | grep -q PASS && break; done
timeout 420 python diag/twin/regress_small.py kin_death actor=B 2>&1 | grep "RESULT [a-z]" | cut -c1-900
bash diag/twin/alive.sh | tail -3
say "runcd done"
