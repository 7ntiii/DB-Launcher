"""Scan the world chr manager for chr sets: python diag/twin/wcm_scan.py A [SIZE]
Prints every qword in WCM that points to an object whose first qword is a vtable in main, with the
vtable offset; then for each such object the count-looking fields."""
import struct, sys
sys.path.insert(0, 'diag/twin')
import mem

size = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x3000
wcm = mem.u64(mem.base + 0x5B3CD88)
raw = b''.join(mem.rd(wcm + o, 0x800) for o in range(0, size, 0x800))
q = struct.unpack('<%dQ' % (size // 8), raw)
lo, hi = mem.base, mem.base + 0x6000000
print('WCM %x vt %x' % (wcm, q[0] - lo))
seen = {}
for i, v in enumerate(q):
    if lo <= v < hi:
        print('  +%x = main+%x' % (i * 8, v - lo))
    elif 0x2000000000 <= v < 0x3000000000 and v not in seen:
        try:
            vt = mem.u64(v)
        except Exception:
            continue
        seen[v] = 1
        if lo <= vt < hi:
            print('  +%x -> %x obj vt main+%x' % (i * 8, v, vt - lo))
