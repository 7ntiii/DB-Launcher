"""Find a chr's stagger gauge (CSChrToughnessModule) by snapshot diff. READ ONLY: only Mem.read, never writes.
python diag/twin/modscan.py WHO CHR_ADDR snap NAME        save the module bag of that chr to diag/twin/modscan_NAME.json
python diag/twin/modscan.py WHO CHR_ADDR diff NAME1 NAME2 print every u32 / float field that changed, per module
python diag/twin/modscan.py WHO CHR_ADDR list             module pointers in the bag with their vtable (main+off)

Module bag = [chr+0x2470] (known slots: +0x18 data module = HP at +0x290, +0xE8 physics, +0x280 friendly group;
diag/net/test_tools_notes.md). The bag's first 0x300 bytes are read; every qword that points into the heap near the
bag is taken as a module and its first 0x400 bytes are saved. The stagger gauge has no known slot [catch_notes 3]:
take `snap s0` before a hit, `snap s1` right after one ZR hit (gauge up), `snap s2` a few seconds later (gauge
recovering) and `snap s3` after the stagger (gauge reset). The field that rises s0 -> s1, falls s1 -> s2 and drops
to 0 at s3 is the gauge (its maximum usually sits next to it). Run from the workspace root."""
import json
import os
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

BAG_LEN, MOD_LEN = 0x300, 0x400


def modules(m, c):
    bag = m.u64(c + 0x2470)
    raw = m.read(bag, BAG_LEN)
    out = {}
    for off in range(0, BAG_LEN, 8):
        p = struct.unpack_from('<Q', raw, off)[0]
        if not p or p & 7 or abs(p - bag) > 0x40000000:
            continue
        try:
            body = m.read(p, MOD_LEN)
        except Exception:
            continue
        vt = struct.unpack_from('<Q', body, 0)[0]
        out['%03x' % off] = {'ptr': p, 'vt': vt - m.base if m.base <= vt < m.base + 0x7000000 else None,
                             'hex': body.hex()}
    return bag, out


def main():
    who, c, verb = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
    m = Mem(who)
    if verb in ('snap', 'list'):
        bag, mods = modules(m, c)
        if verb == 'list':
            print('%s chr 0x%x bag 0x%x' % (who, c, bag))
            for k, v in mods.items():
                print('  bag+0x%s -> 0x%x vt %s' % (k, v['ptr'], 'main+0x%x' % v['vt'] if v['vt'] is not None else '-'))
            return
        path = os.path.join('diag', 'twin', 'modscan_%s.json' % sys.argv[4])
        json.dump({'who': who, 'chr': c, 'bag': bag, 'mods': mods}, open(path, 'w'))
        print('%s: %d modules saved to %s' % (who, len(mods), path))
        return
    if verb == 'diff':
        a = json.load(open(os.path.join('diag', 'twin', 'modscan_%s.json' % sys.argv[4])))
        b = json.load(open(os.path.join('diag', 'twin', 'modscan_%s.json' % sys.argv[5])))
        for k in sorted(set(a['mods']) & set(b['mods'])):
            x, y = bytes.fromhex(a['mods'][k]['hex']), bytes.fromhex(b['mods'][k]['hex'])
            rows = []
            for o in range(8, MOD_LEN, 4):
                if x[o:o + 4] != y[o:o + 4]:
                    u0, u1 = struct.unpack_from('<I', x, o)[0], struct.unpack_from('<I', y, o)[0]
                    f0, f1 = struct.unpack_from('<f', x, o)[0], struct.unpack_from('<f', y, o)[0]
                    rows.append('    +0x%03x  u32 %10d -> %10d   f %.4g -> %.4g' % (o, u0, u1, f0, f1))
            if rows:
                vt = a['mods'][k]['vt']
                print('bag+0x%s (vt %s), %d changed fields' % (k, 'main+0x%x' % vt if vt is not None else '-', len(rows)))
                print('\n'.join(rows[:40]))
        return
    print(__doc__)


if __name__ == '__main__':
    main()
