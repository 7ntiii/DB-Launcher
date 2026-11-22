#!/bin/bash
# TEST ONLY (2026-11-18 match 5): end rounds 2-3 now, then fx_probe through the final.
cd <WORKSPACE>
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v3.9.15.zip" PKGTEST_PASSWORD=1
R="python diag/twin/pkgtest.py run"
waitfor() { until grep -E "^A:" diag/twin/watch_m5.log | tail -n 1 | grep -q "step 6 round $1"; do sleep 2; done; }
echo "$(date +%T) round 2 -> 5 s"; $R diag/twin/set_clock.py AB 5
waitfor 3; sleep 8; echo "$(date +%T) round 3 -> 5 s"; $R diag/twin/set_clock.py AB 5
waitfor 4; echo "$(date +%T) final running"; sleep 10
$R diag/twin/fx_probe.py AB 420 all > diag/net/fx_probe_m5.txt 2>&1
echo "$(date +%T) fx_probe done"
