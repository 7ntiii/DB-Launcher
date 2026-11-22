"""Alliance patches, live (diag/net/alliance_notes.md group A): python diag/twin/ally_live.py AB [undo]"""
import sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
P = [(0x10AF424, '082540f9', '082140f9', True), (0x4C4B600, '40000000', '00000000', False),
     (0x10B5D38, '09f3ff34', '1f2003d5', True), (0x10AFA78, '95030036', '1f2003d5', True),
     (0x10AD748, '00060054', '1f2003d5', True), (0x10B07B4, '00013fd6', '1f2003d5', True)]
undo = 'undo' in sys.argv
for w in sys.argv[1]:
    m = Mem(w)
    for off, orig, new, code in P:
        have = m.read(m.base + off, 4).hex()
        want = orig if undo else new
        if have in (orig, new, '20000000'):
            m.write(m.base + off, bytes.fromhex(want), code=code)
            print(w, hex(off), have, '->', want)
        else:
            print(w, hex(off), 'is', have, '- NOT patched')
