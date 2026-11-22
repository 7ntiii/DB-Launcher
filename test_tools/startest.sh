#!/bin/bash
# Star Fragment event run: fresh match, force 1210 for Phase II, wait for both crashes, report whether both games live.
cd <WORKSPACE>
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'hold_clock|force_event' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 bash diag/twin/go.sh > diag/twin/go.log 2>&1 &
until grep -q "nav done" diag/twin/go.log; do sleep 10; done
until timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round 1"; do sleep 8; done; sleep 25
for w in A B; do timeout 30 python diag/twin/nodeath.py $w on >/dev/null 2>&1; done
(nohup python diag/twin/force_event.py A 1210 arm B > diag/twin/fe.txt 2>&1 &); sleep 8
timeout 40 python diag/twin/clock.py 5 AB >/dev/null 2>&1
until timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round 2"; do sleep 6; done; sleep 20
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)
n=0; until timeout 40 python diag/twin/starfrag.py A 2>/dev/null | head -1 | grep -q "crash1 [1-9].*crash2 [1-9]" || [ $n -ge 40 ]; do sleep 10; n=$((n+1)); done; sleep 25
timeout 60 python diag/twin/starfrag.py A 2>&1 | head -1 | cut -c1-150
timeout 60 python diag/twin/treasures.py AB 2>&1 | grep "world items" | cut -c1-130
for w in A B; do timeout 30 python diag/twin/mapsys.py $w 2>&1 | tail -1 | cut -c1-60; done
grep -c "PANIC" diag/twin/userB/log/eden_log.txt; grep -c "PANIC" "$APPDATA/eden/log/eden_log.txt" 2>/dev/null
echo "startest done"
