#!/bin/bash
# TEST ONLY (made 2026-11-18 for the joint test that night). One command per step, laptop = player 2,
# rig A = host player 1 (this PC runs the match server), rig B = player 3. Two rig games only.
#   bash diag/twin/run_night.sh start 3.9.16     fresh rig on that zip: unpack, servers, A, B, hub, start3 (waits for the laptop)
#   bash diag/twin/run_night.sh match            when the laptop searches: join, watch, hold Phase I at 600 s, fps_watch
#   bash diag/twin/run_night.sh hold             hold the current phase clock at 600 s (stops any other hold first)
#   bash diag/twin/run_night.sh ff               end the current and later phases (5 s each) up to the final; no probe
#   bash diag/twin/run_night.sh blink            8-s Blink site reading on B (B's player must cast Blink right then)
#   bash diag/twin/run_night.sh storm | storm-off  storm re-check on A+B in the background (when the storm is drawn)
#   bash diag/twin/run_night.sh fx               fire probe on A+B for 150 s (20 s+ into the final only)
#   bash diag/twin/run_night.sh logs N           copy the rig logs to diag/net/user3p_<date>_mN/
#   bash diag/twin/run_night.sh stop             stop the rig tools and both rig games (never the launcher)
# Logs: diag/twin/night_*.log. Match number for log names: M=<n> (default 1).
# RIG_NET=tailscale (tailscale_rig_notes.md): the rig hosts on this PC's Tailscale address (`tailscale ip -4`,
# read only); every other player joins with that 100.x. RIG_PLAYERS=<n> (default 4) players in all: start3
# presses Start match at n searching, `match` waits for n-2 remote ones. Unset / lan = the home match as before.
cd <WORKSPACE> || exit 2
M=${M:-1}
RIG_NET=${RIG_NET:-lan}; export RIG_NET
RIG_PLAYERS=${RIG_PLAYERS:-4}
LAPTOP_IP=${LAPTOP_IP:-192.168.1.66}   # the laptop's LAN address (start3's log shows it when it searches)
serve_net() { python -c "import json; print(json.load(open('diag/twin/pkgtest/state.json')).get('rig_net', 'lan'))" 2>/dev/null || echo lan; }
V=${V:-$(cat diag/twin/.night_version 2>/dev/null || echo 3.9.16)}
export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v$V.zip" PKGTEST_PASSWORD=1 TO_MATCH_ONE_PRESS=1
R="python diag/twin/pkgtest.py run"
P=diag/twin/pkgtest/Duskbloods-Lichii-Online
stopper() {   # by process name + tool name only (a command-line-only filter once killed my own shell)
    powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match '$1' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
}
round_now() { grep -E "^A:" diag/twin/night_watch_m$M.log 2>/dev/null | tail -n 1 | sed -n 's/.*step 6 round \([0-9]\).*/\1/p'; }
case "$1" in
start)
    V=${2:-$V}; echo "$V" > diag/twin/.night_version
    export PKGTEST_ZIP="share/Duskbloods-Lichii-Online v$V.zip"
    [ -f "$PKGTEST_ZIP" ] || { echo "no $PKGTEST_ZIP"; exit 1; }
    if [ "$RIG_NET" = tailscale ]; then
        TSIP=$( (tailscale ip -4 2>/dev/null || "/c/Program Files/Tailscale/tailscale.exe" ip -4 2>/dev/null) | tr -d '\r' \
            | grep -E '^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.' | head -n 1)   # read only
        [ -n "$RIG_VPN_IP" ] && TSIP=$RIG_VPN_IP   # another VPN (ZeroTier): RIG_VPN_IP + DUSK_VPN_NET + DUSK_VPN_NAME
        [ -n "$TSIP" ] || { echo "RIG_NET=tailscale: no 100.x address from 'tailscale ip -4' (sign in to Tailscale first); nothing done"; exit 1; }
        echo "$(date +%T) Tailscale rig: every other player joins with $TSIP (Online, Join a room), $RIG_PLAYERS players in all"
    fi
    if powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'pkgtest.py serve' }" | grep -q python \
        && [ "$(serve_net)" != "$RIG_NET" ]; then
        echo "a pkgtest serve for '$(serve_net)' is running, this start is '$RIG_NET': run 'python diag/twin/pkgtest.py stop' first; nothing done"
        exit 1
    fi
    stopper 'watch_match|start3|hold_clock|fps_watch|to_match2b|fx_probe'
    taskkill //IM lichii.exe //F >/dev/null 2>&1; sleep 3
    python diag/twin/pkgtest.py unpack 2>&1 | tail -n 1 | cut -c1-80
    python diag/twin/pkgtest.py userdir 2>&1 | tail -n 1 | cut -c1-80
    if ! powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'pkgtest.py serve' }" | grep -q python; then
        nohup python diag/twin/pkgtest.py serve > diag/twin/night_serve.log 2>&1 &
        sleep 8
    fi
    python diag/twin/pkgtest.py game1 2>&1 | tail -n 1 | cut -c1-80
    python diag/twin/pkgtest.py waitdebug A 2>&1 | tail -n 1
    python diag/twin/pkgtest.py game2 2>&1 | tail -n 1 | cut -c1-80
    python diag/twin/pkgtest.py waitdebug B 2>&1 | tail -n 1
    timeout 600 $R diag/twin/to_hub2b.py 2>&1 | tail -n 1
    N3=3; [ "$RIG_NET" = tailscale ] && N3=$RIG_PLAYERS
    nohup $R diag/twin/start3.py $N3 > diag/twin/night_start3_m$M.log 2>&1 &
    echo "$(date +%T) v$V: both rig games in the hub, start3 waiting for $N3 searching players (log night_start3_m$M.log)"
    ;;
match)
    if [ "$RIG_NET" = tailscale ]; then
        python diag/twin/remote_search.py $((RIG_PLAYERS - 2)) || exit 1
    else
        until tail -n 1 diag/twin/night_start3_m$M.log | grep -q "$LAPTOP_IP', 'search'"; do sleep 1; done
        echo "$(date +%T) laptop ($LAPTOP_IP) searching"
    fi
    $R diag/twin/to_match2b.py
    nohup $R diag/twin/watch_match.py 3600 AB --every 5 > diag/twin/night_watch_m$M.log 2>&1 &
    nohup $R diag/twin/fps_watch.py AB 3600 > diag/twin/night_fps_m$M.log 2>&1 &
    until [ "$(round_now)" = 1 ]; do sleep 2; done
    echo "$(date +%T) round 1 running, holding the clock at 600"
    nohup $R diag/twin/hold_clock_smooth.py AB 600 7200 nohp > diag/twin/night_hold_m$M.log 2>&1 &
    ;;
hold)
    stopper 'hold_clock'
    nohup $R diag/twin/hold_clock_smooth.py AB 600 7200 nohp > diag/twin/night_hold_m$M.log 2>&1 &
    echo "$(date +%T) holding round $(round_now) at 600"
    ;;
ff)
    stopper 'hold_clock|storm_watch'   # no storm reader left running into the final
    r=$(round_now); [ -z "$r" ] && { echo "not in a phase (step 6) now"; exit 1; }
    while [ "$r" -le 3 ]; do
        echo "$(date +%T) round $r -> 5 s"; $R diag/twin/set_clock.py AB 5
        n=$((r + 1)); until [ "$(round_now)" = "$n" ]; do sleep 2; done; sleep 8; r=$n
        [ "$r" = 4 ] && break
    done
    echo "$(date +%T) final running (no probe at its start; fps_watch is on: tail night_fps_m$M.log)"
    ;;
storm)
    # storm re-check (row 39, read only): start when the storm is drawn; runs in the background up to 60 min
    stopper storm_watch
    nohup $R diag/twin/storm_watch.py AB 3600 > diag/net/storm_watch_night_m$M.txt 2>&1 &
    echo "$(date +%T) storm_watch on A+B (diag/net/storm_watch_night_m$M.txt); storm-off / ff / blink / fx / stop end it"
    ;;
storm-off)
    stopper storm_watch
    echo "$(date +%T) storm_watch stopped"
    ;;
blink)
    stopper storm_watch   # one debug reader at a time
    $R diag/twin/blink_site.py B 8 2>&1 | tee diag/net/blink_site_night_m$M.txt | tail -n 8
    ;;
fx)
    stopper storm_watch   # one debug reader at a time
    # fire probe (card test 3): only 20 s+ after "final: player N is in the final with us" (no probe at a final's start)
    $R diag/twin/fx_probe.py AB 150 all 2>&1 | tee diag/net/fx_probe_night_m$M.txt | grep -E "DIES|GONE" | tail -n 8
    ;;
logs)
    D=diag/net/user3p_$(date +%m%d)_m${2:-$M}; mkdir -p "$D"
    cp $P/Lichii/user/log/dusk_lan.txt "$D/A_dusk_lan.txt"; cp $P/SecondPlayer/user/log/dusk_lan.txt "$D/B_dusk_lan.txt"
    cp $P/Lichii/user/log/eden_log.txt "$D/A_eden_log.txt"; cp $P/SecondPlayer/user/log/eden_log.txt "$D/B_eden_log.txt"
    cp diag/twin/night_*_m${2:-$M}.log "$D/" 2>/dev/null
    cp diag/net/blink_site_night_m${2:-$M}.txt diag/net/fx_probe_night_m${2:-$M}.txt diag/net/storm_watch_night_m${2:-$M}.txt "$D/" 2>/dev/null
    echo "$V" > "$D/build.txt"
    echo "logs in $D (build v$V)"
    ;;
stop)
    stopper 'watch_match|start3|hold_clock|fps_watch|to_match2b|fx_probe|blink_site|storm_watch'
    taskkill //IM lichii.exe //F >/dev/null 2>&1
    echo "rig stopped (launcher untouched)"
    ;;
*)
    sed -n 2,16p "$0"
    ;;
esac
