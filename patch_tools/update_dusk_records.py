"""Like add_dusk_records.py, but also UPDATES records whose address is already in patch_manager.cpp:
python tools/update_dusk_records.py DATA_FILE GROUP [GROUP..]
For each record (offset, orig_hex, new_hex, is_code) of the groups: if DUSK_W_<OFFSET> exists in the source, its
byte array is replaced by new_hex (the _ORIGINAL array is left alone: it is the game's stock word); the rest is
handed to add_dusk_records.py. Prints what it changed."""
import importlib.util
import re
import subprocess
import sys

P = r'<WORKSPACE>\src\lichii\src\core\file_sys\patch_manager.cpp'
spec = importlib.util.spec_from_file_location('d', sys.argv[1])
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
s = open(P, encoding='utf-8', newline='').read()
changed = 0
for g in sys.argv[2:]:
    for off, o, n, c in getattr(d, g):
        name = 'DUSK_W_%X' % off
        m = re.search(r'(constexpr std::array<u8, (\d+)> %s\{)([^}]*)(\};)' % name, s)
        if not m:
            continue
        new = ', '.join('0x%s' % n[i:i + 2].upper() for i in range(0, len(n), 2))
        if int(m.group(2)) != len(n) // 2:
            print('SIZE MISMATCH', name)
            continue
        if m.group(3).replace(' ', '').upper() != new.replace(' ', '').upper():
            s = s[:m.start(3)] + new + s[m.end(3):]
            changed += 1
            print('update', name, g, m.group(3), '->', new)
open(P, 'w', encoding='utf-8', newline='').write(s)
print('updated', changed)
r = subprocess.run([sys.executable, 'tools/add_dusk_records.py'] + sys.argv[1:], capture_output=True, text=True)
print('added', r.stdout.count('add DUSK_W_'), r.stderr[-300:])
