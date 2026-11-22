"""Does the movement delay follow a step of one game's guest counter? Run when both twin games are in
the battle: python diag/twin/tick_test.py  -> lag both ways for tick offsets of A and B."""
import subprocess, sys, time
sys.path.insert(0, 'diag/twin')
import tctl
def lag(m):
    r = subprocess.run([sys.executable, 'diag/twin/lag.py', m, '4'], capture_output=True, text=True).stdout
    d = [l.split('delay ')[1] for l in r.splitlines() if 'delay ' in l]
    return d[0] if d else '?'
def step(who, ms):
    r = tctl.call(who, {'method': 'perf_flag', 'params': {'name': 'tick_offset_ms', 'value': ms}})
    return 'error' in r.lower() and r[:120] or 'ok'
for who, ms in [('A', 0), ('B', 400), ('B', -400), ('B', 0), ('A', 400), ('A', -400), ('A', 0)]:
    res = step(who, ms); time.sleep(4)
    print(time.strftime('%H:%M:%S'), f'{who} tick offset {ms:+5d} ms ({res}):  A->B {lag("A")}   B->A {lag("B")}', flush=True)
    time.sleep(3)
