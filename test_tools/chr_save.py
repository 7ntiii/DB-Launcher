"""READ-ONLY: save chr objects to files. python diag/twin/pkgtest.py run diag/twin/chr_save.py WHO OUTDIR NAME=HEX ..."""
import sys, os
sys.path.insert(0, 'diag/twin')
from mem import Mem
m = Mem(sys.argv[1]); d = sys.argv[2]; os.makedirs(d, exist_ok=True)
for kv in sys.argv[3:]:
    k, v = kv.split('=')
    open(os.path.join(d, k + '.bin'), 'wb').write(m.read(int(v, 16), 0x2000))
    print('saved', k)
