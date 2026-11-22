#!/bin/bash
# TEST RIG ONLY: alpha 20 frame-rate baseline for the merge comparison (same steps as the merge2 run):
# match round 1 sample, then the final sample. Result: diag/net/merge366/base20_fps.txt
cd <WORKSPACE> || exit 2
O=diag/net/merge366/base20_fps.txt; : > $O
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online vmerge2.zip" PKGTEST_PASSWORD=1 RIG_NET=lan TO_MATCH_ONE_PRESS=1
python diag/twin/pkgtest.py stop > /dev/null 2>&1
sleep 4
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online valpha20.zip"
R="python diag/twin/pkgtest.py run"
rm -f diag/twin/pkgtest/unpacked.ok
python diag/twin/pkgtest.py unpack 2>&1 | tail -n 1 | cut -c1-80 >> $O
: > diag/twin/night_serve.log
(python diag/twin/pkgtest.py serve > diag/twin/night_serve.log 2>&1 &)
for i in $(seq 1 60); do grep -q "room registered\|did not answer\|stopped at start" diag/twin/night_serve.log 2>/dev/null && break; sleep 2; done
RIG_NET=lan M=16 bash diag/twin/run_night.sh start alpha20 2>&1 | tail -n 1 | cut -c1-150 >> $O
($R diag/twin/start3.py 2 > diag/twin/night_start3_m16.log 2>&1 &)
sleep 4
J=$($R diag/twin/to_match2b.py 2>&1 | tail -n 1 | cut -c1-150); echo "to_match: $J" >> $O
if echo "$J" | grep -q FAILED; then
    $R diag/twin/pressy.py B B 1 > /dev/null 2>&1; sleep 1
    $R diag/twin/pressy.py B Minus 1 > /dev/null 2>&1; sleep 2
    $R diag/twin/pressy.py A Y 1 > /dev/null 2>&1; $R diag/twin/pressy.py B Y 1 > /dev/null 2>&1
    echo "to_match: by hand" >> $O
fi
($R diag/twin/watch_match.py 240 AB --every 5 > diag/twin/night_watch_m16.log 2>&1 &)
rnd() { grep -E "^A:" diag/twin/night_watch_m16.log 2>/dev/null | tail -n 1 | grep -q "step 6 round $1"; }
for i in $(seq 1 100); do rnd 1 && break; sleep 3; done
rnd 1 || { echo "NO MATCH" >> $O; echo DONE >> $O; exit 1; }
sleep 25
echo "== match round 1" >> $O
$R diag/twin/fps_watch.py AB 14 --low 500 2>&1 | grep LOW | cut -c1-80 >> $O
$R diag/twin/shot3big.py A base20_match_a > /dev/null 2>&1
$R diag/twin/to_final.py 600 2>&1 | tail -n 1 >> $O
sleep 60
echo "== final" >> $O
$R diag/twin/fps_watch.py AB 14 --low 500 2>&1 | grep LOW | cut -c1-80 >> $O
$R diag/twin/shot3big.py A base20_final_a > /dev/null 2>&1; $R diag/twin/shot3big.py B base20_final_b > /dev/null 2>&1
echo DONE >> $O
