#!/bin/bash
# TEST ONLY: after round 1's step 6 starts, set the clock to 5 s once (set_clock.py), then take B / A pictures
# every 3 s for 75 s from the moment B logs "environment event" (round 2's card). bash diag/twin/envshots.sh V
cd <WORKSPACE> || exit 2
V=$1; R="python diag/twin/pkgtest.py run"; P=diag/twin/pkgtest/Duskbloods-Lichii-Online
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v$V.zip"
until grep -E "^A:" diag/twin/night_watch_m90.log | tail -n 1 | grep -q "step 6 round 1"; do sleep 2; done
sleep 5; $R diag/twin/set_clock.py AB 5 > /dev/null 2>&1; echo "$(date +%T) round 1 clock -> 5 s"
n0=$(grep -ac 'environment event' $P/SecondPlayer/user/log/dusk_lan.txt)
until [ "$(grep -ac 'environment event' $P/SecondPlayer/user/log/dusk_lan.txt)" -gt "$n0" ]; do sleep 1; done
echo "$(date +%T) env event logged"
for i in $(seq 1 25); do $R diag/twin/shot3big.py B "txt_${V}_env$i" > /dev/null 2>&1; $R diag/twin/shot3big.py A "txt_${V}_env$i" > /dev/null 2>&1; sleep 2; done
echo "$(date +%T) done"
