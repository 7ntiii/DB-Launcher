#!/bin/bash
# TEST ONLY (text check, 2026-11-20): boot the two rig games on build V, take pictures at the hub, at the start of
# round 1 (env event card) and with the map open in Phase I. Pictures: diag/net/user3p_2311/{A,B}_txt_<V>_<what>.png
#   bash diag/twin/textcheck.sh alpha10
cd <WORKSPACE> || exit 2
V=$1; M=${2:-90}; export M
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v$V.zip" PKGTEST_PASSWORD=1 TO_MATCH_ONE_PRESS=1
R="python diag/twin/pkgtest.py run"
shot() { $R diag/twin/shot3big.py A "txt_${V}_$1" > /dev/null 2>&1; $R diag/twin/shot3big.py B "txt_${V}_$1" > /dev/null 2>&1; echo "$(date +%T) shot $1"; }
timeout 900 bash diag/twin/run_night.sh start "$V" > /dev/null 2>&1
nohup $R diag/twin/start3.py 2 > diag/twin/night_start3_m$M.log 2>&1 &
sleep 3
shot hub
timeout 300 $R diag/twin/to_match2b.py > /dev/null 2>&1
nohup $R diag/twin/watch_match.py 1200 AB --every 2 > diag/twin/night_watch_m$M.log 2>&1 &
ok=0; for i in $(seq 1 120); do grep -E "^A:" diag/twin/night_watch_m$M.log 2>/dev/null | tail -n 1 | grep -q "round 1" && { ok=1; break; }; sleep 2; done
[ $ok = 1 ] || { echo "no round 1"; shot noround; exit 1; }
shot r1_a; sleep 3; shot r1_b; sleep 4; shot r1_c; sleep 6; shot r1_d
for w in A B; do $R diag/twin/press1.py $w Minus > /dev/null 2>&1; done
sleep 3; shot map
echo done
