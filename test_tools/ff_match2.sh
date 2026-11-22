#!/bin/bash
# TEST ONLY (2026-11-17 match 2 with the user): fast-forward phases, take icon + timer probes on the way.
cd <WORKSPACE>
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v3.9.13.zip" PKGTEST_PASSWORD=1
R="python diag/twin/pkgtest.py run"
waitfor() { until grep -E "^A:" diag/twin/watch_3913.log | tail -n 1 | grep -q "step 6 round $1"; do sleep 2; done; }
waitfor 2; echo "$(date +%T) round 2 running"; sleep 15
$R diag/twin/icons_src.py AB > diag/net/icons_src_r2_3913.txt 2>&1; echo "$(date +%T) icons_src r2 done"
$R diag/twin/set_clock.py AB 5
waitfor 3; echo "$(date +%T) round 3 running"; sleep 15
$R diag/twin/icons_src.py AB > diag/net/icons_src_r3_3913.txt 2>&1
$R diag/twin/timer_probe3.py A snap A_p3 > /dev/null 2>&1; $R diag/twin/timer_probe3.py B snap B_p3 > /dev/null 2>&1
echo "$(date +%T) round 3 probes done"
$R diag/twin/set_clock.py AB 5
waitfor 4; echo "$(date +%T) final running"; sleep 10
$R diag/twin/timer_probe3.py A snap A_fin > /dev/null 2>&1; $R diag/twin/timer_probe3.py B snap B_fin > /dev/null 2>&1
$R diag/twin/timer_probe3.py cmp A_p3 A_fin > diag/net/timer3_A_p3_fin.txt 2>&1
$R diag/twin/timer_probe3.py cmp B_p3 B_fin > diag/net/timer3_B_p3_fin.txt 2>&1
echo "$(date +%T) final probes done"
