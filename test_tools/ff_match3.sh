#!/bin/bash
# TEST ONLY (2026-11-17 match 3 with the user): icon probe in round 2, timer_probe4 in the final.
cd <WORKSPACE>
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v3.9.13.zip" PKGTEST_PASSWORD=1
R="python diag/twin/pkgtest.py run"
waitfor() { until grep -E "^A:" diag/twin/watch_3913c.log | tail -n 1 | grep -q "step 6 round $1"; do sleep 2; done; }
waitfor 2; echo "$(date +%T) round 2 running"; sleep 15
$R diag/twin/icons_src.py AB > diag/net/icons_src_r2_m3.txt 2>&1; echo "$(date +%T) icons_src r2 done"
waitfor 3; echo "$(date +%T) round 3 running"; sleep 15
$R diag/twin/icons_src.py AB > diag/net/icons_src_r3_m3.txt 2>&1; echo "$(date +%T) icons_src r3 done"
waitfor 4; echo "$(date +%T) final running"; sleep 12
$R diag/twin/timer_probe4.py AB > diag/net/timer_probe4_m3.txt 2>&1
echo "$(date +%T) timer_probe4 done"
