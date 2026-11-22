"""Rig test: wait for Trespasser KEY to finish, stop the fight loops, snapshot rewards on both games with the Power
dialog open, press A on both, diff.  usage: python diag/twin/pickwait.py 0x5f9"""
import subprocess
import sys
import time

sys.path.insert(0, 'diag/twin')
import tctl

key = sys.argv[1].lower().replace('0x', '').zfill(4)
PY = sys.executable
SHOT = '<WORKSPACE>/diag/twin/%s_pw%d.png'


def run(args, t=60):
    try:
        return subprocess.run([PY] + args, capture_output=True, text=True, timeout=t).stdout
    except subprocess.TimeoutExpired:
        return ''


def step9():
    out = run(['diag/twin/trespassers.py', 'A'], 30).splitlines()
    for i, l in enumerate(out):
        if 'id 0x%s' % key in l:
            return 'step 9' in l
    return False


t0 = time.time()
while not step9() and time.time() - t0 < 2400:
    time.sleep(8)
print('finished after %.0f s' % (time.time() - t0))
subprocess.run(['powershell', '-NoProfile', '-Command',
                "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'bash.exe') "
                "-and $_.CommandLine -like '*fightfoe*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"])
for i in range(12):
    out = run(['diag/twin/powers.py', 'AB', 'noroses'])
    n = [l for l in out.splitlines() if 'select dialog list' in l]
    if n and all(' 0 entries' not in l for l in n):
        break
    time.sleep(4)
print('dialog lines', [l.strip()[-40:] for l in n])
for w in 'AB':
    tctl.call(w, {'method': 'screenshot', 'params': {'height': 480}}, SHOT % (w, 1))
    print(w, 'snap', run(['diag/twin/rewards.py', w, 'snap', 'P' + w]).strip().splitlines()[-1:])
before = [l for l in run(['diag/twin/powers.py', 'AB', 'noroses']).splitlines() if 'Power ids' in l or 'owned Powers' in l]
for w in 'AB':
    tctl.call(w, {'method': 'input_sequence', 'params': {'steps': [{'buttons': ['A'], 'frames': 6},
                                                                   {'buttons': [], 'frames': 30}]}})
time.sleep(6)
for w in 'AB':
    tctl.call(w, {'method': 'screenshot', 'params': {'height': 480}}, SHOT % (w, 2))
    print(w, 'DIFF:')
    print(run(['diag/twin/rewards.py', w, 'diff', 'P' + w])[-1500:])
after = [l for l in run(['diag/twin/powers.py', 'AB', 'noroses']).splitlines() if 'Power ids' in l or 'owned Powers' in l]
print('BEFORE'); print('\n'.join(l[:200] for l in before))
print('AFTER'); print('\n'.join(l[:200] for l in after))
