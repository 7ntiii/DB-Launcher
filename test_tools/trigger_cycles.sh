#!/bin/bash
# TEST ONLY (trigger proof, 2026-11-20): one two-game rig final per AREA argument; B (player 2) is made to play round 3
# in that area (pick_area.py on host A), GYBOX on B is sampled in round 4 (gy_watch.py). Logs: diag/net/trigger_V/fC_aAREA.
#   bash diag/twin/trigger_cycles.sh alpha6 0 3 0 3 ...
#   bash diag/twin/loadrel_cycles.sh 3.9.20 5 force     v3.9.20: force_slots.py gives B its own area
#   bash diag/twin/loadrel_cycles.sh alpha4 5           alpha 4: FINALSLOTS2 does it itself
# Per final: fresh rig, 2-player match, ff to the final, 45 s into the final read LRBOX, the list, crashes.
# Result lines: diag/twin/loadrel_cycles.log. Stops the rig at the end.
cd <WORKSPACE> || exit 2
V=$1; shift; AREAS="$@"; FORCE=
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v$V.zip" PKGTEST_PASSWORD=1 TO_MATCH_ONE_PRESS=1
R="python diag/twin/pkgtest.py run"
P=diag/twin/pkgtest/Duskbloods-Lichii-Online
OUT=diag/twin/trigger_cycles.log
stopper() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match '$1' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
c=0
for AR in $AREAS; do
    c=$((c+1)); M=3$c; export M
    echo "$(date +%T) v$V final $c (B round 3 area $AR): start" >> $OUT
    timeout 900 bash diag/twin/run_night.sh start "$V" > /dev/null 2>&1
    stopper start3
    nohup $R diag/twin/start3.py 2 > diag/twin/night_start3_m$M.log 2>&1 &
    sleep 3
    timeout 300 $R diag/twin/to_match2b.py > /dev/null 2>&1
    nohup $R diag/twin/watch_match.py 3600 AB --every 5 > diag/twin/night_watch_m$M.log 2>&1 &
    ok=0; for i in $(seq 1 90); do grep -E "^A:" diag/twin/night_watch_m$M.log 2>/dev/null | tail -n 1 | grep -q "step 6 round 1" && { ok=1; break; }; sleep 4; done
    [ $ok = 1 ] || { echo "$(date +%T) v$V final $c: no round 1, skipped" >> $OUT; continue; }
    nohup $R diag/twin/pick_area.py A 2 $AR 3 900 > diag/twin/night_pick_m$M.log 2>&1 &
    nohup $R diag/twin/gy_watch.py B 900 > diag/twin/night_gy_m$M.log 2>&1 &
    timeout 600 bash diag/twin/run_night.sh ff > /dev/null 2>&1 &
    FF=$!
    if [ "$FORCE" = force ]; then
        until grep -E "^A:" diag/twin/night_watch_m$M.log | tail -n 1 | grep -q "round 3"; do sleep 2; done
        sleep 20   # round 3's own intermission list is decided by now
        $R diag/twin/force_slots.py A 300 > diag/twin/force_slots_m$M.log 2>&1 &
    fi
    wait $FF
    sleep 45
    lr=$($R diag/twin/lrbox_read.py 2>&1 | grep LRBOX | awk '{print $1"="$4}' | tr '\n' ' ')
    lst=$(grep -a "list decided" $P/SecondPlayer/user/log/dusk_lan.txt | tail -n 1 | cut -c1-120)
    fin=$(grep -a "is a finalist" $P/SecondPlayer/user/log/dusk_lan.txt | tail -n 1 | cut -c1-9)
    ca=$(grep -c "Backtrace" $P/Lichii/user/log/eden_log.txt); cb=$(grep -c "Backtrace" $P/SecondPlayer/user/log/eden_log.txt)
    ua=$(grep -c "Unmapped" $P/Lichii/user/log/eden_log.txt); ub=$(grep -c "Unmapped" $P/SecondPlayer/user/log/eden_log.txt)
    fs=$(tail -n 1 diag/twin/night_pick_m$M.log 2>/dev/null | cut -c1-110); r3=$(grep -a "list decided" $P/SecondPlayer/user/log/dusk_lan.txt | tail -n 2 | head -n 1 | cut -c10-110)
    echo "$(date +%T) v$V final $c: finalist $fin | B list: $lst | $lr | backtraces A $ca B $cb | unmapped A $ua B $ub | pick: $fs | B r3: $r3" >> $OUT
    stopper "pick_area|gy_watch"
    bash diag/twin/run_night.sh logs $M > /dev/null 2>&1
    D=diag/net/trigger_$V; mkdir -p $D; cp -r diag/net/user3p_$(date +%m%d)_m$M $D/f${c}_a$AR; cp diag/twin/night_pick_m$M.log diag/twin/night_gy_m$M.log $D/f${c}_a$AR/ 2>/dev/null
    bash diag/twin/run_night.sh stop > /dev/null 2>&1
done
echo "$(date +%T) v$V done" >> $OUT
