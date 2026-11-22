"""Apply patch groups from diag/net/items_live.py live: python diag/twin/apply_groups.py AB GROUP [GROUP..] [undo]
Each record is checked against its original (or already-new) bytes first; a group with a mismatch is not applied."""
import importlib.util, sys
sys.path.insert(0, 'diag/twin')
from mem import Mem
import os
spec = importlib.util.spec_from_file_location('il', os.environ.get('PATCH_FILE', 'diag/net/items_live.py'))
il = importlib.util.module_from_spec(spec); spec.loader.exec_module(il)
undo = 'undo' in sys.argv
for w in sys.argv[1]:
    m = Mem(w)
    for g in [a for a in sys.argv[2:] if a != 'undo']:
        recs = getattr(il, g)
        have = [m.read(m.base + off, len(o) // 2).hex() for off, o, n, c in recs]
        bad = [(hex(r[0]), h) for r, h in zip(recs, have) if h not in (r[1].lower(), r[2].lower())]
        if bad:
            print(w, g, 'NOT applied, unexpected bytes:', bad[:4]); continue
        for off, o, n, c in recs:
            m.write(m.base + off, bytes.fromhex(o if undo else n), code=c)
        print(w, g, len(recs), 'records', 'undone' if undo else 'applied')
