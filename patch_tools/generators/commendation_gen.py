"""Generator + checker for the Commendation groups in commendation_live.py. Static only: reads nso/*.bin,
patch_manager.cpp, dusk_lan.cpp and every other diag/net/*_live.py; writes commendation_live.py; prints the
capstone listing of every word and the [V] context checks.
python commendation_gen.py      (run from diag/net)

Design and [V]/[I] marks: commendation_notes.md. No caves, no box: every record replaces one word in place.
  (Corrected 2026-11-14 after the live test: the first version had the two names swapped.)
  COMMEND_FANG  Bloodfang count (enemy kills). The kill/EXP award 0x10278EC calls 0x110CB68 with the enemy kind;
                it goes to the local count 0x110CC58 only when offline, else it sends request 0x70 to the
                server. 0x110CC58 adds the kill weight to the netvar u32 pgd+0x44C8 through the setter 0x110CE28,
                which in a session SENDS message 0x58 instead of storing. Here: gate -> nop, store straight in.
  COMMEND_COLL  Collector count (map items, MapItemMan 0x15A3F00 -> 0x15B52E0 -> 0xCD49D4): rarity chr+0xB1 and
                first / repeat pickup pick the points; added to u32 pgd+0x4458 only when offline (0xCD4B74),
                through the setter 0xCD526C (same 0x58 problem). Same fix.
  COMMEND_EVAL  The per-phase ranking of par+0x2E0 (the commendation manager): participant list fill at
                MatchPreLoading (0x1149E4C), phase-start init (0x110BB4C), per-frame evaluation (0x110B36C).
                All three are the stock offline path; apply 0x110B36C last.
The assist half (mirror the two counts into the other games' copies) is in commendation_notes.md section 5."""
import glob
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
DATA = open(os.path.join(N, 'main_data.bin'), 'rb').read()
DATA_BASE = 0x563F000
SRC = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core')
PM = os.path.join(SRC, 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

NOP = 0xD503201F
STR_W8_X0_18 = 0xB9001808     # str w8, [x0, #0x18]

# ---------------------------------------------------------------- shipped records (patch_manager.cpp)
src = open(PM, encoding='utf-8', errors='ignore').read()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    n, name, body = int(m.group(1)), m.group(2), m.group(3)
    vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
    arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
shipped = {}
for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
    a, name = int(m.group(1), 16), m.group(2)
    if name in arrays:
        for i in range(len(arrays[name])):
            shipped[a + i] = name
print('shipped bytes parsed: %d' % len(shipped))

# ---------------------------------------------------------------- every other helper's *_live.py records
others = {}
for f in glob.glob(os.path.join(HERE, '*_live.py')):
    if os.path.basename(f) == 'commendation_live.py':
        continue
    for m in re.finditer(r'\(0x([0-9A-Fa-f]+),\s*"([0-9A-Fa-f]*)",\s*"([0-9A-Fa-f]+)"', open(f).read()):
        a = int(m.group(1), 16)
        for i in range(len(m.group(3)) // 2):
            others[a + i] = os.path.basename(f)
print('other *_live.py bytes parsed: %d' % len(others))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def q(a):
    return struct.unpack_from('<Q', DATA, a - DATA_BASE)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def at(addr):
    return dis1(addr, word(addr))


def check(addr, text):
    got = at(addr)
    assert got == text, 'at %x: %s, expected %s' % (addr, got, text)


listing = []
groups = {}


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    for i in range(4):
        assert addr + i not in shipped, 'collides with shipped %s at %x' % (shipped[addr + i], addr)
        assert addr + i not in others, 'collides with %s at %x' % (others[addr + i], addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


# ================================================================ [V] context checks (fail loudly if wrong)
listing.append('=== context [V]')
# counter objects: id 30000 at wp+0x248 (+8 = 0x250), id 40000 at wp+0x2B0 (+8 = 0x2B8); table wp+0xC40 / +0xC48
for a, t in ((0xF71E9C, 'mov w9, #0x7530'), (0xF71EA0, 'str w9, [x19, #0x250]'),
             (0xF71EA4, 'mov w9, #0x9c40'), (0xF71EAC, 'str w9, [x19, #0x2b8]'),
             (0xF71EC0, 'add x18, x19, #0x248'), (0xF7202C, 'str x18, [x19, #0xc40]'),
             (0xF71ECC, 'add x0, x19, #0x2b0'), (0xF72030, 'str x0, [x19, #0xc48]'),
             (0xF70D8C, 'str x8, [x19, #0x248]'), (0xF70E18, 'str x8, [x19, #0x2b0]')):
    check(a, t)
assert q(0x56E7A28 + 0x20) == 0xF6CEA4 and q(0x56E7AC0 + 0x20) == 0xF6D710, 'getter slots'
assert q(0x56E7A28 + 0x10) == 0xF6CE54 and q(0x56E7AC0 + 0x10) == 0xF6D6C0, 'enable slots'
# getters: id 30000 pays PhaseInfo +0x8D / +0x8E for rank 1 / 2 of field A (Bloodfang),
#          id 40000 pays PhaseInfo +0x93 / +0x94 for rank 1 / 2 of field B (Collector)
for a, t in ((0xF6CF30, 'ldrb w8, [x1, #8]'), (0xF6CF4C, 'ldrb w8, [x8, #0x8d]'), (0xF6CF70, 'ldrb w8, [x8, #0x8e]'),
             (0xF6D79C, 'ldrb w8, [x1, #0x18]'), (0xF6D7B8, 'ldrb w8, [x8, #0x93]'), (0xF6D7DC, 'ldrb w8, [x8, #0x94]'),
             (0xF6CE68, 'ldrb w0, [x8, #0x15d]'), (0xF6D6D4, 'ldrb w0, [x8, #0x15e]')):
    check(a, t)
# writers: 0x110E4EC -> counter 30000, 0x110E830 -> counter 40000 (both from the apply 0x110C850 / 0x110C9DC)
check(0x110E510, 'mov w1, #0x7530')
check(0x110E854, 'mov w1, #0x9c40')
# ranking keys: +0x15D -> field +0x10 by u32 pgd+0x44C8 (Bloodfang), +0x15E -> field +0x20 by u32 pgd+0x4458
# (Collector)
for a, t in ((0x110BDBC, 'ldrb w8, [x19, #0x15d]'), (0x110BDC8, 'adr x8, #0x110c2e8'), (0x110BDD8, 'mov w1, #8'),
             (0x110BDE0, 'ldrb w8, [x19, #0x15e]'), (0x110BDEC, 'adr x8, #0x110c2f4'), (0x110BDFC, 'mov w1, #0x18'),
             (0x110C2E8, 'mov w8, #0x44c8'), (0x110C2EC, 'ldr w0, [x0, x8]'),
             (0x110C2F4, 'mov w8, #0x4458'), (0x110C2F8, 'ldr w0, [x0, x8]'),
             (0x110C6BC, 'mov w8, #0x46b2'),                       # a player with pgd+0x46B2 != 0 counts 0
             (0x110C74C, 'csel w13, w12, w13, eq'),                # count 0 -> rank 0xFF (no award)
             (0x110CFB8, 'mov w8, #0x46a0'), (0x110CFCC, 'cmp x9, #7')):   # list = participants, max 8
    check(a, t)
# final-check time PhaseInfo +0xF6 and checkpoints +0xEC..+0xF4
check(0x110B4C8, 'ldrsh w8, [x24, #0xf6]')
check(0x110B530, 'ldrsh w9, [x24, #0xec]')
# the two netvar setters send message 0x58 while a session has members and do not store
for a, t in ((0xCD5300, 'mov w2, #0x58'), (0xCD5328, 'str w8, [x19, #0x18]'),
             (0x110CEBC, 'mov w2, #0x58'), (0x110CEE4, 'str w8, [x19, #0x18]')):
    check(a, t)
# Collector: MapItemMan (0x15A3F00, log file MapItemMan.cpp) -> 0x15B52E0 with the picker's pgd (pgd+0x2E8)
# Bloodfang: kill / EXP award 0x10278EC -> 0x110CB68 (enemy kind u16 chr+0xC2), needs the enemy flag +5
check(0x1027C18, 'bl #0x110cb68')
check(0x1027BE0, 'ldrb w8, [x20, #5]')
check(0x15B5348, 'add x20, x1, #0x2e8')
check(0x15B53A4, 'bl #0xcd49d4')
check(0x15B5314, 'ldrb w8, [x8, #0x15e]')
listing.append('  all context words match')

# ================================================================ COMMEND_COLL
listing.append('=== COMMEND_COLL (Collector count, u32 pgd+0x4458)')
for a, t in ((0xCD4B68, 'adrp x9, #0x5b65000'), (0xCD4B6C, 'ldr x9, [x9, #0xc20]'), (0xCD4B70, 'ldrb w9, [x9, #0xbda]'),
             (0xCD4B78, 'ldr x9, [x19, #0x710]'), (0xCD4B7C, 'mov w10, #0x4440'), (0xCD4B80, 'add x1, x29, #0x1c'),
             (0xCD4B84, 'add x0, x9, x10'), (0xCD4B88, 'ldr w9, [x0, #0x18]'), (0xCD4B8C, 'add w8, w9, w8'),
             (0xCD4B98, 'ldp x20, x19, [sp, #0x30]')):
    check(a, t)
check(0xCD4B34, 'mov w8, wzr')     # no-points paths reach 0xCD4B68 with w8 = 0
check(0xCD4B38, 'b #0xcd4b68')
groups['COMMEND_COLL'] = [
    text_patch(0xCD4B74, 'cbz w9, #0xcd4b98', NOP, 'count in LAN too (offline gate)'),
    text_patch(0xCD4B90, 'str w8, [x29, #0x1c]', STR_W8_X0_18, 'store the new count into pgd+0x4458'),
    text_patch(0xCD4B94, 'bl #0xcd526c', NOP, 'no netvar setter (it would send 0x58 and not store)'),
]

# ================================================================ COMMEND_FANG
listing.append('=== COMMEND_FANG (Bloodfang count, u32 pgd+0x44C8)')
for a, t in ((0x110CB88, 'ldrb w8, [x8, #0xbda]'), (0x110CB90, 'ldp x20, x19, [sp, #0x30]'),
             (0x110CBA4, 'b #0x110cc58'), (0x110CBEC, 'bl #0x110f35c'), (0x110CC10, 'mov w1, #0x70'),
             (0x110CDE0, 'mov w8, #0x44b0'), (0x110CDE4, 'sub x1, x29, #0x30'), (0x110CDE8, 'add x0, x0, x8'),
             (0x110CDEC, 'ldr w8, [x0, #0x18]'), (0x110CDF0, 'add w8, w8, w19'), (0x110CDFC, 'b #0x110cc84')):
    check(a, t)
groups['COMMEND_FANG'] = [
    text_patch(0x110CB8C, 'cbz w8, #0x110cba8', NOP, 'local count in LAN, no 0x70 request to the server'),
    text_patch(0x110CDF4, 'stur w8, [x29, #-0x30]', STR_W8_X0_18, 'store the new count into pgd+0x44C8'),
    text_patch(0x110CDF8, 'bl #0x110ce28', NOP, 'no netvar setter (it would send 0x58 and not store)'),
]

# ================================================================ COMMEND_EVAL
listing.append('=== COMMEND_EVAL (ranking of par+0x2E0, stock offline path)')
for a, t in ((0x1149E44, 'ldr x9, [x25, #0xc20]'), (0x1149E48, 'ldrb w9, [x9, #0xbda]'),
             (0x1149E50, 'adrp x9, #0x56f3000'), (0x1149E54, 'add x9, x9, #0x420'), (0x1149E64, 'mov w1, #0x27'),
             (0x110BB28, 'strb wzr, [x0, #0x15c]'), (0x110BB2C, 'str wzr, [x0, #0x158]'),
             (0x110BB48, 'ldrb w8, [x8, #0xbda]'), (0x110BC14, 'b #0x110bcc0'),
             (0x110B368, 'ldrb w8, [x8, #0xbda]'), (0x110B370, 'ldr x8, [x19, #0x150]'),
             (0x110B378, 'ldrb w8, [x19, #0x15f]'), (0x110B3C4, 'bl #0x110b410'), (0x110B3D8, 'b #0x110b700')):
    check(a, t)
assert q(0x56F3420 + 0x30) == 0x110CFB8, 'participant functor vtable 0x56F3420 slot +0x30'
groups['COMMEND_EVAL'] = [
    text_patch(0x1149E4C, 'cbz w9, #0x1149eac', NOP, 'MatchPreLoading: build the participant list (+0x150)'),
    text_patch(0x110BB4C, 'cbz w8, #0x110bba8', NOP, 'phase start: checkpoint index +0x158, start push'),
    text_patch(0x110B36C, 'cbz w8, #0x110b3c8', NOP, 'per-frame checkpoints / final ranking (apply last)'),
]

# ---------------------------------------------------------------- no record overlaps another
seen = {}
for g, rs in groups.items():
    for a, o, n, c in rs:
        for i in range(len(n) // 2):
            assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
            seen[a + i] = g
# the assist half keys on the last COMMEND_EVAL word and the two count offsets
lan = open(os.path.join(SRC, 'dusk_lan.cpp'), encoding='utf-8', errors='ignore').read()
for needle in ('COMMEND_EVAL_GATE = 0x110B36C', 'COMMEND_EVAL_NOP = 0xD503201F', 'PGD_BLOODFANG = 0x44C8',
               'PGD_COLLECTOR = 0x4458', 'VIRTUE_COPY_COUNTERS_OFF = true'):
    assert needle in lan, 'dusk_lan.cpp lacks %s' % needle
assert groups['COMMEND_EVAL'][-1][0] == 0x110B36C and groups['COMMEND_EVAL'][-1][2] == hexw(NOP)
listing.append('dusk_lan.cpp CommendShare keys on 0x110B36C = nop and the offsets above')
listing.append('no overlap with patch_manager.cpp (%d bytes) or %d bytes of other *_live.py records'
               % (len(shipped), len(others)))

# ---------------------------------------------------------------- optional: the award table from the regulation
try:
    import zstandard
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    KEY = bytes.fromhex('10B8C2BDAAB0FA1D5EA1CD750CFDBC1368A76603119D56647F4B25069443C64B')
    REG = os.path.join(HERE, '..', '..', 'emulators', 'v30-eglantine', 'user', 'duskbloods_test', 'nand', 'system',
                       'save', 'bcat', '0400D1D02399A000', 'Regulation', 'regulation_nt_1_0.bin')
    blob = open(REG, 'rb').read()
    d = Cipher(algorithms.AES(KEY), modes.CBC(blob[:16])).decryptor()
    plain = d.update(blob[16:]) + d.finalize()
    us, cs = struct.unpack_from('>II', plain, 0x1c)
    bnd = zstandard.ZstdDecompressor().decompress(plain[0x4c:0x4c + cs], max_output_size=us)
    for i in range(struct.unpack_from('<I', bnd, 0xc)[0]):
        h = 0x40 + i * 0x24
        _, _, size, _, off, fid, name_at = struct.unpack_from('<BxxxiqqIiI', bnd, h)
        e = name_at
        while bnd[e:e + 2] != b'\0\0':
            e += 2
        if bnd[name_at:e].decode('utf-16le').endswith('PhaseInfoParam.param'):
            listing.append('=== award table (PhaseInfoParam, regulation_nt_1_0.bin)')
            for k in range(struct.unpack_from('<H', bnd, off + 0xa)[0]):
                rid, ro = struct.unpack_from('<ixxxxQ', bnd, off + 0x40 + k * 24)
                if 10020001 <= rid <= 10020004:
                    r = bnd[off + ro:off + ro + 0xF8]
                    listing.append('  row %d: Bloodfang 1st/2nd %d/%d, Collector 1st/2nd %d/%d, checkpoints %s, '
                                   'final check %d s before the end' % (
                                       rid, r[0x8D], r[0x8E], r[0x93], r[0x94],
                                       list(struct.unpack_from('<5h', r, 0xEC)), struct.unpack_from('<h', r, 0xF6)[0]))
except Exception as e:   # tables are informational only
    listing.append('(award table not read: %s)' % e)

print('\n'.join(listing))

ORDER = ['COMMEND_FANG', 'COMMEND_COLL', 'COMMEND_EVAL']
notes = {
    'COMMEND_FANG': 'Bloodfang: enemy kills count in LAN, stored straight into u32 pgd+0x44C8',
    'COMMEND_COLL': 'Collector: map items count in LAN, stored straight into u32 pgd+0x4458',
    'COMMEND_EVAL': 'per-phase top-two ranking of par+0x2E0 runs in LAN (0x110B36C last)',
}
out = ['"""Commendation groups: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by commendation_gen.py (original-word checks, capstone listing of every new word, [V] context checks,',
       'collision checks against patch_manager.cpp and every other diag/net/*_live.py). No caves. Not live-tested.',
       'Notes: commendation_notes.md. Apply on EVERY game, in ORDER; COMMEND_EVAL last, its 0x110B36C record last.',
       'Without the assist half (commendation_notes.md section 5) each game ranks with 0 for everybody but the',
       'players it credited itself, and VIRTUE_COPY_COUNTERS_OFF must be true (copies get commendation records)."""',
       '',
       'FANG_COUNT = 0x44C8      # u32 pgd+0x44C8 Bloodfang points (netvar pgd+0x44B0, value +0x18)',
       'COLL_COUNT = 0x4458      # u32 pgd+0x4458 Collector points (netvar pgd+0x4440, value +0x18)',
       '']
for g in ORDER:
    out.append('%s = [  # %s' % (g, notes[g]))
    for a, o, n, c in groups[g]:
        out.append('    (0x%X, "%s", "%s", %s),  # %s -> %s' % (a, o, n, c, dis1(a, int.from_bytes(bytes.fromhex(o), 'little')),
                                                              dis1(a, int.from_bytes(bytes.fromhex(n), 'little'))))
    out.append(']')
out.append('')
out.append('ORDER = [%s]' % ', '.join(ORDER))
open(os.path.join(HERE, 'commendation_live.py'), 'w').write('\n'.join(out) + '\n')
print('commendation_live.py written')
