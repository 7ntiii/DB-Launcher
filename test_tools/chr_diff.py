"""READ-ONLY: byte-diff two chr objects on one game (invisible copy hunt).
python diag/twin/pkgtest.py run diag/twin/chr_diff.py WHO CHR_A_HEX CHR_B_HEX [SIZE_HEX=2000]"""
import sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
m = Mem(sys.argv[1]); a = int(sys.argv[2], 16); b = int(sys.argv[3], 16)
n = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x2000
x, y = m.read(a, n), m.read(b, n)
out = []
for o in range(n):
    if x[o] != y[o] and x[o] < 4 and y[o] < 4:      # small flags / enum bytes only
        out.append('+%04x %02x|%02x' % (o, x[o], y[o]))
print(len(out), 'small-byte differences')
print('  '.join(out[:160]))
