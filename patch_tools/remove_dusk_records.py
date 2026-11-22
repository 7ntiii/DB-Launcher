"""Remove built-in records from patch_manager.cpp:
python tools/remove_dusk_records.py DATA_FILE GROUP [GROUP..]
For each record offset of the groups: deletes the arrays DUSK_W_<OFFSET> / DUSK_W_<OFFSET>_ORIGINAL and the
BuiltinPatchRecord row. Prints what it removed. Use it only for records nothing else depends on."""
import importlib.util
import re
import sys

P = r'<WORKSPACE>\src\lichii\src\core\file_sys\patch_manager.cpp'
spec = importlib.util.spec_from_file_location('d', sys.argv[1])
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
s = open(P, encoding='utf-8', newline='').read()
n = 0
for g in sys.argv[2:]:
    for rec in getattr(d, g):
        name = 'DUSK_W_%X' % rec[0]
        s, a = re.subn(r'[ \t]*constexpr std::array<u8, \d+> %s(_ORIGINAL)?\{[^}]*\};\r?\n' % name, '', s)
        s, b = re.subn(r'[ \t]*BuiltinPatchRecord\{0x%X, %s,[^\n]*\},?\r?\n' % (rec[0], name), '', s)
        if a or b:
            n += 1
            print('removed', name, 'arrays', a, 'rows', b)
open(P, 'w', encoding='utf-8', newline='').write(s)
print('records removed', n)
