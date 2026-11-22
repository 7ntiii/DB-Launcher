#!/bin/bash
# GUARD 2026-11-16: the user allows at most TWO games on this PC (a 4-game run froze it). Do not remove.
if [ "${USER_SAID_MORE_THAN_TWO_GAMES:-0}" != "1" ]; then echo "REFUSED: more than two games on this PC is not allowed (user rule 2026-11-16)"; exit 9; fi
# run4.sh: the 4-game programme (rows 3 and 4: more players and the culls; row 23: Bloodbound with two pairs),
# hands-free from a cold start. Written 2026-11-17 as static work; never run. TEST RIG ONLY.
# Notes, expected values and the described twin.py / go4.sh diffs: diag/net/run4_notes.md.
#
#   bash diag/twin/run4.sh               programme A (Standard) then programme B (Bloodbound), one cold start each
#   RUN4_PROG=A bash diag/twin/run4.sh   only A;   RUN4_PROG=B: only B
#   RUN4_GAMES=ABC bash diag/twin/run4.sh   3-game proof of go4b.sh / twin4.py and the memory checks (A only)
# The cold start uses diag/twin/go4b.sh (= go4.sh + twin4.py, the copies with per-game caps / lazy commit); the
# originals go4.sh and twin.py are not used. (The text below about "twin.py" means twin4.py.)
# Other switches: RUN4_FORCE=1 starts even when a prerequisite check fails (exe without lazy commit, twin.py
# without per-game texture caps); RUN4_NEED_GB (default 88) commit headroom; RUN4_HOST_LOW=0 skips the Phase II
# kills by B, C, D that try to make the host the lowest (the host-leaves case of the Phase III cut);
# RUN_KEEP=1 leaves the rig running at the end. Log diag/twin/run4.log, rows also in diag/twin/run4_results.txt.
#
# Environment set for the cold start (go4.sh -> twin.py):
#   TWIN_GAMES=ABCD DUSK_MATCH_MIN=4 GO4_PHASE1=1 GO4_PHASE1_WAIT=540 GO4_STAGGER=60 (one hub load at a time,
#   more time for textures); TWIN_LAZY=1 and TWIN_LAZY_GAMES=CD (lazy commit for C and D only);
#   texture caps TWIN_TC_MAX_<W> / TWIN_TC_EXP_<W> in MiB: A 3584/2688, B 3584/2688, C 2048/1536, D 1536/1152
#   (lazy_commit_notes "Video memory": 3.5 + 3.5 + 2 + 1.5 GiB caches + 2 GiB overhead = about 12.5 of 12 GiB, so
#   C and D also run at 0.5x: resolution_setup=1 in userC / userD qt-config.ini, go4.sh logs it).
#   IMPORTANT: today's twin.py drops every EDEN_NX2_* variable (emu_env) and has no TWIN_TC_* / TWIN_LAZY: the
#   variables above only work after the described twin.py diff (run4_notes.md 2). The precheck refuses otherwise.
#   Programme B adds GO4_RULE=4 (set_rule.py writes the Bloodbound menu mask in the hub on every game).
#
# Precheck (nothing is started when one fails):
#   - the user's own game / launcher is not running, and no rig lichii.exe is running (another run);
#   - C: free >= 80 GB (PowerShell Get-PSDrive C);
#   - commit headroom >= RUN4_NEED_GB: run4_check.py commit = free commit now (Win32_OperatingSystem
#     FreeVirtualMemory) + what the paging file can still grow (system-managed only: up to 3 x RAM, but never
#     past C: free - 10 GB). Need 88 GB = 2 x 26 (A, B full commit) + 2 x 18 (C, D lazy) (lazy_commit_notes table);
#   - the exe has lazy commit (the string "lazy commit on first touch" in lichii.exe) and twin.py has TWIN_TC_MAX_.
# Health between steps (games still in the match only): run_lib.sh health (alive.sh + userC / userD poll age,
#   pids, C: >= 10 GB) plus run4_check.py vram: fatal emulator-log lines on any game (device lost, failed image,
#   render target unbacked, "Lazy commit failed", 1455) or commit headroom < 2 GB stop the run cleanly; the
#   live per-game video memory (GPU Process Memory counters, as go4.sh's vram lines) is printed every time.
#   A 4th game that cannot get memory shows as go4 "FAILED: game D not in the hub", a gone process, or one of
#   those log lines: each ends the run with the rows left SKIP.
# Rules (as run3.sh): every step first stops stray hold_clock.py; no step waits more than 10 minutes (go4: no new
# go4 output line for 600 s; 1500 s in all for 4 boots + 4 hub loads); at the end (and between A and B) only the
# rig's processes are stopped. regress_small.py, twin.py and go4.sh are only called.
#
# Rows (one PASS / FAIL / SKIP each):
#   A: aStart (cold start), aLazy (C, D log lazy commit; A, B full), aCut2 (after Phase II: nobody cut with 4
#      players, same F1 list on all 4), aCut3 (after Phase III: exactly one cut, the same on every game: F1 list,
#      H1 / F4 lines, the culled game out of the final, phase entries equal), aFinal (final over: result ranks and
#      placement line equal on the 3 finalists), aVram (no fatal VRAM line in the whole match), aLog (cutcheck.py)
#   B: bStart, bPairs1..4 (pairs.py ABCD each phase: rule 2, pairs equal), bCut2 / bCut3 (nobody cut: 2 pairs),
#      bKillC / bKillD (two real deaths each by A), bFinal (bbfinal_notes 5.3 + assist_v396_notes 4b: entries,
#      ranks 255, place 1 / 2, same placement line), bVram, bLog (cutcheck.py)
# Exit 0 = no FAIL, 1 = a FAIL, 2 = stopped early.
#
# 2026-11-16 additions (helper 3) for tonight's cut fix (cutauth_notes.md 4, assist_v400_notes.md, audit_v401_notes.md
# 2.4, spectate_notes.md 9); build: CUTAUTH group + assist v401c + v402:
#   after each cut (rows xAuth2 / xAuth3, run4_check.py cutlog, on EVERY game): the CUTAUTH lines ("our phase end
#      waits", "list is in the mailbox (clock held T s)", "cut here X, cut by the authority X: same"), the
#      authority's V400-1 answer line and send count, the F1 verdict, the mailbox (key + rank bytes), and that no
#      guest's phase end waited more than RUN4_HOLD_MAX (1.5 s; programme C RUN4_HOLD_MAX_SIM 3.5 s); then
#      cutcheck.py with its health section on all four logs (printed, not a row).
#   Standard final (rows xOut, xFinal): A kills one finalist twice -> that player is at his result screen, the
#      others still play the final, nobody ran it down early; then A kills the second -> the final ends; result
#      ranks equal on the finalists, the "final placement" line equal on all four games, rank order killer,
#      second victim, first victim. (Before: the final clock was simply cut.)
#   Bloodbound final: after C's two deaths row bOn (A, B, D still play the final); D's deaths end it (bFinal).
#   Programme C (optional, RUN4_PROG=C or ABC): programme A again with the network simulator on games B and D
#      (TWIN_NET_SIM_B / TWIN_NET_SIM_D = RUN4_NETSIM, default 20,10,1,45,2000: 20 ms, 10 ms jitter, 1 % loss, a 2-s
#      stall every 45 s; twin4.py already passes TWIN_NET_SIM_<W> for every game, D included). The Phase II and III
#      cuts are aimed so the phase ends about 1 s into a stall (unix time % 45 == 40 at the clock cut). Rows cStart
#      cSim (NET SIM active on B and D only) cCut2 cAuth2 cCut3 cAuth3 cOut cFinal cVram cLog. Expected:
#      "same" on every guest, more than one V400-1 send, holds up to ~3 s. Programmes A and B run without any
#      simulator (every TWIN_NET_SIM_* is removed for them).

G=${RUN4_GAMES:-ABCD}
case "$G" in ABCD|ABC) ;; *) echo "RUN4_GAMES=$G: only ABCD or ABC"; exit 2;; esac
# 3-game mode (RUN4_GAMES=ABC): proves go4b.sh / twin4.py and the memory checks on the known-good 3 games first.
# Programme A only (Bloodbound with 3 is played as Standard), nobody is cut (top 3 kept), C is the lazy game,
# commit need 2 x 26 + 18 = 70 GB.
if [ "$G" = ABC ]; then PROG=${RUN4_PROG:-A}; NEED_DEF=70; CUT3=0; else PROG=${RUN4_PROG:-AB}; NEED_DEF=88; CUT3=1; fi
case "$G$PROG" in ABC*B*) echo "programme B needs four games (two pairs)"; exit 2;; esac
case "$G$PROG" in ABC*C*) echo "programme C needs four games (CUTAUTH acts with 4+ entries only)"; exit 2;; esac
RUN_NAME=run4
ROWS_A="aStart aLazy aCut2 aAuth2 aCut3 aAuth3 aOut aFinal aVram aLog"
ROWS_B="bStart bPairs1 bPairs2 bCut2 bAuth2 bPairs3 bCut3 bAuth3 bPairs4 bKillC bOn bKillD bFinal bVram bLog"
ROWS_C="cStart cSim cCut2 cAuth2 cCut3 cAuth3 cOut cFinal cVram cLog"
ROWS="pre $ROWS_A $ROWS_B $ROWS_C"
source <WORKSPACE>/diag/twin/run_lib.sh
for k in $ROWS; do RR[$k]="SKIP not reached"; done
case "$PROG" in *A*) ;; *) for k in $ROWS_A; do RR[$k]="SKIP programme A not chosen"; done;; esac
case "$PROG" in *B*) ;; *) for k in $ROWS_B; do RR[$k]="SKIP programme B not chosen"; done;; esac
case "$PROG" in *C*) ;; *) for k in $ROWS_C; do RR[$k]="SKIP programme C not chosen (RUN4_PROG=C or ABC)"; done;; esac
NETSIM=${RUN4_NETSIM:-20,10,1,45,2000}
HOLD_MAX=${RUN4_HOLD_MAX:-1.5}
SIM_ON=          # set while programme C runs: start_prog passes TWIN_NET_SIM_B / _D, cuts are aimed at a stall
R4() { PY "$1" diag/twin/run4_check.py "${@:2}"; }
# run4_dry_notes.md fix 1: run_lib's cut_phase calls clock.py, which resolves and writes one game after the other
# (seconds between A and D). clock4.py resolves all first, then writes back to back, the cut authority first.
cut_phase() {
    hold_off || say "warning: a holder may still reset the clock"
    say "cut: $(PY 60 diag/twin/clock4.py 5 "$G" | tr '\n' ' ')"
}

# ------------------------------------------------------------------ 0. precheck
precheck
RIG=$(powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='lichii.exe'\" | Where-Object { \$_.ExecutablePath -match 'DuskbloodsWorkspace.build.lichii.bin' }).Count" 2>/dev/null | tr -d '\r')
[ "${RIG:-0}" = 0 ] || { row pre FAIL "a rig game is running ($RIG lichii.exe of build/lichii/bin): another run?"; finish 2 "rig busy: nothing started"; }
FREE=$(powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free/1GB,1)" 2>/dev/null | tr -d '\r')
CM=$(R4 120 commit "${RUN4_NEED_GB:-$NEED_DEF}" | grep '^COMMIT' | tail -1)
PR=$(R4 60 prereq | grep '^PREREQ' | tail -1)
say "C: free $FREE GB | $CM | $PR"
BAD=
python -c "import sys; sys.exit(0 if float('${FREE:-0}') >= 80 else 1)" 2>/dev/null || BAD="$BAD C: free ${FREE:-?} GB < 80;"
case "$CM" in "COMMIT ok"*) ;; *) BAD="$BAD commit headroom too small or unreadable;";; esac
# run4_dry_notes.md fix 3: A (0 s) and B (+20 s) take their 16-17.6 GB backing section in ONE charge each; the
# paging file grows only after a request failed or is close to the limit, so this needs free commit NOW, not
# headroom. A failed charge = "Failed to allocate 16000 MiB of backing memory": that game runs without fastmem.
FC=$(echo "$CM" | sed -n 's/.* free \([0-9.]*\) GB .*/\1/p')
python -c "import sys; sys.exit(0 if float('${FC:-0}') >= float('${RUN4_FREE_GB:-40}') else 1)" 2>/dev/null ||
    BAD="$BAD free commit now ${FC:-?} GB < ${RUN4_FREE_GB:-40} (A and B full commit at boot: fastmem);"
[ "$G" = ABCD ] && case "$PR" in *userD=True*) ;; *) BAD="$BAD diag/twin/userD/config missing;";; esac
PRB=
case "$PR" in *exe_lazy=True*) ;; *) PRB="$PRB exe has no lazy commit (build lazy_commit_b.diff);";; esac
case "$PR" in *twin_caps=True*) ;; *) PRB="$PRB twin4.py missing or without TWIN_TC_MAX_ (run4_notes.md 2);";; esac
if [ -n "$BAD" ] || { [ -n "$PRB" ] && [ "$RUN4_FORCE" != 1 ]; }; then
    row pre FAIL "precheck:$BAD$PRB | $CM | $PR"
    finish 2 "precheck failed: nothing started"
fi
row pre PASS "precheck${PRB:+ (RUN4_FORCE=1 despite:$PRB)} | C: free $FREE GB | $CM | $PR"

export DUSK_MATCH_MIN=${#G} GO4_PHASE1=1 GO4_PHASE1_WAIT=540 GO4_STAGGER=60
export TWIN_LAZY=1 TWIN_LAZY_GAMES=CD
export TWIN_TC_MAX_A=3584 TWIN_TC_EXP_A=2688 TWIN_TC_MAX_B=3584 TWIN_TC_EXP_B=2688
# run4_dry_notes / lazy_perf_notes 7: C and D at 2048 / 1536 thrashed the texture cache after their hub load
# (hub working set about 2.7 GiB, as A and B show): every game gets 3584 / 2688 (card total about 10 GiB of 12).
export TWIN_TC_MAX_C=3584 TWIN_TC_EXP_C=2688 TWIN_TC_MAX_D=3584 TWIN_TC_EXP_D=2688

# ------------------------------------------------------------------ helpers
LIVE_G=$G
health4() {   # health of the games still in the match + video memory / commit
    local g0=$G v
    G=$LIVE_G
    health "$1"
    G=$g0
    v=$(R4 150 vram "$LIVE_G" | grep '^VRAM' | tail -1)
    say "vram ($1): $(echo "$v" | cut -c1-500)"
    case "$v" in "VRAM STOP"*) finish 2 "video memory / commit ($1): $(echo "$v" | cut -c1-300)";; esac
}
step4() { say "=== step: $1"; hc_stray; health4 "$1"; }
live_count() {   # live_count ROUND : number of games in step 6 of ROUND
    steps | tr ' ' '\n' | paste - - - | awk -v r="$1" '$2 == 6 && $3 == r' | wc -l
}
wait_live() {   # wait_live ROUND MIN : at least MIN games in step 6 of ROUND, at most STEP_MAX s
    local t0 h n
    t0=$(date +%s); h=$t0
    while :; do
        n=$(live_count "$1")
        [ "$n" -ge "$2" ] && { say "round $1: $n game(s) in play ($(steps))"; sleep 10; return 0; }
        [ $(( $(date +%s) - t0 )) -ge $STEP_MAX ] && { say "round $1: only $n game(s) in play after $STEP_MAX s ($(steps))"; return 1; }
        [ $(( $(date +%s) - h )) -ge 60 ] && { health4 "waiting for round $1"; h=$(date +%s); }
        sleep 10
    done
}
wait_over() {   # wait_over GAMES : none of GAMES in step 6 of round 4 any more (final over), at most STEP_MAX s
    local t0 s w busy
    t0=$(date +%s)
    while :; do
        s=$(PY 40 diag/twin/run3_check.py steps "$1" | tail -1 | tr -d '\r')
        busy=$(echo "$s" | tr ' ' '\n' | paste - - - | awk '$2 == 6 && $3 == 4' | wc -l)
        [ "$busy" = 0 ] && { say "final over on $1 ($s)"; return 0; }
        [ $(( $(date +%s) - t0 )) -ge $STEP_MAX ] && { say "final not over after $STEP_MAX s ($s)"; return 1; }
        sleep 10
    done
}
check_row() {   # check_row KEY TAG OUTPUT : the last "<TAG> STATUS text" line of a run4_check.py mode -> ROW
    local l
    l=$(echo "$3" | grep "^$2 " | tail -1)
    if [ -z "$l" ]; then
        row "$1" FAIL "$2: no result line (timeout or crash): $(echo "$3" | tail -2 | tr '\n' ' ' | cut -c1-200)"
    else
        row "$1" "$(echo "$l" | awk '{print $2}')" "$2: $(echo "$l" | cut -d' ' -f3-)"
    fi
}
vram_row() {   # vram_row KEY : fatal VRAM lines over the whole match (all four logs)
    local v
    v=$(R4 150 vram "$G" | grep '^VRAM' | tail -1)
    case "$v" in
        "VRAM ok"*) row "$1" PASS "$(echo "$v" | cut -c10-400)";;
        "VRAM STOP"*) row "$1" FAIL "$(echo "$v" | cut -c11-400)";;
        *) row "$1" SKIP "vram check gave no line";;
    esac
}
# run4_dry_notes.md fix 2: to_hub2b.py's output goes to go4_hub.txt, not to this file, and one game may take
# 300 s (debug server) + 300 s (hub): the stall limit must lie past that, so go4b's own "FAILED: game X not in
# the hub" line (with the reason) arrives first.
WL_STALL=660; WL_TOTAL=2400   # run4_retry_notes 1: 4 hubs (up to 600 s each) + join + Phase I wait (540 s)
wait_go4() {   # wait_go4 FILE : 0 nav done, 1 FAILED line, 2 stall / total time-out / go4 gone
    local t0 tl n last=-1
    t0=$(date +%s); tl=$t0
    while :; do
        grep -q '^nav done' "$1" 2>/dev/null && return 0
        grep -q '^FAILED:' "$1" 2>/dev/null && return 1
        n=$(wc -l < "$1" 2>/dev/null)
        if [ "${n:-0}" != "$last" ]; then last=${n:-0}; tl=$(date +%s); say "  go4: $(tail -1 "$1" | cut -c1-150)"; fi
        [ $(( $(date +%s) - tl )) -ge $WL_STALL ] && return 2
        [ $(( $(date +%s) - t0 )) -ge $WL_TOTAL ] && return 2
        kill -0 "$GO_PID" 2>/dev/null || { grep -q '^nav done' "$1" && return 0; return 2; }
        sleep 10
    done
}
start_prog() {   # start_prog a|b RULE : stop the previous programme's rig, cold start ABCD
    local key=$1 gl=diag/twin/run4_go4_$1.txt rc
    if [ -n "$GO_PID" ]; then
        say "end of the previous programme: rig processes stopped before the next cold start"
        hold_off
        PY 90 diag/twin/run3_check.py cleanup
        kill "$GO_PID" 2>/dev/null
        GO_PID=
        sleep 15
    fi
    LIVE_G=$G
    unset LASTLOG LASTT; declare -gA LASTLOG LASTT
    STARTED=1
    hold_off
    # Every inherited simulator variable is removed; programme C (SIM_ON=1) gives it to B and D only.
    local -a envs=(env -u TWIN_NET_SIM_A -u TWIN_NET_SIM_B -u TWIN_NET_SIM_C -u TWIN_NET_SIM_D
                   -u TWIN_NET_SIM_SEED_B -u TWIN_NET_SIM_SEED_D)
    [ "$SIM_ON" = 1 ] && envs+=("TWIN_NET_SIM_B=$NETSIM" "TWIN_NET_SIM_D=$NETSIM"
                                "TWIN_NET_SIM_SEED_B=${RUN4_NETSIM_SEED:-1}" "TWIN_NET_SIM_SEED_D=$(( ${RUN4_NETSIM_SEED:-1} + 1 ))")
    "${envs[@]}" GO4_RULE="$2" bash diag/twin/go4b.sh > "$gl" 2>&1 &
    GO_PID=$!
    say "go4b.sh started (pid $GO_PID, GO4_RULE='${2}'${SIM_ON:+, LICHII_NET_SIM=$NETSIM on B and D}), output $gl"
    wait_go4 "$gl"; rc=$?
    grep -E '^  vram ' "$gl" | tail -8
    case $rc in
        0) row "${key}Start" PASS "go4: $(grep '^nav done' "$gl" | tail -1) | $(grep '^server match:' "$gl" | tail -1 | cut -c1-160) | $(grep '^resolution:' "$gl" | tail -1)";;
        1) row "${key}Start" FAIL "go4: $(grep '^FAILED:' "$gl" | tail -1 | cut -c1-300) | $(grep -E '^  vram ' "$gl" | tail -2 | tr '\n' ' ' | cut -c1-300)"; return 1;;
        *) row "${key}Start" FAIL "go4: no nav done (stall $WL_STALL s / total $WL_TOTAL s): $(tail -1 "$gl" | cut -c1-200)"; return 1;;
    esac
    return 0
}
cut_and_check() {   # cut_and_check KEY ROUND KEEP EXPECT [teams] : read the cut of ROUND once the next phase plays
    local out want
    want=$(( ${#G} - $4 ))
    if wait_live $(( $2 + 1 )) "$want"; then
        out=$(R4 300 cuts "$2" "$3" "$4" "$G" $5)
        check_row "$1" CUT "$out"
        CUTNOS=$(echo "$out" | grep '^CUTNOS' | tail -1 | cut -d' ' -f2-)
    else
        out=$(R4 300 cuts "$2" "$3" "$4" "$G" $5)
        check_row "$1" CUT "$out"
        CUTNOS=$(echo "$out" | grep '^CUTNOS' | tail -1 | cut -d' ' -f2-)
        case "${RR[$1]}" in PASS*) RR[$1]="FAIL next phase not reached by $want game(s); ${RR[$1]}";; esac
    fi
    say "lives: $(PY 90 diag/twin/lives.py "$G" | tr '\n' ';' | cut -c1-600)"
    say "endgame: $(PY 90 diag/twin/endgame.py "$G" | grep -E 'step|entry|row' | tr '\n' ';' | cut -c1-700)"
}
set_live_from_cut() {   # LIVE_G = the games whose player number is not in CUTNOS
    local map w n
    map=$(R4 90 nos "$G" | tail -1 | tr -d '\r')
    LIVE_G=
    for w in $(echo "$G" | sed "s/./& /g"); do
        n=$(echo "$map" | tr ' ' '\n' | grep "^$w=" | cut -d= -f2)
        case " $CUTNOS " in *" $n "*) ;; *) LIVE_G="$LIVE_G$w";; esac
    done
    say "player numbers $map; cut: ${CUTNOS:-none}; games still playing: $LIVE_G"
}
logs_row() {   # logs_row KEY : cutcheck.py on the four dusk_lan.txt of this programme (copies in run4<x>_logs/)
    local rn=$RUN_NAME hb
    RUN_NAME=${rn}$2
    cutcheck_row "$1"
    # cutcheck.py's health section (link values per game; never a disagreement): printed, and its verdicts in the row
    sed -n '/=== health/,/disagreement(s) flagged/p' "diag/twin/${RUN_NAME}_cutcheck.txt" 2>/dev/null | grep -v 'flagged'
    hb=$(grep 'HEALTH ' "diag/twin/${RUN_NAME}_cutcheck.txt" 2>/dev/null | sed 's/^ *//' | tr '\n' ' ' | cut -c1-500)
    RR[$1]="${RR[$1]} | ${hb:-no health lines}"
    RUN_NAME=$rn
}
cc_snap() {   # cc_snap LABEL : cutcheck.py (+ health) on all four logs as they are now; printed only, never a row
    local args= w f cc
    for w in $(echo "$G" | sed 's/./& /g'); do
        if [ "$w" = A ]; then f="$(cygpath -m "$APPDATA")/eden/log/dusk_lan.txt"; else f="$(pwd -W)/diag/twin/user$w/log/dusk_lan.txt"; fi
        args="$args $w:$f"
    done
    # shellcheck disable=SC2086
    cc=$(PY 240 diag/twin/cutcheck.py $args --quiet)
    say "cutcheck ($1): $(echo "$cc" | grep 'disagreement(s) flagged' | tail -1) $(echo "$cc" | grep '!!' | head -3 | tr '\n' ' ' | cut -c1-300)"
    echo "$cc" | grep -E 'HEALTH |ping |"no side message"|"not heard|timer corrections|network clock moves|v400:' | sed 's/^/    /'
}
auth_row() {   # auth_row KEY ROUND [teams] : CUTAUTH / V400-1 lines, mailbox and phase-end wait on every game
    local hm=$HOLD_MAX
    [ "$SIM_ON" = 1 ] && hm=${RUN4_HOLD_MAX_SIM:-3.5}
    if [ ${#G} -lt 4 ]; then
        row "$1" SKIP "${#G} games: CUTAUTH is inert below 4 phase entries (cutauth_notes 3)"
        cc_snap "after the cut of round $2"
        return
    fi
    check_row "$1" AUTH "$(R4 180 cutlog "$2" "$G" "hold_max=$hm" $3)"
    cc_snap "after the cut of round $2"
}
aim_cut() {   # programme C: cut when unix time % period == period - 5: the phase ends (clock 5 s) about at a
              # stall start, so the guests' answers and last Virtue sends are held (netsim_notes "Stall")
    [ "$SIM_ON" = 1 ] || return 0
    local per t0
    per=$(echo "$NETSIM" | cut -d, -f4)
    [ -n "$per" ] && [ "$per" -gt 10 ] 2>/dev/null || return 0
    t0=$(date +%s)
    while [ $(( $(date +%s) % per )) != $(( per - 5 )) ]; do
        [ $(( $(date +%s) - t0 )) -gt $(( per + 5 )) ] && break
        sleep 0.5
    done
    say "cut aimed at the simulator's stall (unix time % $per = $(( $(date +%s) % per )))"
}
num_of() { echo "$1" | tr ' ' '\n' | grep "^$2=" | cut -d= -f2; }   # num_of MAP GAME
final_std() {   # final_std KEY : 3+ finalists: kill one twice (result screen, the others play on), then a second
    local k=$1 killer v1 v2 map o1 o2 o3 out ord
    killer=${LIVE_G:0:1}; v1=${LIVE_G: -1}; v2=${LIVE_G:1:1}
    if [ ${#LIVE_G} -lt 3 ]; then
        row "${k}Out" SKIP "only ${#LIVE_G} finalists ($LIVE_G): no 'out with others playing on' case"
        v2=$v1
    else
        sleep 20                                     # no teleport in the first ~20 s of the final
        out=$(R4 400 kill2 "$killer" "$v1")
        say "kill2 $killer -> $v1: $(echo "$out" | grep '^KILL2' | tail -1 | cut -c1-300)"
        case "$(echo "$out" | grep '^KILL2' | tail -1)" in
            "KILL2 PASS"*) sleep 15; check_row "${k}Out" OUT "$(R4 120 finalstate "$LIVE_G" "$v1")";;
            *) row "${k}Out" FAIL "kill2 $killer $v1: $(echo "$out" | grep '^KILL2' | tail -1 | cut -c1-300)"; return 1;;
        esac
        say "lives: $(PY 90 diag/twin/lives.py "$G" | tr '\n' ';' | cut -c1-600)"
        step4 "$k final, second elimination"
    fi
    out=$(R4 400 kill2 "$killer" "$v2")
    say "kill2 $killer -> $v2: $(echo "$out" | grep '^KILL2' | tail -1 | cut -c1-300)"
    wait_over "$LIVE_G"
    sleep 15
    map=$(R4 90 nos "$G" | tail -1 | tr -d '\r')
    o1=$(num_of "$map" "$killer"); o2=$(num_of "$map" "$v2"); o3=$(num_of "$map" "$v1")
    if [ "$v1" = "$v2" ]; then ord="$o1,$o2"; else ord="$o1,$o2,$o3"; fi
    check_row "${k}Final" FINAL "$(R4 120 final "$LIVE_G" "$G" "order=$ord")"
}

# ------------------------------------------------------------------ programme A: Standard, culls, final
cut_cut() {   # the phase cut; in programme C aimed at a simulator stall (no stray-holder pass in between)
    if [ "$SIM_ON" = 1 ]; then
        hold_off || say "warning: a holder may still reset the clock"
        aim_cut
        say "cut: $(PY 60 diag/twin/clock4.py 5 "$G" | tr '\n' ' ')"
    else
        cut_phase
    fi
}
prog_std() {   # prog_std a|c : Standard: culls, CUTAUTH after each cut, the final fought out (c = with the simulator)
    local k=$1 K
    K=$(echo "$1" | tr a-z A-Z)
    start_prog "$k" "" || return 1
    if [ "$k" = a ]; then
        LZO=$(R4 120 lazy "$G")
        say "commit mode: $(echo "$LZO" | grep '^MEMMODE' | tail -1)"
        LZ=$(echo "$LZO" | grep '^LAZY' | tail -1)
        WANT_LZ="LAZY A=full B=full C=lazy"; [ "$G" = ABCD ] && WANT_LZ="$WANT_LZ D=lazy"
        if [ "$LZ" = "$WANT_LZ" ]; then row aLazy PASS "$LZ"; else row aLazy FAIL "$LZ (want ${WANT_LZ#LAZY })"; fi
    else
        # the simulator on B and D only (A and C must have no NET SIM start line)
        local on off
        on=$(R4 60 netsim BD | grep '^NETSIM' | tail -1)
        off=$(R4 60 netsim AC | grep '^NETSIM' | tail -1)
        case "$on|$off" in
            "NETSIM PASS"*"|NETSIM FAIL not active on AC"*) row cSim PASS "B, D: ${on#NETSIM PASS } || A, C off: ${off#NETSIM FAIL }";;
            *) row cSim FAIL "B, D: $on || A, C: $off"; finish 2 "programme C: the simulator is not where it should be";;
        esac
    fi
    wait_round 1 || { finish 2 "programme $K: Phase I not on every game"; }
    sleep 25
    step4 "$K Phase I (health only)"
    step4 "$K cut Phase I"
    cut_phase
    if ! wait_round 2; then row "${k}Cut2" SKIP "Phase II not on every game ($(steps))"; return 1; fi
    sleep 25
    step4 "$K Phase II"
    if [ "${RUN4_HOST_LOW:-1}" = 1 ]; then
        for w in $(echo "${G#A}" | sed 's/./& /g'); do say "kills by $w: $(PY 200 diag/twin/kill.py $w 6 | tail -1 | cut -c1-150)"; done
    fi
    say "virtue: $(PY 120 diag/twin/virtue.py "$G" | grep -iE 'total|banked' | head -8 | tr '\n' ';' | cut -c1-500)"
    step4 "$K cut Phase II"
    cut_cut
    cut_and_check "${k}Cut2" 2 6 0
    auth_row "${k}Auth2" 2
    step4 "$K Phase III"
    sleep 20
    say "virtue: $(PY 120 diag/twin/virtue.py "$G" | grep -iE 'total|banked' | head -8 | tr '\n' ';' | cut -c1-500)"
    step4 "$K cut Phase III"
    cut_cut
    cut_and_check "${k}Cut3" 3 3 "$CUT3"
    auth_row "${k}Auth3" 3
    set_live_from_cut
    [ ${#LIVE_G} -ge 2 ] || { row "${k}Final" SKIP "fewer than 2 games in the final ($LIVE_G)"; return 0; }
    step4 "$K final"
    final_std "$k"
    say "endgame: $(PY 90 diag/twin/endgame.py "$G" | grep -E 'step|entry|row' | tr '\n' ';' | cut -c1-700)"
    vram_row "${k}Vram"
    logs_row "${k}Log" "$K"
}
prog_a() { prog_std a; }
prog_c() { SIM_ON=1; prog_std c; SIM_ON=; }

# ------------------------------------------------------------------ programme B: Bloodbound, two pairs
pairs_row() { check_row "$1" PAIRS "$(R4 150 pairs ABCD)"; }
prog_b() {
    start_prog b 4 || return 1
    wait_round 1 || { finish 2 "programme B: Phase I not on every game"; }
    sleep 25
    step4 "B Phase I"
    pairs_row bPairs1
    step4 "B cut Phase I"
    cut_phase
    if ! wait_round 2; then row bPairs2 SKIP "Phase II not on every game ($(steps))"; return 1; fi
    sleep 25
    step4 "B Phase II"
    pairs_row bPairs2
    step4 "B cut Phase II"
    cut_phase
    cut_and_check bCut2 2 6 0 teams
    auth_row bAuth2 2 teams
    step4 "B Phase III"
    pairs_row bPairs3
    step4 "B cut Phase III"
    cut_phase
    cut_and_check bCut3 3 3 0 teams
    auth_row bAuth3 3 teams
    step4 "B final"
    pairs_row bPairs4
    sleep 20                                         # no teleport in the first ~20 s of the final
    check_row bKillC KILL2 "$(R4 400 kill2 A C)"
    say "lives after C: $(PY 90 diag/twin/lives.py "$G" | tr '\n' ';' | cut -c1-600)"
    sleep 10
    check_row bOn ON "$(R4 90 finalon ABD)"        # C's partner D lives: the final must go on for A, B, D
    step4 "B final, second pair member"
    check_row bKillD KILL2 "$(R4 400 kill2 A D)"
    say "lives after D: $(PY 90 diag/twin/lives.py "$G" | tr '\n' ';' | cut -c1-600)"
    wait_over ABCD
    sleep 10
    check_row bFinal BBFINAL "$(R4 120 bbfinal ABCD)"
    say "endgame: $(PY 90 diag/twin/endgame.py "$G" | grep -E 'step|entry|row' | tr '\n' ';' | cut -c1-700)"
    vram_row bVram
    logs_row bLog B
}

case "$PROG" in *A*) prog_a;; esac
case "$PROG" in *B*) prog_b;; esac
case "$PROG" in *C*) prog_c;; esac
finish 0
