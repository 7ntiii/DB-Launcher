"""Apply code patches to twin games as soon as their main module is up (JIT-safe), once per game.
python diag/twin/boot_patch.py AB "OFF NEW ORIG" ["OFF NEW ORIG" ...]   (hex words)"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

games = sys.argv[1]
patches = [tuple(int(x, 16) for x in p.split()) for p in sys.argv[2:]]
done = set()
deadline = time.time() + 600
while len(done) < len(games) and time.time() < deadline:
    for w in games:
        if w in done:
            continue
        try:
            m = Mem(w)
            words = [struct.unpack('<I', m.read(m.base + off, 4))[0] for off, _, _ in patches]
            if any(have not in (orig, new) for have, (off, new, orig) in zip(words, patches)):
                continue                           # not loaded yet
            for have, (off, new, orig) in zip(words, patches):
                if have == orig:
                    m.write(m.base + off, struct.pack('<I', new), code=True)
            done.add(w)
            print(time.strftime('%H:%M:%S'), w, 'patched', len(patches), flush=True)
        except Exception as e:
            pass
    time.sleep(1)
