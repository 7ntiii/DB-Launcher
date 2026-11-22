#!/bin/bash
# TEST ONLY (2026-11-18 match 5): join when the laptop searches, then hold Phase I's clock at 10 min.
cd <WORKSPACE>
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v3.9.15.zip" PKGTEST_PASSWORD=1
R="python diag/twin/pkgtest.py run"
until tail -n 1 diag/twin/start3_m5.log | grep -q "192.168.1.66', 'search'"; do sleep 1; done
echo "$(date +%T) laptop searching"
$R diag/twin/to_match2b.py
nohup $R diag/twin/watch_match.py 3600 AB --every 5 > diag/twin/watch_m5.log 2>&1 &
until grep -E "^A:" diag/twin/watch_m5.log 2>/dev/null | tail -n 1 | grep -q "step 6 round 1"; do sleep 2; done
echo "$(date +%T) round 1 running, holding the clock at 600"
nohup $R diag/twin/hold_clock_smooth.py AB 600 7200 nohp > diag/twin/hold_m5.log 2>&1 &
