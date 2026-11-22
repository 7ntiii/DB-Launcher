#!/bin/bash
# prints for A and B the age (s) of the last NIFM poll line in the emulator log: > 6 s = that game is frozen
for w in A B; do
  f="$APPDATA/eden/log/eden_log.txt"; [ $w = B ] && f=<WORKSPACE>/diag/twin/userB/log/eden_log.txt
  python - "$f" $w <<'PY'
import re,sys
t=[float(m.group(1)) for l in open(sys.argv[1],encoding='utf-8',errors='replace') for m in [re.match(r'\[\s*([0-9.]+)\]',l)] if m]
n=[float(re.match(r'\[\s*([0-9.]+)\]',l).group(1)) for l in open(sys.argv[1],encoding='utf-8',errors='replace') if 'GetCurrentIpAddress' in l]
print(sys.argv[2],'last log %.0f s, last game poll %.0f s, poll age %.0f s'%(t[-1],n[-1] if n else -1,t[-1]-(n[-1] if n else 0)))
PY
done
powershell -NoProfile -Command "Get-PSDrive C | ForEach-Object { 'C: free GB ' + [math]::Round(\$_.Free/1GB,1) }"
