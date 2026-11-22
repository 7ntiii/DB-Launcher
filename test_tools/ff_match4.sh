#!/bin/bash
# TEST ONLY (2026-11-18 match 4 with the user): fast-forward rounds 1-3 to the final.
cd <WORKSPACE>
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v3.9.13.zip" PKGTEST_PASSWORD=1
R="python diag/twin/pkgtest.py run"
waitfor() { until grep -E "^A:" diag/twin/watch_m4.log | tail -n 1 | grep -q "step 6 round $1"; do sleep 2; done; }
for r in 1 2 3; do waitfor $r; sleep 8; echo "$(date +%T) round $r -> 5 s"; $R diag/twin/set_clock.py AB 5; done
waitfor 4; echo "$(date +%T) final running"
