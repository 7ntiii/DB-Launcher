#!/bin/bash
# alpha 19 rig check (TEST ONLY): two games, LAN. Output: diag/net/zt_faults/a19_rig.txt
cd <WORKSPACE> || exit 2
O=diag/net/zt_faults/a19_rig.txt; : > $O
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online valpha19a.zip" PKGTEST_PASSWORD=1 RIG_NET=lan TO_MATCH_ONE_PRESS=1
R="python diag/twin/pkgtest.py run"
P=diag/twin/pkgtest/Duskbloods-Lichii-Online
for i in $(seq 1 60); do grep -q "room registered\|did not answer\|stopped at start" diag/twin/night_serve.log 2>/dev/null && break; sleep 2; done
RIG_NET=lan M=12 bash diag/twin/run_night.sh start alpha19a 2>&1 | tail -n 1 | cut -c1-150 >> $O
($R diag/twin/start3.py 2 > diag/twin/night_start3_m12.log 2>&1 &)
sleep 4
J=$($R diag/twin/to_match2b.py 2>&1 | tail -n 1 | cut -c1-150); echo "to_match: $J" >> $O
if echo "$J" | grep -q FAILED; then          # B's tilted camera: open the menu by hand, then search on both
    $R diag/twin/pressy.py B B 1 > /dev/null 2>&1; sleep 1
    $R diag/twin/pressy.py B Minus 1 > /dev/null 2>&1; sleep 2
    $R diag/twin/screen.py 2>&1 | tail -n 2 >> $O
    $R diag/twin/pressy.py A Y 1 > /dev/null 2>&1; $R diag/twin/pressy.py B Y 1 > /dev/null 2>&1
    echo "to_match: by hand" >> $O
fi
($R diag/twin/watch_match.py 1500 AB --every 5 > diag/twin/night_watch_m12.log 2>&1 &)
rnd() { grep -E "^A:" diag/twin/night_watch_m12.log 2>/dev/null | tail -n 1 | grep -q "step 6 round $1"; }
for k in 1 2 3 4 5 6 7 8 9 10; do
    $R diag/twin/shot3big.py A a19_load_a$k > /dev/null 2>&1; $R diag/twin/shot3big.py B a19_load_b$k > /dev/null 2>&1
done
for i in $(seq 1 60); do rnd 1 && break; sleep 3; done
rnd 1 || { echo "NO MATCH" >> $O; $R diag/twin/screen.py 2>&1 | tail -n 2 >> $O; echo DONE >> $O; exit 1; }
$R diag/twin/nodeath.py A on > /dev/null 2>&1; $R diag/twin/nodeath.py B on > /dev/null 2>&1
sleep 10
$R diag/twin/set_clock.py AB 5 > /dev/null 2>&1
for i in $(seq 1 60); do rnd 2 && break; sleep 3; done
sleep 20
($R diag/twin/hold_clock_smooth.py AB 600 1200 nohp > diag/twin/night_hold_m12.log 2>&1 &)
echo "== round 2 $(date +%T): bosses before any battle" >> $O
$R diag/twin/trespassers.py AB 2>&1 | grep -E "^[AB]:|ins 0x|participants|enemy chr|goto:" | cut -c1-150 >> $O
# both players to the first boss of game A (its goto line), 3 m apart
G=$($R diag/twin/trespassers.py A 2>&1 | grep "goto:" | head -n 1 | sed 's/.*goto.py A //')
set -- $G
if [ -n "$3" ]; then
    $R diag/twin/goto.py A $1 $2 $3 > /dev/null 2>&1
    $R diag/twin/goto.py B $(python -c "print($1 + 3)") $2 $3 > /dev/null 2>&1
    echo "== both players at the boss ($1 $2 $3) $(date +%T)" >> $O
    for w in 8 20 35; do
        sleep $([ $w = 8 ] && echo 8 || echo 13)
        echo "-- +$w s" >> $O
        $R diag/twin/trespassers.py AB 2>&1 | grep -E "^[AB]:|ins 0x|participants|enemy chr" | grep -B1 -A2 "step [2-9]" | cut -c1-170 >> $O
    done
fi
echo "== logs" >> $O
for g in Lichii SecondPlayer; do
    echo "-- $g: unmapped $(grep -c Unmapped $P/$g/user/log/eden_log.txt)" >> $O
    grep -n "partsync\|levels:\|line-up: hold\|!!!\|HPO" $P/$g/user/log/dusk_lan.txt | cut -c1-230 | tail -n 14 >> $O
done
grep -E "^A:|^B:" diag/twin/night_watch_m12.log | tail -n 2 | cut -c1-70 >> $O
$R diag/twin/shot3big.py A a19_boss_a > /dev/null 2>&1; $R diag/twin/shot3big.py B a19_boss_b > /dev/null 2>&1
echo DONE >> $O
