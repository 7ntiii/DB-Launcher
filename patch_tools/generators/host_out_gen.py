"""Generator + checker for HOST_OUT_LIST (host_out_live.py). Static only: reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py, writes host_out_live.py,
prints a capstone listing. python host_out_gen.py   (from diag/net)

HOST_OUT_LIST is a FALLBACK, not needed by the static reading (host_out_notes.md section 2): the host's
death list gives an out player stage 2 (02 01 01 00), which the EndPhase list filler 0x115646C lists.
Only if the live test shows the host's own word at stage 4 BEFORE its final EndPhase (host gets no entry)
apply this group: the filler then also lists a stage-4 pgd whose reason byte has bit 2 set
(04 04 / 04 05 / 04 06 / 04 07); stage-4 words with reason 1/2/3/8 (cut 04 03, points 04 02, abort 04 08)
stay skipped exactly as today, so the round-2/3 culls are unchanged.

In-place only, no cave: 0x115646C..0x115648C (9 words, the filler's skip test) + 0x11564AC (1 word, the
local-flag byte load now uses base pgd+0x4000 with offset 0xD0)."""
import glob
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
TXT = open(os.path.join(HERE, 'nso', 'main_text.bin'), 'rb').read()
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

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
        for i, bt in enumerate(arrays[name]):
            shipped[a + i] = name
print('shipped bytes parsed: %d' % len(shipped))

# ---------------------------------------------------------------- every other *_live.py record
live = {}
for f in glob.glob(os.path.join(HERE, '*_live.py')):
    if os.path.basename(f) == 'host_out_live.py':
        continue
    t = open(f, encoding='utf-8', errors='ignore').read()
    for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]+)"', t):
        a, new = int(m.group(1), 16), m.group(3)
        for i in range(len(new) // 2):
            live.setdefault(a + i, os.path.basename(f))
print('*_live.py bytes parsed: %d' % len(live))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def ldr_w(rt, rn, off): return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def ldrb(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt


listing = []


def text_patch(addr, expect, new, expect_new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    got_new = dis1(addr, new)
    assert got_new == expect_new, 'new at %x: %s, expected %s' % (addr, got_new, expect_new)
    for i in range(4):
        assert addr + i not in shipped, 'collides with shipped %s at %x' % (shipped[addr + i], addr)
        assert addr + i not in live, 'collides with %s at %x' % (live[addr + i], addr)
    listing.append('  0x%x  %-28s ->  %-28s (%s)' % (addr, got, got_new, note))
    return (addr, hexw(old), hexw(new), True)


# ---------------------------------------------------------------- context the change relies on
CTX = [
    (0x1156490, 'ldr x12, [x0, #8]'),          # x12 reloaded: old w12 dead
    (0x1156494, 'ldr x9, [x12, #0x490]'),      # w9 overwritten
    (0x1156498, 'add x11, x9, #1'),            # w11 overwritten
    (0x11564B0, 'cmp w10, #1'),                # the only use of the byte at pgd+0x40D0
    (0x1156514, 'str w8, [x9, #0x40]'),        # w8 = the stage word (unchanged meaning)
    (0x1156528, 'ret'),                        # skip target
]
for a, t in CTX:
    assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)))
# x10 is not touched between 0x1156490 and 0x11564AC
for a in range(0x1156490, 0x11564AC, 4):
    ins = list(md.disasm(struct.pack('<I', word(a)), a))[0]
    assert not re.search(r'(?<![#\w])[xw]10\b', ins.op_str), hex(a)

# no branch lands inside the changed words (the function entry 0x115646C is reached only through the vtable
# 0x56F4B08 slot 0x30; its only constructor is EndPhase 0x114C0DC)
def branch_target(pc, w):
    if (w & 0x7C000000) == 0x14000000:                       # b / bl
        imm = w & 0x3FFFFFF
        return pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
    if (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000:   # b.cond / cbz / cbnz
        imm = (w >> 5) & 0x7FFFF
        return pc + ((imm - (1 << 19)) if imm & (1 << 18) else imm) * 4
    if (w & 0x7E000000) == 0x36000000:                       # tbz / tbnz
        imm = (w >> 5) & 0x3FFF
        return pc + ((imm - (1 << 14)) if imm & (1 << 13) else imm) * 4
    return None


INSIDE = set(range(0x1156470, 0x1156490, 4)) | {0x11564AC}
hits = []
for o in range(0, len(TXT) - 3, 4):
    w = struct.unpack_from('<I', TXT, o)[0]
    t = branch_target(o, w)
    if t is not None and t in INSIDE:
        hits.append(o)
assert not hits, 'branch into the changed words: %r' % [hex(h) for h in hits]
listing.append('no b/bl/b.cond/cbz/tbz in main text targets 0x1156470..0x115648C or 0x11564AC')

# ---------------------------------------------------------------- HOST_OUT_LIST
F = 0x115646C
listing.append('=== HOST_OUT_LIST (filler 0x115646C, x0 = functor, x1 = pgd)')
group = [
    text_patch(F + 0x00, 'mov w8, #0x40d0', 0x9140102A, 'add x10, x1, #4, lsl #12', 'x10 = pgd+0x4000'),
    text_patch(F + 0x04, 'add x10, x1, x8', ldr_w(9, 1, 0x154), 'ldr w9, [x1, #0x154]', 'pgd+0x154'),
    text_patch(F + 0x08, 'ldr w8, [x1, #0x154]', 0x51006529, 'sub w9, w9, #0x19', 'P: +0x154 in 0x14..0x18'),
    text_patch(F + 0x0C, 'sub w9, w8, #0x19', ldr_w(8, 10, 0x6B0), 'ldr w8, [x10, #0x6b0]', 'w8 = pgd+0x46B0'),
    text_patch(F + 0x10, 'ldr w8, [x10, #0x5e0]', word(0x1156484), 'and w11, w8, #0xff', 'stage byte'),
    text_patch(F + 0x14, 'cmn w9, #6', 0x7216011F, 'tst w8, #0x400', 'reason bit 2 (4/5/6/7)'),
    text_patch(F + 0x18, 'and w11, w8, #0xff', 0x7A440960, 'ccmp w11, #4, #0, eq',
               'eq <=> stage 4 and reason bit 2 clear'),
    text_patch(F + 0x1C, 'ccmp w11, #4, #4, ls', 0x3A461922, 'ccmn w9, #6, #2, ne',
               'not that -> hi <=> P; that -> hi'),
    text_patch(F + 0x20, 'b.eq #0x1156528', 0x540004E8, 'b.hi #0x1156528', 'skip (no list entry)'),
    text_patch(0x11564AC, 'ldrb w10, [x10]', ldrb(10, 10, 0xD0), 'ldrb w10, [x10, #0xd0]',
               'local flag byte pgd+0x40D0 (same byte)'),
]

seen = set()
for a, o, n, c in group:
    for i in range(4):
        assert a + i not in seen
        seen.add(a + i)

print('\n'.join(listing))

out = ['"""HOST_OUT_LIST: (offset_from_main, orig_hex, new_hex, is_code). Bytes little-endian as in memory.',
       'Generated by host_out_gen.py (original-word asserts, capstone check of every new word, no collision with',
       'patch_manager.cpp or any other diag/net/*_live.py, no branch into the changed words). Not live-tested.',
       'FALLBACK ONLY (host_out_notes.md): the static reading says the host already lists its own out player',
       '(stage 2 at EndPhase). Apply only if a live test shows the host own pgd+0x46B0 at stage 4 before its final',
       'EndPhase. Effect: the EndPhase list filler also lists stage-4 pgds whose reason byte has bit 2 set',
       '(04 04 / 04 05 / 04 06 / 04 07); 04 02 / 04 03 / 04 08 stay skipped as today. In place, no cave.',
       'Safe to apply on every game (guests never hold such a word before EndPhase) and to apply live',
       'outside EndPhase (one function, entered only from EndPhase 0x114C0F8)."""', '',
       'HOST_OUT_LIST = [']
for a, o, n, c in group:
    out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
out.append(']')
out.append('')
out.append('ORDER = [HOST_OUT_LIST]')
open(os.path.join(HERE, 'host_out_live.py'), 'w').write('\n'.join(out) + '\n')
print('host_out_live.py written')
