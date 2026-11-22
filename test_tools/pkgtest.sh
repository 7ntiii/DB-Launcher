#!/usr/bin/env bash
# 2026-11-16: one search press per game: a blind second press made one game leave the shared session (pkgtest399_notes.md).
export TO_MATCH_ONE_PRESS=${TO_MATCH_ONE_PRESS-1}
# pkgtest.sh: one-PC test of the v3.9.9 package's second-player scripts, from a scratch copy (2026-11-16, static,
# not run yet). Design and the reasons for each step: the docstring of diag/twin/pkgtest.py.
#
#   bash diag/twin/pkgtest.sh            full test: precheck, unpack, data copy, host, game 1, game 2, hub, match,
#                                        checks, treasures, untouched check, stop
#   bash diag/twin/pkgtest.sh stop       stop everything this test started (by its scratch path), nothing else
#   PKGTEST_CLEAN=1 bash diag/twin/pkgtest.sh [stop]   also delete diag\twin\pkgtest afterwards (nothing else)
#   PKGTEST_KEEP=1   leave both games running at the end (stop later with "pkgtest.sh stop")
#   PKGTEST_FROZEN=1 run the servers with Play.Duskbloods.exe --run-script (the launcher's own Python)
#
# Never: writes into %APPDATA%\eden (read-only copy), launcher\launcher_settings.json (read only), firewall or
# system settings. Refuses to start while lichii / eden / Play.Duskbloods / the twin rig / a host tool runs.
# Needs: about 1.5 GB disk (0.33 GB unpacked, 0.6 GB portable data copy, 0.6 GB SecondPlayer copy) plus logs
# (precheck wants 3.5 GB free); about 34 GB free commit (2 games x 17 GB).
set -u
WS="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$WS" || exit 2
PT="$WS/diag/twin/pkgtest"
PY=python
T() { $PY diag/twin/pkgtest.py "$@"; }
say() { echo "$(date +%H:%M:%S) [pkgtest.sh] $*" | tee -a "$PT/pkgtest_log.txt" 2>/dev/null || echo "$*"; }
RESULT=FAIL

finish() {
    if [ "${PKGTEST_KEEP:-0}" = 1 ]; then
        say "PKGTEST_KEEP=1: games left running; stop with: bash diag/twin/pkgtest.sh stop"
    else
        T stop
    fi
    if [ "${PKGTEST_CLEAN:-0}" = 1 ] && [ "${PKGTEST_KEEP:-0}" != 1 ]; then
        T clean
    fi
    echo "pkgtest result: $RESULT (log: $PT/pkgtest_log.txt)"
}

if [ "${1:-}" = stop ]; then
    T stop; [ "${PKGTEST_CLEAN:-0}" = 1 ] && T clean
    exit 0
fi

# 1. nothing of the user's or the rig's may run; ports, disk, commit
T precheck || { echo "pkgtest: precheck refused (see above); nothing was started"; exit 2; }
trap finish EXIT

# 2. scratch package + the launcher's server tools out of Play.Duskbloods.exe (read, not run)
T unpack || exit 1
# 3. portable Lichii\user (read-only copy of %APPDATA%\eden) + the scratch package's launcher_settings.json
T userdir || exit 1

# 4. host side, headless: launcher host servers + lan_fix_host / host_plus environment + host_plus relays
PT_WIN="$(cygpath -w "$PT")"
HPLOG="$PT/Duskbloods-Lichii-Online/lan_fix/host_plus_log.txt"
[ -f "$HPLOG" ] && mv -f "$HPLOG" "$HPLOG.prev"           # this run's relay lines only (scratch file)
N=$(wc -l < "$PT/pkgtest_log.txt" 2>/dev/null || echo 0)
$PY diag/twin/pkgtest.py serve "$PT_WIN\\serve" >> "$PT/serve_console.txt" 2>&1 &
for i in $(seq 1 30); do
    NEW="$(tail -n +$((N + 1)) "$PT/pkgtest_log.txt" 2>/dev/null)"
    echo "$NEW" | grep -q "relay threads started" && break
    echo "$NEW" | grep -q "serve ends\|did not answer\|make_pki failed\|stopped at start" && break
    sleep 2
done
for i in $(seq 1 15); do grep -q "relay 18455 -> 127.0.0.1:18445 ready" "$HPLOG" 2>/dev/null && break; sleep 2; done   # 2026-11-16: the second relay line can come a few seconds late
if ! grep -q "relay 18455 -> 127.0.0.1:18445 ready" "$HPLOG" 2>/dev/null; then
    say "host side not ready (see $PT/serve_console.txt and host_plus_log.txt)"; exit 1
fi
say "host side ready (frontdoor 18443, room 18445, panel API 18451, relays 18453 / 18455)"

# 5. game 1 as the launcher starts it (+ debug server 6545); wait for its sign-in before game 2
T game1 || exit 1
T waitdebug A || exit 1

# 6. game 2 through the package's own second_player.py (as "Start second player.cmd" runs it)
T game2 || { say "second_player.py did not do its part (see $PT/Duskbloods-Lichii-Online/SecondPlayer/second_player_log.txt)"; exit 1; }
T waitdebug B || exit 1

# 7. both games to the hub (rig tool, paths pointed at the pkgtest games)
TWIN_GAMES=AB timeout 900 $PY diag/twin/pkgtest.py run diag/twin/to_hub2b.py || say "to_hub2b did not report hub for both (continuing to the checks)"

# 8. the panel rows: 127.0.0.1 (game 1) and the LAN address (game 2) once both signed in
T rows || say "panel rows not both there yet"

# 9. into one match; the panel's Start match is pressed by the helper once both rows search
TO_MATCH_WAIT=90 timeout 900 $PY diag/twin/pkgtest.py run --autostart diag/twin/to_match2b.py || say "to_match2b reported a problem"

# 10. match check: panel rows + player 1 and 2 in both dusk_lan logs + peer pings + relays ready
T check && RESULT=PASS

# 11. item / treasure state of both games (read only), if the debug ports answer
timeout 300 $PY diag/twin/pkgtest.py run diag/twin/treasures.py AB 2>&1 | tee -a "$PT/pkgtest_log.txt" | tail -40

# 12. the user's own data and launcher settings must be unchanged
T untouched || RESULT="FAIL (user data changed)"
exit 0
