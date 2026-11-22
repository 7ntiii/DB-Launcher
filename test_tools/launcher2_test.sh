#!/bin/bash
# TEST RIG ONLY: the NEW launcher (launcher2_src) hosts a room on the rig package, rig game 2 joins it,
# the panel's Start match is pressed and both games must load into a match. Result: diag/net/launcher2/rig.txt
cd <WORKSPACE> || exit 2
mkdir -p diag/net/launcher2; O=diag/net/launcher2/rig.txt; : > $O
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v${1:-merge4}.zip" PKGTEST_PASSWORD=1 RIG_NET=lan TO_MATCH_ONE_PRESS=1
R="python diag/twin/pkgtest.py run"
P=diag/twin/pkgtest/Duskbloods-Lichii-Online
python diag/twin/pkgtest.py stop > /dev/null 2>&1; taskkill //IM lichii.exe //F > /dev/null 2>&1; sleep 3
python diag/twin/pkgtest.py unpack 2>&1 | tail -n 1 | cut -c1-70 >> $O
python diag/twin/pkgtest.py userdir 2>&1 | tail -n 1 | cut -c1-70 >> $O
M=diag/twin/pkgtest/mei/tools
mkdir -p $P/servers/dusk_server $P/servers/npln_server
cp $M/dusk_server/frontdoor.py $M/dusk_server/response_schemas.json $P/lan_fix/frontend_api.py $P/servers/dusk_server/
cp $M/npln_server/make_pki.py $M/npln_server/npln_accounts.py $M/npln_server/npln_dashboard.py $P/lan_fix/npln_stub.py $P/servers/npln_server/
cp $P/lan_fix/panel.html $P/servers/
python - <<'PY'
import json
from pathlib import Path
pkg = Path('diag/twin/pkgtest/Duskbloods-Lichii-Online')
old = json.loads((pkg / 'launcher_settings.json').read_text(encoding='utf-8'))
(pkg / 'duskbloods_lan.json').write_text(json.dumps({'game': old.get('game', ''), 'mode': 'host', 'password': '1',
                                                     'room_name': 'launcher2 test', 'check_updates': False}), encoding='utf-8')
PY
L2=${L2:-launcher2_src/run.cmd}; : > $P/duskbloods_lan_log.txt
LAN=$(python -c "import sys; sys.path.insert(0,'launcher2_src'); from dusklan import network; print(network.home_network(network.networks())['ip'])")
echo "host address $LAN" >> $O
(DUSKLAN_BASE=$P EDEN_NX2_DEBUG_SERVER=127.0.0.1:6545 DUSK_P2P_PORTS="$LAN=15501" "$L2" --host > diag/net/launcher2/host.log 2>&1 &)
for i in $(seq 1 40); do grep -q "Game started\|^.\{20\}! " $P/duskbloods_lan_log.txt 2>/dev/null && break; sleep 2; done
cut -c1-160 $P/duskbloods_lan_log.txt >> $O
grep -q "Game started" $P/duskbloods_lan_log.txt || { echo "HOST START FAILED" >> $O; echo DONE >> $O; exit 1; }
python diag/twin/pkgtest.py waitdebug A 2>&1 | tail -n 1 | cut -c1-90 >> $O
(DUSKLAN_BASE="$(pwd -W)/$P" LICHII_USER_DIR="$(pwd -W)/$P/SecondPlayer/user" LICHII_PORT_MAP=15500=15501 EDEN_NX2_DEBUG_SERVER=127.0.0.1:6546 EDEN_NX2_ONLINE_PROFILES="$(pwd -W)/$P/SecondPlayer/user/online" "$L2" --join $LAN > diag/net/launcher2/join.log 2>&1 &); sleep 8; tail -n 3 $P/duskbloods_lan_log.txt | cut -c1-160 >> $O
python diag/twin/pkgtest.py waitdebug B 2>&1 | tail -n 1 | cut -c1-90 >> $O
timeout 600 $R diag/twin/to_hub2b.py 2>&1 | tail -n 1 | cut -c1-120 >> $O
($R diag/twin/start3.py 2 > diag/twin/night_start3_m18.log 2>&1 &)
sleep 4
J=$($R diag/twin/to_match2b.py 2>&1 | tail -n 1 | cut -c1-150); echo "to_match: $J" >> $O
if echo "$J" | grep -q FAILED; then
    $R diag/twin/pressy.py B B 1 > /dev/null 2>&1; sleep 1
    $R diag/twin/pressy.py B Minus 1 > /dev/null 2>&1; sleep 2
    $R diag/twin/pressy.py A Y 1 > /dev/null 2>&1; $R diag/twin/pressy.py B Y 1 > /dev/null 2>&1
    echo "to_match: by hand" >> $O
fi
($R diag/twin/watch_match.py 300 AB --every 5 > diag/twin/night_watch_m18.log 2>&1 &)
rnd() { grep -E "^A:" diag/twin/night_watch_m18.log 2>/dev/null | tail -n 1 | grep -q "step 6 round $1"; }
for i in $(seq 1 100); do rnd 1 && break; sleep 3; done
rnd 1 && echo "MATCH RUNNING" >> $O || echo "NO MATCH" >> $O
grep -E "^A:|^B:" diag/twin/night_watch_m18.log | tail -n 2 | cut -c1-110 >> $O
$R diag/twin/shot3big.py A l2_match_a > /dev/null 2>&1; $R diag/twin/shot3big.py B l2_match_b > /dev/null 2>&1
echo DONE >> $O
