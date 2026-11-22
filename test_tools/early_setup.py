"""Early setup while the twin games boot (run right after go.sh starts):
python diag/twin/early_setup.py SIGIL_GAMES [PATCH_FILE GROUP ..]
As soon as a game's debug server answers and its local player data exists: applies the given live patch groups
(to every game A and B) and, for the games named in SIGIL_GAMES ('-' for none), writes the Bloodsworn row with a
sigil into the local player data (pgd+0x10C = 600000, Albert with his sigil; default 600001 = no sigil), which the
match start applies. Keeps re-writing the row until a match object exists. Prints what it did."""
import importlib.util
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

sigil = sys.argv[1]
groups = []
if len(sys.argv) > 3:
    spec = importlib.util.spec_from_file_location('g', sys.argv[2])
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    groups = [(n, getattr(g, n)) for n in sys.argv[3:]]
done_patch, done_row = set(), {}
t0 = time.time()
while time.time() - t0 < 420:
    for w in 'AB':
        try:
            m = Mem(w)
            if w not in done_patch and m.read(m.base + 0x11123E0, 4):
                for name, recs in groups:
                    have = [m.read(m.base + off, len(o) // 2).hex() for off, o, n, c in recs]
                    if all(h in (r[1].lower(), r[2].lower()) for r, h in zip(recs, have)):
                        for off, o, n, c in recs:
                            m.write(m.base + off, bytes.fromhex(n), code=c)
                        print(time.strftime('%H:%M:%S'), w, name, 'applied', flush=True)
                    else:
                        print(time.strftime('%H:%M:%S'), w, name, 'NOT applied (unexpected bytes)', flush=True)
                done_patch.add(w)
            if w in sigil:
                gdm = m.u64(m.base + 0x5B57EB8)
                p = m.u64(gdm + 0x20) if gdm else 0
                if p:
                    cur = struct.unpack('<i', m.read(p + 0x10C, 4))[0]
                    if cur != 600000:
                        m.write(p + 0x10C, struct.pack('<i', 600000))
                        print(time.strftime('%H:%M:%S'), w, 'row', cur, '-> 600000', flush=True)
                    # the producer reads the equipped skill pairs {id, count} at pgd+0x1C6C (30 pairs), which
                    # only the menu's row apply fills: put the sigil skill 1010000 (Sworn Enemy) into a free pair
                    pairs = m.read(p + 0x1C6C, 30 * 8)
                    ids = [struct.unpack_from('<iI', pairs, i * 8) for i in range(30)]
                    if not any(i == 1010000 and c >= 1 for i, c in ids):
                        free = next((k for k, (i, c) in enumerate(ids) if i == -1 or c == 0), None)
                        if free is not None:
                            m.write(p + 0x1C6C + free * 8, struct.pack('<iI', 1010000, 1))
                            print(time.strftime('%H:%M:%S'), w, 'sigil skill 1010000 written into pair', free, flush=True)
                    done_row[w] = True
            par = m.u64(m.base + 0x5B3CDF8)
            if par and m.u32(par + 0xB8) >= 1 and (w not in sigil or done_row.get(w)) and w in done_patch:
                done_row[w + '_match'] = True
        except Exception:
            pass
    if all(done_row.get(w + '_match') for w in 'AB'):
        break
    time.sleep(0.5)
print('early setup finished', sorted(done_patch), done_row, flush=True)
