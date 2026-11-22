"""Live code/data patches on twin games: python diag/twin/lp.py AB "OFF ORIG NEW [d]" ...   (hex; bytes as in memory;
add d for a data byte patch that needs no JIT invalidation). Prints what was there. "undo" as last arg swaps."""
import sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
args = [a for a in sys.argv[2:] if a != 'undo']
undo = 'undo' in sys.argv
for w in sys.argv[1]:
    m = Mem(w)
    for a in args:
        f = a.split()
        off, orig, new = int(f[0], 16), f[1].lower(), f[2].lower()
        if undo:
            orig, new = new, orig
        have = m.read(m.base + off, len(orig) // 2).hex()
        if have == orig:
            m.write(m.base + off, bytes.fromhex(new), code=len(f) < 4)
            print(w, hex(off), have, '->', new)
        else:
            print(w, hex(off), 'is', have, '(already patched)' if have == new else '- MISMATCH, not patched')
