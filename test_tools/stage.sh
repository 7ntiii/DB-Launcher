#!/bin/bash
# stage check: host + guest treasure pick-up, list sync
cd <WORKSPACE>
echo "== stage $1 $(date +%T)"
timeout 280 python diag/twin/taketest.py A 2>&1 | grep "^target\|inventory change\|still listed" | cut -c1-150
timeout 280 python diag/twin/taketest.py B 2>&1 | grep "^target\|inventory change\|still listed" | cut -c1-150
timeout 60 python diag/twin/treasures.py AB 2>&1 | grep "world items" | cut -c1-110
timeout 60 python diag/twin/itemauth.py AB take 2>&1 | grep "^roles" | cut -c1-120
