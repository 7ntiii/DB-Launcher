"""Flicker hunt at the user's spot (handoff 1 section 8.9l): python diag/twin/flick.py A [SECONDS=60] [goto]
With "goto": puts the player at (301.17, -33.03, 433.87) yaw -0.297 and resets the camera behind it.
Then takes small screenshots as fast as the debug server gives them over one kept-open connection,
and reports frames whose upper-left region (the foggy cliff) differs from the median; those frames
and their neighbours are kept in diag/twin/flick/."""
import base64
import io
import os
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from dbg import Dbg
from PIL import Image

who = sys.argv[1]
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60
g = Dbg(who)
if 'goto' in sys.argv:
    wcm = g.u64(g.base + 0x5B3CD88)
    phys = g.u64(g.u64(wcm + 0x30) + 0x28)
    g.call('write_memory', {'address': hex(phys + 0x70), 'hex': struct.pack('<3f', 301.167, -33.034, 433.870).hex()})
    g.call('write_memory', {'address': hex(phys + 0x64), 'hex': struct.pack('<f', -0.2968805).hex()})
    time.sleep(1.5)
    g.call('input_sequence', {'steps': [{'buttons': ['StickR'], 'frames': 4}, {'frames': 40}]})
os.makedirs('diag/twin/flick', exist_ok=True)
out = 'diag/twin/flick/cur.png'
frames = []
t0 = time.time()
while time.time() - t0 < secs:
    r = g.call('screenshot', {'height': 180, 'path': os.path.abspath(out)})
    png = None
    if isinstance(r, dict):
        if r.get('png') and os.path.exists(r['png']):
            png = open(r['png'], 'rb').read()
        elif r.get('png_base64'):
            png = base64.b64decode(r['png_base64'])
    if not png:
        print('screenshot result', str(r)[:200])
        break
    im = Image.open(io.BytesIO(png)).convert('L')
    w, h = im.size
    reg = im.crop((int(w * .15), int(h * .05), int(w * .6), int(h * .5))).resize((24, 12))
    frames.append((time.time() - t0, list(reg.tobytes()), png))
n = len(frames)
print('%d frames in %.1f s (%.1f per second)' % (n, time.time() - t0, n / max(time.time() - t0, 1e-3)))
if n > 10:
    cells = len(frames[0][1])
    med = [sorted(f[1][c] for f in frames)[n // 2] for c in range(cells)]
    score = [sum(abs(f[1][c] - med[c]) for c in range(cells)) / cells for f in frames]
    base = sorted(score)[n // 2]
    odd = [i for i in range(n) if score[i] > max(4 * base, base + 6)]
    print('median difference %.1f, odd frames: %s' % (base, [(i, round(frames[i][0], 2), round(score[i], 1)) for i in odd][:30]))
    for i in odd[:12]:
        for k in (i - 1, i, i + 1):
            if 0 <= k < n:
                open('diag/twin/flick/%s_%04d.png' % (who, k), 'wb').write(frames[k][2])
