#!/bin/bash
# runcut2.sh: ONE two-game match (A and B only, never more) that judges the three 3-8-player stages that two games
# can show (diag/net/walk8_notes.md, "What two games can exercise"). TEST RIG ONLY. Not a 3+ game run.
#   numbering   the numbering wait for a lobby of 3 and the lobby-size hand-on (type 14).
#               A fake lobby file "players 3" next to A's status file (A reads it; B can only HEAR it).
#               Expect: A "lobby: the match server put 3 games", B "lobby: 3 games in match .. (heard from game" "waiting for the others",
#               then after 12 s "numbering from this list", and two different numbers 1 and 2.
#               Why not DUSK_MATCH_MIN=3: the rig's match server (frontend_api.py MIN_PLAYERS) reads the same
#               variable and would never make a 2-player match. The lobby file drives the same wait code
#               ("lobby size" instead of "DUSK_MATCH_MIN") plus the sharing. The real server's own file is sent
#               to diag/twin/runcut2_server_match.txt (DUSK_MATCH_FILE) so it cannot overwrite the fake one.
#   tie         Phase I with nobody scoring (both players idle; stock cut limit -1, so nobody is cut): the cut
#               check (F1) ranks a Virtue tie. Both games must list the same ranks / hash (cutcheck.py: the tie
#               named, no "!!" in round 1). Totals not equal = NOT JUDGED.
#   handover    Phase II: the game with player no 2 kills enemies (kill.py) so it outscores no 1 (the host).
#               Then the round-2 cut limit is set to 1 on both games (cutlimit.py, the loaded param row,
#               this session only) and the phase is ended (clock.py).
#               Expect:
#                 - no 1 cut on both games ("H1: our player (no 1) is cut");
#                 - no 2 "authority: taken ... every lower-numbered player is cut";
#                 - the same round-2 list (cutcheck, no "!!").
#               No 1 not outscored = NOT JUDGED.
#               2026-11-16 (helper 3, after the 15:00 run): THIS ROW CANNOT PASS WITH TWO GAMES. dusk_lan.cpp CutStep
#               ("With exactly two players nobody is cut", review5 case 8): with TwoPlayers() a game at result step
#               14 / 29 / 36 is never recorded as cut, so no "H1: our player (no 1) is cut" line and no hand-over,
#               whatever the cut limit. (Also seen at 15:07: cutlimit.py refused B, "cfg vtable main+0x56D8A38 !=
#               main+0x56D8A28", so the limit stayed 6 there; the row values read were the right ones.) The row is
#               now reported as NOT JUDGEABLE (2 games) and is on the human test card (needs 4 players, host lowest).
# Groups: none applied (CUTAUTH, VIRTUE_TIEBREAK, FINALOUT are built in). With 2 entries CUTAUTH does not hold
# (CUTAUTH_MIN_ENTRIES 4); the run shows the cut lists (type 13 / 15), the cut and the hand-over.
# One "RESULT <row> <PASS|FAIL|NOT JUDGED> ..." line per row in diag/twin/runcut2.log. Timeouts on every step;
# the trap cleans up:
#   - the fake lobby file and its writer;
#   - hold_clock;
#   - the round-2 cut limit back to 6.
# Expected time: about 25 min (hub 6, match 5, Phase I 3, Phase II 6, judging 2).
cd <WORKSPACE> || exit 1
LOG=diag/twin/runcut2.log
LOGA="$APPDATA/eden/log/dusk_lan.txt"
LOGB=diag/twin/userB/log/dusk_lan.txt
FAKE="$APPDATA/eden/log/dusk_lan_match.txt"
say() { echo "[$(date +%T)] $*"; }
result() { echo "[$(date +%T)] RESULT $1 $2 | $3" | cut -c1-900 | tee -a "$LOG"; }
stop_hc() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*hold_clock*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
WRITER=
cleanup() {
  [ -n "$WRITER" ] && kill "$WRITER" 2>/dev/null && sleep 1
  grep -q "^match 990" "$FAKE" 2>/dev/null && rm -f "$FAKE"      # only our fake file (match id 990xxx)
  grep -q "^match 990" "$FAKE.tmp" 2>/dev/null && rm -f "$FAKE.tmp"   # review: a writer killed mid-write
  stop_hc
  timeout 40 python diag/twin/cutlimit.py AB 2 6 >/dev/null 2>&1   # stock Phase II limit (session param row)
  say "cleanup done"
}
trap cleanup EXIT INT TERM
echo "=== runcut2 $(date '+%F %T') ===" >> "$LOG"
[ "${TWIN_GAMES:-AB}" = AB ] || { result setup FAIL "TWIN_GAMES must be AB (two games only)"; exit 1; }
export TWIN_GAMES=AB
export DUSK_MATCH_FILE="$PWD/diag/twin/runcut2_server_match.txt"   # the server's real file (players 2) goes here
unset DUSK_MATCH_MIN
# review: never start while the user's own game or launcher runs (go_hub.sh kills every lichii.exe), and never
# overwrite a match file that is not ours (his own v3.9.4 server writes the same name into this folder).
own=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'Play.Duskbloods.exe' -or (\$_.Name -eq 'lichii.exe' -and \$_.ExecutablePath -notlike '*DuskbloodsWorkspace\\build\\lichii\\*') }).Count" | tr -d '\r')
[ "${own:-1}" = 0 ] || { trap - EXIT INT TERM; result setup FAIL "the user's own game or launcher runs (or the check failed): nothing started"; exit 1; }
if [ -e "$FAKE" ] && ! grep -q "^match 990" "$FAKE"; then
  trap - EXIT INT TERM; result setup FAIL "$FAKE exists and is not ours: not overwritten, nothing started"; exit 1
fi

# ---- hub (no groups needed)
rm -f diag/twin/go.log                    # review: a stale "hub-ready" from the last run would pass the wait at once
(DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 nohup bash diag/twin/go_hub.sh > diag/twin/go.log 2>&1 &)
n=0; until grep -q "hub-ready" diag/twin/go.log || [ $n -ge 45 ]; do sleep 8; n=$((n+1)); done
grep -q "hub-ready" diag/twin/go.log || { result setup FAIL "hub not ready in 6 min"; exit 1; }
say "hub: $(grep -c TIMEOUT diag/twin/go.log) timeouts"
LA0=$(wc -l < "$LOGA" 2>/dev/null || echo 0); LB0=$(wc -l < "$LOGB" 2>/dev/null || echo 0)

# ---- fake lobby of 3, kept fresh (the game takes files up to 300 s old) until the numbering is done
MID=990$((RANDOM % 900 + 100))
( while true; do printf 'match %s players 3 time %s\n' "$MID" "$(date +%s)" > "$FAKE.tmp" && mv -f "$FAKE.tmp" "$FAKE"; sleep 20; done ) &
WRITER=$!
sleep 5
DUSK_WAIT_LONGPOLL=3600 TO_MATCH_ONE_PRESS=1 timeout 300 python diag/twin/to_match2.py 2>&1 | tail -1
n=0; until timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -q "step 6 round 1" || [ $n -ge 25 ]; do sleep 8; n=$((n+1)); done
kill "$WRITER" 2>/dev/null; WRITER=; rm -f "$FAKE"
newA() { tail -n +"$((LA0 + 1))" "$LOGA" 2>/dev/null; }
newB() { tail -n +"$((LB0 + 1))" "$LOGB" 2>/dev/null; }
noA=$(newA | grep -o "player no [0-9]* team" | tail -1 | grep -o "[0-9]*" | head -1)
noB=$(newB | grep -o "player no [0-9]* team" | tail -1 | grep -o "[0-9]*" | head -1)
lobA=$(newA | grep -c "lobby: the match server put 3 games"); lobB=$(newB | grep -c "lobby: 3 games in match")
waitA=$(newA | grep -c "of 3 players listed (lobby size); waiting"); waitB=$(newB | grep -c "of 3 players listed (lobby size); waiting")
fallA=$(newA | grep -c "no change for 12 s; numbering from this list"); fallB=$(newB | grep -c "no change for 12 s; numbering from this list")
heardB=$(newB | grep -c "lobby: 3 games.*heard from game")
why="A no ${noA:-?} lobby $lobA wait $waitA fallback $fallA | B no ${noB:-?} lobby $lobB (heard $heardB) wait $waitB fallback $fallB"
if [ -z "$noA" ] || [ -z "$noB" ]; then result numbering FAIL "no player number on a game: $why"
elif [ "$noA" = "$noB" ]; then result numbering FAIL "DUPLICATE number $noA: $why"
elif [ "$lobA" -ge 1 ] && [ "$heardB" -ge 1 ] && [ "$waitA" -ge 1 ] && [ "$waitB" -ge 1 ] && [ "$fallA" -ge 1 ] && [ "$fallB" -ge 1 ]; then
  result numbering PASS "lobby 3 read on A and heard on B, both waited, both numbered after 12 s: $why"
elif [ "$lobA" -eq 0 ]; then result numbering "NOT JUDGED" "A never took the fake lobby file (too old / not read): $why"
else result numbering FAIL "lobby size not shared or no wait / fallback: $why"; fi
H1=$( [ "$noA" = 1 ] && echo A || echo B ); H2=$( [ "$H1" = A ] && echo B || echo A )
say "host (no 1) = $H1, no 2 = $H2"

# ---- Phase I: tie (both idle), end it early
sleep 22
timeout 60 python diag/twin/virtue.py AB > diag/twin/runcut2_virtue1.txt 2>&1
timeout 40 python diag/twin/clock.py 5 AB >/dev/null 2>&1
n=0; until timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round 2" || [ $n -ge 25 ]; do sleep 6; n=$((n+1)); done
sleep 10
r1A=$(newA | grep "cut check (F1): round 1 step" | tail -1 | cut -c1-300)
r1B=$(newB | grep "cut check (F1): round 1 step" | tail -1 | cut -c1-300)
hA=$(echo "$r1A" | grep -o "hash [0-9a-f]*" | head -1); hB=$(echo "$r1B" | grep -o "hash [0-9a-f]*" | head -1)
tot=$(echo "$r1A" | grep -o "ranked totals[^;]*" | head -1)
tie=$(echo "$r1A" | grep -q "; tie at " && echo yes || echo no)    # the F1 line names a tie ("tie at T (no:rank ..)")
if [ -z "$hA" ] || [ -z "$hB" ]; then result tie FAIL "no round-1 cut check line (A '$r1A' / B '$r1B')"
elif [ "$tie" != yes ]; then result tie "NOT JUDGED" "Virtue not tied in Phase I ($tot; see runcut2_virtue1.txt); lists $hA / $hB"
elif [ "$hA" = "$hB" ]; then result tie PASS "tie ($tot) ranked the same on both games: $hA"
else result tie FAIL "tie ($tot) ranked differently: A $hA / B $hB | A: $r1A | B: $r1B"; fi

# ---- Phase II: no 2 outscores the host, cut limit 1, end the phase
(nohup python diag/twin/hold_clock.py AB 300 3000 > diag/twin/hold.txt 2>&1 &)
say "KILLS on $H2 (no 2)"
for k in 1 2 3; do timeout 120 python diag/twin/kill.py "$H2" 12 2>&1 | tail -1 | cut -c1-200; done
timeout 60 python diag/twin/virtue.py AB > diag/twin/runcut2_virtue2.txt 2>&1
timeout 40 python diag/twin/cutlimit.py AB 2 1 2>&1 | tail -2
stop_hc
timeout 40 python diag/twin/clock.py 5 AB >/dev/null 2>&1
n=0; until newB | grep -q "cut check (F1): round 2 step" && newA | grep -q "cut check (F1): round 2 step" || [ $n -ge 20 ]; do sleep 6; n=$((n+1)); done
sleep 45                                  # the hand-over (lower_all_cut: no 15-s wait) and the type 13 / 15 answers
cutH1=$( ( [ "$H1" = A ] && newA || newB ) | grep -c "H1: our player (no 1) is cut")
roleH2=$( ( [ "$H2" = A ] && newA || newB ) | grep "authority: taken after" | tail -1 | cut -c1-200)
r2A=$(newA | grep "cut check (F1): round 2 step" | tail -1 | grep -o "hash [0-9a-f]*" | head -1)
r2B=$(newB | grep "cut check (F1): round 2 step" | tail -1 | grep -o "hash [0-9a-f]*" | head -1)
why="host $H1 cut-line $cutH1 | $H2 role '$roleH2' | lists A $r2A B $r2B | virtue: runcut2_virtue2.txt"
if [ "$cutH1" -ge 1 ] && echo "$roleH2" | grep -q "every lower-numbered player is cut" && [ -n "$r2A" ] && [ "$r2A" = "$r2B" ]; then
  result handover PASS "$why"
elif [ "$cutH1" -eq 0 ] && [ -n "$r2A" ] && [ "$r2A" = "$r2B" ]; then
  result handover "NOT JUDGEABLE (2 games)" "the host is never taken as cut with two players (CutStep TwoPlayers, review5 case 8): $why"
else result handover FAIL "$why"; fi

timeout 300 python diag/twin/cutcheck.py "A:$LOGA" "B:$LOGB" > diag/twin/runcut2_cutcheck.txt 2>&1
say "cutcheck: $(grep -c '!!' diag/twin/runcut2_cutcheck.txt) '!!' lines (diag/twin/runcut2_cutcheck.txt)"
bash diag/twin/alive.sh | tail -3
say "runcut2 done"
