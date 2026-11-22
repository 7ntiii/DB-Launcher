#!/bin/bash
# RIG DEFAULTS 2026-11-16: every passing run used these; without them the loader skews 20 s and a rank row is lost.
export DUSK_WAIT_LONGPOLL=${DUSK_WAIT_LONGPOLL-3600} TWIN_P2P_FORMAT=${TWIN_P2P_FORMAT-self} TO_MATCH_ONE_PRESS=${TO_MATCH_ONE_PRESS-1}
# One-shot twin test: stop old rig, clear logs, launch both games + watchers, drive to hub and into a
# match with screen checks. QW_* env vars pass through to the watchers. Output: diag/twin/go.log
cd <WORKSPACE>
taskkill //F //IM lichii.exe >/dev/null 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'quic_watch|npln_stub|frontdoor|twin4?.py|to_hub|to_match' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
rm -f diag/net/quic_watch.log diag/net/quic_watch_B.log diag/net/qw_st_*.txt diag/net/qw_stop_* diag/net/qw_cmd_*.txt
# (the assist keeps the last five dusk_lan logs itself: never delete them here, the user needs them)
echo "start $(date +%T)"
# TWIN_ARGS: e.g. --no-watch (no gdbstub/watcher; the build's LAN patch + assist do the work)
python diag/twin/twin.py ${TWIN_ARGS---no-watch} > diag/twin/twin_console.log 2>&1 &
sleep 5
python diag/twin/to_hub2.py
python diag/twin/to_match2.py
echo "nav done $(date +%T)"
wait
