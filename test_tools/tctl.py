"""ctl for twin games: python diag/twin/tctl.py A|B shot NAME | press BTN.. | status | wait N"""
import json, subprocess, sys
from pathlib import Path
WS = Path(__file__).resolve().parents[2]
AD = WS / 'src' / 'lichii' / 'tools' / 'nx2' / 'debug_mcp.py'
PORT = {'A': 6545, 'B': 6546, 'C': 6547, 'D': 6548}
GAMES = __import__('os').environ.get('TWIN_GAMES', 'AB')   # which twin games run: AB or ABC
def call(who, req, out=None):
    c = [sys.executable, '-I', str(AD), '--server', f'127.0.0.1:{PORT[who]}', '--call', json.dumps(req)]
    if out: c += ['--out', str(out)]
    r = subprocess.run(c, capture_output=True, text=True, timeout=120)
    return r.stdout.strip() or r.stderr.strip()
if __name__ == '__main__':
    who, cmd, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    if cmd == 'shot':
        out = WS / 'diag' / 'twin' / f'{who}_{rest[0] if rest else "shot"}.png'
        print(call(who, {'method': 'screenshot', 'params': {'height': 480}}, out))
    elif cmd == 'press':
        print(call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': rest, 'frames': 6}, {'frames': 90}]}}))
    elif cmd == 'wait':
        print(call(who, {'method': 'input_sequence', 'params': {'steps': [{'frames': int(rest[0])}]}}))
    elif cmd == 'status':
        print(call(who, {'method': 'status'}))
