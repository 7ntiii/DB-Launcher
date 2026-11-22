#!/bin/bash
# TEST ONLY (LOADREL proof, 2026-11-20): N two-game rig finals on one build, B (guest) in its own start area.
#   bash diag/twin/loadrel_cycles.sh 3.9.20 5 force     v3.9.20: force_slots.py gives B its own area
#   bash diag/twin/loadrel_cycles.sh alpha4 5           alpha 4: FINALSLOTS2 does it itself
# Per final: fresh rig, 2-player match, ff to the final, 45 s into the final read LRBOX, the list, crashes.
# Result lines: diag/twin/loadrel_cycles.log. Stops the rig at the end.
cd <WORKSPACE> || exit 2
V=$1; N=${2:-5}; FORCE=$3
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v$V.zip" PKGTEST_PASSWORD=1 TO_MATCH_ONE_PRESS=1
R="python diag/twin/pkgtest.py run"
P=diag/twin/pkgtest/Duskbloods-Lichii-Online
OUT=diag/twin/loadrel_cycles.log
stopper() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match '$1' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
for c in $(seq 1 "$N"); do
    M=3$c; export M
    echo "$(date +%T) v$V final $c: start" >> $OUT
    timeout 900 bash diag/twin/run_night.sh start "$V" > /dev/null 2>&1
    stopper start3
    nohup $R diag/twin/start3.py 2 > diag/twin/night_start3_m$M.log 2>&1 &
    sleep 3
    timeout 300 $R diag/twin/to_match2b.py > /dev/null 2>&1
    nohup $R diag/twin/watch_match.py 3600 AB --every 5 > diag/twin/night_watch_m$M.log 2>&1 &
    # text check (2026-11-20): one picture of B at round 1's intermission map (the labels must be real text)
    TXT=-; for i in $(seq 1 60); do grep -E "^B:" diag/twin/night_watch_m$M.log 2>/dev/null | tail -n 1 | grep -q "step 26 round 1" && { sleep 3; $R diag/twin/shot3big.py B "txt_${V}_m$M" > /dev/null 2>&1; TXT="diag/net/user3p_2311/B_txt_${V}_m$M.png"; break; }; sleep 2; done
    ok=0; for i in $(seq 1 90); do grep -E "^A:" diag/twin/night_watch_m$M.log 2>/dev/null | tail -n 1 | grep -q "step 6 round 1" && { ok=1; break; }; sleep 4; done
    [ $ok = 1 ] || { echo "$(date +%T) v$V final $c: no round 1, skipped" >> $OUT; continue; }
    timeout 600 bash diag/twin/run_night.sh ff > /dev/null 2>&1 &
    FF=$!
    if [ "$FORCE" = force ]; then
        until grep -E "^A:" diag/twin/night_watch_m$M.log | tail -n 1 | grep -q "round 3"; do sleep 2; done
        sleep 20   # round 3's own intermission list is decided by now
        $R diag/twin/force_slots.py A 300 > diag/twin/force_slots_m$M.log 2>&1 &
    fi
    wait $FF
    # final pictures (2026-11-20, alpha 12): each game as placed, then the other player put 4 m in front of its camera
    sleep 2
    $R diag/twin/shot3big.py A "fin_${V}_m$M" > /dev/null 2>&1; $R diag/twin/shot3big.py B "fin_${V}_m$M" > /dev/null 2>&1
    $R diag/twin/place.py B A 5 1.5 > diag/twin/place_m$M.log 2>&1; sleep 2; $R diag/twin/shot3big.py B "seeA_${V}_m$M" > /dev/null 2>&1
    $R diag/twin/place.py A B 5 1.5 >> diag/twin/place_m$M.log 2>&1; sleep 2; $R diag/twin/shot3big.py A "seeB_${V}_m$M" > /dev/null 2>&1
    FIN="diag/net/user3p_2311/{A,B}_fin_${V}_m$M.png B_seeA A_seeB"
    sleep 25
    lr=$($R diag/twin/lrbox_read.py 2>&1 | grep LRBOX | awk '{print $1"="$4}' | tr '\n' ' ')
    lst=$(grep -a "list decided" $P/SecondPlayer/user/log/dusk_lan.txt | tail -n 1 | cut -c1-120)
    fin=$(grep -a "is a finalist" $P/SecondPlayer/user/log/dusk_lan.txt | tail -n 1 | cut -c1-9)
    ca=$(grep -c "Backtrace" $P/Lichii/user/log/eden_log.txt); cb=$(grep -c "Backtrace" $P/SecondPlayer/user/log/eden_log.txt)
    ua=$(grep -c "Unmapped" $P/Lichii/user/log/eden_log.txt); ub=$(grep -c "Unmapped" $P/SecondPlayer/user/log/eden_log.txt)
    fs=$(tail -n 1 diag/twin/force_slots_m$M.log 2>/dev/null | cut -c1-90)
    echo "$(date +%T) v$V final $c: finalist $fin | B list: $lst | $lr | backtraces A $ca B $cb | unmapped A $ua B $ub | force: $fs | text: $TXT | final: $FIN | replay: $(grep -a "WARPREPLAY" $P/SecondPlayer/user/log/dusk_lan.txt | tail -n 1 | cut -c10-260)" >> $OUT
    bash diag/twin/run_night.sh logs $M > /dev/null 2>&1
    bash diag/twin/run_night.sh stop > /dev/null 2>&1
done
echo "$(date +%T) v$V done" >> $OUT
