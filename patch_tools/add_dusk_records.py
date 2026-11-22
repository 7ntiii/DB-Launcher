"""Add 4-byte LAN patch records to patch_manager.cpp from a live-patch data file:
python tools/add_dusk_records.py DATA_FILE GROUP [GROUP..]
DATA_FILE holds lists of (offset, orig_hex, new_hex, is_code) as in diag/net/items_live.py. Records whose
address is already in the source are skipped. Declarations go after DUSK_W_1597400_ORIGINAL, table rows
after the 0x1597400 row."""
import importlib.util
import sys

P = r'<WORKSPACE>\src\lichii\src\core\file_sys\patch_manager.cpp'
spec = importlib.util.spec_from_file_location('d', sys.argv[1])
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
s = open(P, newline='').read()
nl = '\r\n' if '\r\n' in s else '\n'


def arr(h):
    return ', '.join('0x%s' % h[i:i + 2].upper() for i in range(0, len(h), 2))


decl, rows = '', ''
for g in sys.argv[2:]:
    for off, o, n, c in getattr(d, g):
        name = 'DUSK_W_%X' % off
        if name + '{' in s or name + '{' in decl:
            print('skip', name)
            continue
        assert len(o) == len(n)
        k = len(o) // 2
        decl += '// %s (%s)%s' % (hex(off), g, nl)
        decl += 'constexpr std::array<u8, %d> %s{%s};%s' % (k, name, arr(n), nl)
        decl += 'constexpr std::array<u8, %d> %s_ORIGINAL{%s};%s' % (k, name, arr(o), nl)
        if off >= 0xC500000:
            # the emulator's cave region (main+0xC500000..): accepted only as a cave record with no original
            rows += '    BuiltinPatchRecord{0x%X, %s, {}, true},%s' % (off, name, nl)
        else:
            rows += '    BuiltinPatchRecord{0x%X, %s, %s_ORIGINAL},%s' % (off, name, name, nl)
        print('add', name, g)
a = 'constexpr std::array<u8, 4> DUSK_W_1597400_ORIGINAL{0x81, 0x00, 0x00, 0x54};' + nl
b = '    BuiltinPatchRecord{0x1597400, DUSK_W_1597400, DUSK_W_1597400_ORIGINAL},' + nl
assert s.count(a) == 1 and s.count(b) == 1
s = s.replace(a, a + decl).replace(b, b + rows)
open(P, 'w', newline='').write(s)
