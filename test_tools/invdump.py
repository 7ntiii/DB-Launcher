"""READ-ONLY: dump every inventory entry of the local player on each game.
usage: python diag/twin/invdump.py AB"""
import sys
sys.path.insert(0, 'diag/twin')
import rewards as R

for w in (sys.argv[1] if len(sys.argv) > 1 else 'AB'):
    m = R.Mem(w)
    pgd = R.local_pgd(m)
    inv = R.inventory(m, pgd)
    print('%s: pgd %x, %d entries' % (w, pgd, len(inv)))
    for i, w0, w1, cnt in inv:
        print('   [%3d] %08x %08x x%d' % (i, w0, w1, cnt))
