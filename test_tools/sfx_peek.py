"""READ-ONLY: dump SFX wrapper objects and say what each pointer in them points at (by vtable).
python diag/twin/pkgtest.py run diag/twin/sfx_peek.py WHO ADDR_HEX [ADDR_HEX...]"""
import struct, sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
m = Mem(sys.argv[1])
def vt(p):
    try:
        v = m.u64(p)
    except Exception:
        return None
    off = v - m.base
    return off if 0x5000000 < off < 0x6000000 else None
for a in sys.argv[2:]:
    a = int(a, 16)
    b = m.read(a, 0xD8)
    print('obj %x' % a)
    for o in range(0, 0xD8, 8):
        v = struct.unpack_from('<Q', b, o)[0]
        note = ''
        if 0x2000000000 <= v < 0x3000000000:
            t = vt(v)
            note = ' -> heap' + (' vt main+%#x' % t if t else '')
            if t:
                try:
                    bb = m.read(v, 0x40)
                    note += ' | ' + ' '.join('%x' % x for x in struct.unpack_from('<8Q', bb))[:150]
                except Exception:
                    pass
        elif m.base <= v < m.base + 0x6000000:
            note = ' main+%#x' % (v - m.base)
        lo, hi = struct.unpack_from('<ii', b, o)
        print('  +%02x %016x  (%d, %d)%s' % (o, v, lo, hi, note))
