#!/bin/bash
# alpha 20 rig check (TEST ONLY): match, then the Vanish Dash on rig A next to B with fx_probe on both games.
cd <WORKSPACE> || exit 2
O=diag/net/zt_faults/merge3_rig.txt; : > $O
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online vmerge3.zip" PKGTEST_PASSWORD=1 RIG_NET=lan TO_MATCH_ONE_PRESS=1
R="python diag/twin/pkgtest.py run"
P=diag/twin/pkgtest/Duskbloods-Lichii-Online
for i in $(seq 1 60); do grep -q "room registered\|did not answer\|stopped at start" diag/twin/night_serve.log 2>/dev/null && break; sleep 2; done
RIG_NET=lan M=15 bash diag/twin/run_night.sh start merge3 2>&1 | tail -n 1 | cut -c1-150 >> $O
($R diag/twin/start3.py 2 > diag/twin/night_start3_m17.log 2>&1 &)
sleep 4
J=$($R diag/twin/to_match2b.py 2>&1 | tail -n 1 | cut -c1-150); echo "to_match: $J" >> $O
if echo "$J" | grep -q FAILED; then
    $R diag/twin/pressy.py B B 1 > /dev/null 2>&1; sleep 1
    $R diag/twin/pressy.py B Minus 1 > /dev/null 2>&1; sleep 2
    $R diag/twin/pressy.py A Y 1 > /dev/null 2>&1; $R diag/twin/pressy.py B Y 1 > /dev/null 2>&1
    echo "to_match: by hand" >> $O
fi
($R diag/twin/watch_match.py 900 AB --every 5 > diag/twin/night_watch_m17.log 2>&1 &)
rnd() { grep -E "^A:" diag/twin/night_watch_m17.log 2>/dev/null | tail -n 1 | grep -q "step 6 round $1"; }
for i in $(seq 1 100); do rnd 1 && break; sleep 3; done
rnd 1 || { echo "NO MATCH" >> $O; $R diag/twin/screen.py 2>&1 | tail -n 2 >> $O; echo DONE >> $O; exit 1; }
($R diag/twin/hold_clock_smooth.py AB 600 900 nohp > diag/twin/night_hold_m17.log 2>&1 &)
($R diag/twin/fps_watch.py AB 150 > diag/twin/night_fps_m17.log 2>&1 &)
$R diag/twin/shot3big.py A merge3_match_a > /dev/null 2>&1; $R diag/twin/shot3big.py B merge3_match_b > /dev/null 2>&1
$R diag/twin/nodeath.py A on > /dev/null 2>&1; $R diag/twin/nodeath.py B on > /dev/null 2>&1
sleep 6
$R diag/twin/bring_to.py 1 2>&1 | tail -n 2 >> $O         # both next to player 1 (A stays near itself, B comes)
sleep 3
($R diag/twin/fx_probe.py AB 75 all > diag/net/zt_faults/merge3_fx.txt 2>&1 &)
sleep 5
# candidate inputs on A, each with a mark in the output: dodge / dash and the skill buttons
for step in "B" "L" "ZL" "X" "R" "ZR" "L+B" "ZL+B"; do
    echo "$(date +%T) input $step" >> $O
    case $step in
        L+B)  $R diag/twin/pressy.py A L 1 > /dev/null 2>&1; sleep 1; $R diag/twin/stick.py A 0 1 12 B > /dev/null 2>&1 ;;
        ZL+B) $R diag/twin/pressy.py A ZL 1 > /dev/null 2>&1; sleep 1; $R diag/twin/stick.py A 0 1 12 B > /dev/null 2>&1 ;;
        B)    $R diag/twin/stick.py A 0 1 12 B > /dev/null 2>&1 ;;
        *)    $R diag/twin/pressy.py A $step 1 > /dev/null 2>&1 ;;
    esac
    sleep 6
done
sleep 12
echo "== fx on A's own player (p1) and on B's copy of it" >> $O
grep -E "A p1:|B p1:" diag/net/zt_faults/merge3_fx.txt | grep -E "142643|14010|1401|1444|1407|140070|140171" | cut -c1-200 | head -n 40 >> $O
echo "== summary lines" >> $O
sed -n '/--- summary/,$p' diag/net/zt_faults/merge3_fx.txt | cut -c1-230 >> $O
echo "== boot lines (A)" >> $O
grep -hE "cave region|built-in|unexpected original|Nextendo|Online redirect|frames_ahead|does not fit|Lichii Version|Total Pipeline|JIT seed|GPU thread split" $P/Lichii/user/log/eden_log.txt | cut -c1-210 | head -n 16 >> $O
echo "== fps" >> $O; tail -n 6 diag/twin/night_fps_m17.log | cut -c1-200 >> $O
grep -hc "<Critical>" $P/Lichii/user/log/eden_log.txt $P/SecondPlayer/user/log/eden_log.txt >> $O
for g in Lichii SecondPlayer; do echo "-- $g: unmapped $(grep -c Unmapped $P/$g/user/log/eden_log.txt)" >> $O; done
grep -E "^A:|^B:" diag/twin/night_watch_m17.log | tail -n 2 | cut -c1-70 >> $O
echo DONE >> $O
