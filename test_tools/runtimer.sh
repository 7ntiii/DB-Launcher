#!/bin/bash
# runtimer.sh: two-game check of "the host has no match timer in the final" (timer_notes.md section 4). Rig only.
cd <WORKSPACE>
O=diag/net/timer2g; mkdir -p $O
say() { echo "[$(date +%T)] $*"; }
(nohup bash diag/twin/go.sh > diag/twin/go.log 2>&1 &)
n=0; until grep -qE "nav done|FAILED" diag/twin/go.log || [ $n -ge 70 ]; do sleep 8; n=$((n+1)); done
say "$(tail -1 diag/twin/go.log)"
wait_round() { n=0; until timeout 30 python diag/twin/mapsys.py A 2>/dev/null | grep -q "step 6 round $1" || [ $n -ge 40 ]; do sleep 5; n=$((n+1)); done; }
snap() { say "== $1"; timeout 40 python diag/twin/timer_gates.py AB diff 2>&1 | tail -8; for g in A B; do python - "$g" "$1" <<'PY'
import sys, os
sys.path.insert(0, 'diag/twin')
import screen
who, name = sys.argv[1], sys.argv[2]
out = os.path.abspath('diag/net/timer2g/%s_%s.png' % (who, name))
screen.call(who, {'method': 'screenshot', 'params': {'height': 720}}, out)
print(out)
PY
done; }
wait_round 1; sleep 20; snap phase1
for r in 2 3 4; do timeout 40 python diag/twin/clock.py 5 AB >/dev/null 2>&1; wait_round $r; sleep 20; [ $r = 2 ] && snap phase2; done
snap final
bash diag/twin/alive.sh | tail -3
taskkill //F //IM lichii.exe >/dev/null 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -eq 'bash.exe' -and \$_.CommandLine -match 'go\.sh' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }"
say "runtimer done"
