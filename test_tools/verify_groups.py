"""Check that patch groups are present in a running game (built-in): python diag/twin/verify_groups.py A FILE GROUP..
Prints per group how many records hold the new bytes."""
import importlib.util, sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
m = Mem(sys.argv[1])
spec = importlib.util.spec_from_file_location('g', sys.argv[2]); g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
for name in sys.argv[3:]:
    recs = getattr(g, name)
    bad = [hex(off) for off, o, n, c in recs if m.read(m.base + off, len(n) // 2).hex() != n.lower()]
    print(name, len(recs) - len(bad), 'of', len(recs), 'in place', ('MISSING ' + ' '.join(bad[:6])) if bad else '')
