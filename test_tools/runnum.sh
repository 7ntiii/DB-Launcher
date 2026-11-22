#!/bin/bash
# runnum.sh: the v413 number exchange on TWO games (A, B only), helper 4's recipe (diag/net/audit8_numbering.md,
# "What two games can exercise"). TEST RIG ONLY. Written 2026-11-16 (helper 3). Not run yet.
# Needs the build WITH v412b + v413 (the guard looks for "v413" in build/lichii/bin/lichii.exe).
#   run 1 "plain": go_hub.sh as the passing runs, no switch.
#     plain_numbers   numbers 1 and 2, delivered, no DUPLICATE line
#     plain_no_v413   no "(v413)" line on either game (the two-player path is today's)
#     plain_timing    "session state 2/3" -> "message 4 armed" per game no longer than the baseline + 2 s; the
#                     baseline = the dusk_lan logs present when this script starts (the previous run, v3.9.6), or
#                     BASE_A / BASE_B. NOT JUDGED when a baseline time cannot be read
#     plain_phase1    both games at step 6 round 1, every rank entry on both games state 01010000 (part_flag)
#   run 2 "force1": DUSK_NUMBER_FORCE_B=1 for game B only (twin.py gives LICHII_USER_DIR to B only; the switch is
#     honoured only there). Checks force1_yield (exactly one "taking N instead (v413)" line, on one game; NOT JUDGED
#     when none: B's member id was the lower one, so it kept 1), force1_numbers, force1_phase1 as above.
#   run 3 "force2" only when run 2 had no yield: DUSK_NUMBER_FORCE_B=2 (A then yields to 1), the same checks.
# The switch lives only in a subshell around go_hub.sh. Every hub start kills all lichii.exe first, and at the exit
# the rig games are closed if a forced run was the last, so B never keeps the switch into a later run.
# Time: about 9 min per run (hub 6, match 2, checks 1): 18 min, 27 min with run 3.
cd <WORKSPACE> || exit 1
LOG=diag/twin/runnum.log
LOGA="$APPDATA/eden/log/dusk_lan.txt"
LOGB=diag/twin/userB/log/dusk_lan.txt
EXE=build/lichii/bin/lichii.exe
say() { echo "[$(date +%T)] $*"; }
result() { echo "[$(date +%T)] RESULT $1 $2 | $3" | cut -c1-700 | tee -a "$LOG"; }
stop_hc() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*hold_clock*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
kill_rig() { powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='lichii.exe'\" | Where-Object { \$_.ExecutablePath -match 'DuskbloodsWorkspace.build.lichii.bin' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"; }
unset DUSK_NUMBER_FORCE_B
LAST_FORCED=0
STARTED=0
final_cleanup() {
  stop_hc >/dev/null 2>&1
  [ "$STARTED" = 1 ] || return 0
  if [ "$LAST_FORCED" = 1 ]; then kill_rig >/dev/null 2>&1; say "rig games closed (the last run had DUSK_NUMBER_FORCE_B)"; fi
}
trap final_cleanup EXIT
trap 'exit 130' INT TERM
echo "=== runnum $(date '+%F %T') ===" >> "$LOG"

# ---- guards
other=$(timeout 60 python diag/twin/run3_check.py userrun 2>/dev/null | tr -d '\r')
[ -n "$other" ] && { result guard FAIL "the user's game or launcher is running ($other): nothing started"; exit 2; }
rig=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'item_loop|regress_small|runitem|match4|to_match' }).Count" 2>/dev/null | tr -d '\r')
[ "${rig:-0}" = 0 ] || { result guard FAIL "$rig rig test process(es) running (runitem?): nothing started"; exit 2; }
grep -q "v413" "$EXE" || { result guard FAIL "$EXE has no v413 text: build with v412b + v413 first"; exit 2; }
[ -f diag/twin/numcheck.py ] || { result guard FAIL "diag/twin/numcheck.py missing"; exit 2; }

# ---- baseline (before any game restarts: the logs of the previous run)
BA="${BASE_A:-diag/twin/runnum_base_A.txt}"; BB="${BASE_B:-diag/twin/runnum_base_B.txt}"
[ -n "$BASE_A" ] || cp -f "$LOGA" "$BA" 2>/dev/null
[ -n "$BASE_B" ] || cp -f "$LOGB" "$BB" 2>/dev/null
baseA=$(python diag/twin/numcheck.py "$BA" | grep -o "delta=[0-9-]*" | cut -d= -f2)
baseB=$(python diag/twin/numcheck.py "$BB" | grep -o "delta=[0-9-]*" | cut -d= -f2)
say "baseline numbering time: A ${baseA:--} s, B ${baseB:--} s ($BA, $BB)"

kv() { echo "$1" | grep -o "$2=[^ ]*" | cut -d= -f2; }

one_run() {   # one_run TAG FORCE(empty = none) -> sets NA NB YIELD (and RESULT lines)
  local tag=$1 force=$2
  stop_hc
  STARTED=1
  rm -f diag/twin/go.log
  if [ -n "$force" ]; then
    LAST_FORCED=1
    (export DUSK_NUMBER_FORCE_B=$force; DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 TWIN_GAMES=AB nohup bash diag/twin/go_hub.sh > diag/twin/go.log 2>&1 &)
  else
    LAST_FORCED=0
    (unset DUSK_NUMBER_FORCE_B; DUSK_WAIT_LONGPOLL=3600 TWIN_ARGS=--no-watch TWIN_P2P_FORMAT=self TO_MATCH_ONE_PRESS=1 TWIN_GAMES=AB nohup bash diag/twin/go_hub.sh > diag/twin/go.log 2>&1 &)
  fi
  local n=0
  until grep -q "hub-ready" diag/twin/go.log || [ $n -ge 45 ]; do sleep 8; n=$((n+1)); done
  grep -q "hub-ready" diag/twin/go.log || { result ${tag}_hub FAIL "hub not ready after 6 min (go.log)"; return 1; }
  DUSK_WAIT_LONGPOLL=3600 TO_MATCH_ONE_PRESS=1 TWIN_GAMES=AB timeout 300 python diag/twin/to_match2.py 2>&1 | tail -1
  n=0
  until { timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round 1"; } && \
        { timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -q "step 6 round 1"; } || [ $n -ge 25 ]; do
    sleep 8; n=$((n+1))
  done
  sleep 15
  cp -f "$LOGA" diag/twin/runnum_${tag}_A.txt; cp -f "$LOGB" diag/twin/runnum_${tag}_B.txt
  local ca cb
  ca=$(python diag/twin/numcheck.py diag/twin/runnum_${tag}_A.txt); cb=$(python diag/twin/numcheck.py diag/twin/runnum_${tag}_B.txt)
  say "$tag A: $ca"; say "$tag B: $cb"
  NA=$(kv "$ca" no); NB=$(kv "$cb" no)
  local da db dupA dupB fA fB
  da=$(kv "$ca" deliv); db=$(kv "$cb" deliv); dupA=$(kv "$ca" dup); dupB=$(kv "$cb" dup)
  YIELD=$(( $(kv "$ca" yield) + $(kv "$cb" yield) ))
  fA=$(kv "$ca" force); fB=$(kv "$cb" force)
  local nums="A no $NA (delivered $da), B no $NB (delivered $db), DUPLICATE lines A $dupA B $dupB"
  if [ "$da" = "$NA" ] && [ "$db" = "$NB" ] && [ "$dupA" = 0 ] && [ "$dupB" = 0 ] && \
     { [ "$NA$NB" = 12 ] || [ "$NA$NB" = 21 ]; }; then
    result ${tag}_numbers PASS "$nums"
  else
    result ${tag}_numbers FAIL "$nums"
  fi
  # Phase I and part_flag (virtue.py rank entries: "entry k no N ... state XXXXXXXX")
  local mA mB v good all
  mA=$(timeout 40 python diag/twin/mapsys.py A 2>/dev/null | grep -c "step 6 round 1")
  mB=$(timeout 40 python diag/twin/mapsys.py B 2>/dev/null | grep -c "step 6 round 1")
  v=$(timeout 60 python diag/twin/virtue.py AB 2>&1); echo "$v" > diag/twin/runnum_${tag}_virtue.txt
  all=$(echo "$v" | grep -c "^  entry [0-9]* no ")
  good=$(echo "$v" | grep "^  entry [0-9]* no " | grep -c "state 01010000")
  if [ "$mA" -ge 1 ] && [ "$mB" -ge 1 ] && [ "$all" = 4 ] && [ "$good" = 4 ]; then
    result ${tag}_phase1 PASS "both games at step 6 round 1; 4 of 4 rank entries state 01010000"
  else
    result ${tag}_phase1 FAIL "step 6 round 1: A $mA B $mB; rank entries $all, state 01010000 $good (runnum_${tag}_virtue.txt)"
  fi
  if [ -z "$force" ]; then
    local vA vB
    vA=$(kv "$ca" v413); vB=$(kv "$cb" v413)
    if [ "$vA" = 0 ] && [ "$vB" = 0 ]; then result ${tag}_no_v413 PASS "no (v413) line on A or B"
    else result ${tag}_no_v413 FAIL "(v413) lines: A $vA, B $vB (the two-player path must not act)"; fi
    local tA tB ok=1 why=""
    tA=$(kv "$ca" delta); tB=$(kv "$cb" delta)
    for p in "A $tA $baseA" "B $tB $baseB"; do
      set -- $p
      if [ "$2" = "-" ] || [ -z "$3" ] || [ "$3" = "-" ]; then ok=2; why="$why $1: now ${2:--} s, baseline ${3:--} s (unreadable);"
      elif [ "$2" -gt $(( $3 + 2 )) ]; then ok=0; why="$why $1: now $2 s > baseline $3 s + 2;"
      else why="$why $1: now $2 s, baseline $3 s;"; fi
    done
    case $ok in
      1) result ${tag}_timing PASS "session state 2/3 -> message 4 armed:$why" ;;
      0) result ${tag}_timing FAIL "slower than today:$why" ;;
      *) result ${tag}_timing "NOT JUDGED" "$why" ;;
    esac
  else
    if [ "$fB" -lt 1 ] || [ "$fA" != 0 ]; then
      result ${tag}_switch FAIL "DUSK_NUMBER_FORCE_B line: A $fA (must be 0), B $fB (must be 1)"
    fi
    if [ "$YIELD" = 1 ]; then result ${tag}_yield PASS "one game logged \"taking N instead (v413)\"; final A $NA B $NB"
    elif [ "$YIELD" = 0 ]; then result ${tag}_yield "NOT JUDGED" "no yield: B proposed $force and kept it (its member id is the lower one?)"
    else result ${tag}_yield FAIL "$YIELD yield lines (expected exactly 1)"; fi
  fi
  return 0
}

say "RUN 1: plain (no switch)"
one_run plain ""
say "RUN 2: DUSK_NUMBER_FORCE_B=1 on B"
one_run force1 1
if [ "${YIELD:-0}" = 0 ]; then
  say "RUN 3: no yield in run 2: DUSK_NUMBER_FORCE_B=2 on B (A should yield to 1)"
  one_run force2 2
fi
stop_hc
bash diag/twin/alive.sh | tail -3
say "runnum done: see $LOG"
