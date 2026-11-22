#!/bin/bash
# runkd4.sh: one 2-game match for "a rival kills your kin" with kindeath4 (KIN4_HIT_CAVE, KIN4_AUTH, KIN4_SEND, KIN4_PRED;
# player-number fix, kin8_notes.md)
# applied in the hub. Phase I is cut short (kin circles exist from round 2). kin_summon (actor B) then kin_death v3
# (actor B = owner, A = rival) from regress_small_kd4.py (the copy with the ownership gate: no swing unless the
# owner reads "OURS (owner)"). TEST RIG ONLY. Copy of runkd.sh. Output: diag/twin/kd4_out.txt.
cd <WORKSPACE>
say() { echo "[$(date +%T)] $*"; }
stop_hc() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*hold_clock*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
(DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 nohup bash diag/twin/go_hub.sh > diag/twin/go.log 2>&1 &)
n=0; until grep -q "hub-ready" diag/twin/go.log || [ $n -ge 45 ]; do sleep 8; n=$((n+1)); done
say "hub: $(grep -c TIMEOUT diag/twin/go.log) timeouts"
for g in KIN4_HIT_CAVE KIN4_AUTH KIN4_SEND KIN4_PRED; do PATCH_FILE=diag/net/kindeath4_live.py python diag/twin/apply_groups.py AB $g 2>&1 | tail -1; done
DUSK_WAIT_LONGPOLL=3600 TO_MATCH_ONE_PRESS=1 timeout 300 python diag/twin/to_match2.py 2>&1 | tail -1
n=0; until timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -q "step 6 round 1" || [ $n -ge 25 ]; do sleep 8; n=$((n+1)); done; sleep 22
timeout 40 python diag/twin/clock.py 5 AB >/dev/null 2>&1
n=0; until timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round 2" || [ $n -ge 25 ]; do sleep 6; n=$((n+1)); done; sleep 22
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)
say "KIN summon"
for t in 1 2; do r=$(timeout 200 python diag/twin/regress_small_kd4.py kin_summon actor=B 2>&1 | grep "RESULT [a-z]" | cut -c1-140); echo "$r"; echo "$r" | grep -q PASS && break; done
say "KIN death v3 (kindeath4, gate)"
timeout 560 python diag/twin/regress_small_kd4.py kin_death actor=B 2>&1 | tee diag/twin/kd4_out.txt | grep -E "RESULT [a-z]|ownership as the caves|kindeath4 cave|still 3 s|attack t=|attack over|no connect" | cut -c1-600
stop_hc
bash diag/twin/alive.sh | tail -3
say "runkd4 done"
