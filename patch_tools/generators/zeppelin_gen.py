"""Generator + checker for the ZEPPELIN_* groups in zeppelin_live.py. Static only (reads nso/*.bin,
src/lichii/src/core/file_sys/patch_manager.cpp and every diag/net/*_live.py; writes zeppelin_live.py,
prints a capstone listing). UNTESTED: nothing here was run in a game.
python zeppelin_gen.py

Design B of startarea_zeppelin_notes.md (B4): the host decides airship (zeppelin, env 0x0A) support.
"HOST byte" = main+0x492AFD8 (GENERATOR_IDLE in dusk_lan.cpp): 0 = this game is the authority.
  ZEPPELIN_GRANT      B1: 0xF0DB7C..88 support-goods grant at PrepareSecond: offline gate -> host only.
  ZEPPELIN_GRANT_ALL  alternative to B1 (one nop at 0xF0DB88: every game grants). Same word as
                      ZEPPELIN_GRANT: apply ONE of the two, never both.
  ZEPPELIN_ROUTE      B2 + B2b: 0x9E attribute 0x40 (server) -> 0x20 (players) and the sender 0xF107F0..F8:
                      the host loops its own request back, guests send theirs to the players.
  ZEPPELIN_STORE      B3: 0xF11EDC..EC the 0x9E receiver stores kind-0 requests on the host only.
  ZEPPELIN_DECIDE     B4: 0xF11174..7C the decision 0xF11140 runs on the host only.
No cave: B4b (decide REMOTE requests on the host) is left out. The notes' candidate 0x703660..0x7036CC
is not proven free (a u32 0x703660 sits in a ro table at 0x508E3E0, see cave_candidate() below), so
guests' requests reach the host's queue but are only decided if something calls 0xF11140 for them."""
import glob
import importlib.util
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
N = os.path.join(HERE, 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
RO = open(os.path.join(N, 'main_ro.bin'), 'rb').read()
DATA = open(os.path.join(N, 'main_data.bin'), 'rb').read()
RO_BASE = 0x492B000
DATA_BASE = 0x563F000
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

HOST_BYTE = 0x492AFD8      # 0 = host (dusk_lan.cpp GENERATOR_IDLE; read by cave 3 the same way)

# ---------------------------------------------------------------- shipped records (patch_manager.cpp)
src = open(PM, encoding='utf-8', errors='ignore').read()
arrays = {}
for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
    n, name, body = int(m.group(1)), m.group(2), m.group(3)
    vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
    arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
shipped = {}   # byte address -> record name
for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
    a, name = int(m.group(1), 16), m.group(2)
    if name not in arrays:
        continue
    for i in range(len(arrays[name])):
        shipped[a + i] = name
print('shipped bytes parsed: %d' % len(shipped))

# ---------------------------------------------------------------- every other helper's live groups
ME = 'zeppelin_live.py'
others = {}
for path in sorted(glob.glob(os.path.join(HERE, '*_live.py'))):
    fn = os.path.basename(path)
    if fn == ME:
        continue
    spec = importlib.util.spec_from_file_location(fn[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for g, v in vars(mod).items():
        if not (isinstance(v, list) and v and all(isinstance(r, tuple) and len(r) == 4 for r in v)):
            continue
        for a, o, nw, c in v:
            for i in range(len(nw) // 2):
                others.setdefault(a + i, '%s:%s' % (fn, g))
print('other live-group bytes parsed: %d' % len(others))


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def dis1(addr, w):
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


def ldrb_w(rt, rn, off): return 0x39400000 | (off << 10) | (rn << 5) | rt


def _imm19(pc, t):
    d = t - pc
    assert d % 4 == 0 and -(1 << 20) <= d < (1 << 20)
    return ((d // 4) & 0x7FFFF) << 5


def cbz_w(pc, rt, t): return 0x34000000 | _imm19(pc, t) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | _imm19(pc, t) | rt


NOP = 0xD503201F
HB_PAGE, HB_OFF = HOST_BYTE & ~0xFFF, HOST_BYTE & 0xFFF

listing = []
groups = {}


def text_patch(addr, expect, new, note):
    old = word(addr)
    got = dis1(addr, old)
    assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
    assert not any(addr + i in shipped for i in range(4)), 'collides with shipped %s at %x' % (shipped.get(addr), addr)
    listing.append('  0x%x  %s  ->  %s   (%s)' % (addr, got, dis1(addr, new), note))
    return (addr, hexw(old), hexw(new), True)


def context(pairs):
    for a, t in pairs:
        assert dis1(a, word(a)) == t, (hex(a), dis1(a, word(a)), t)
        listing.append('  context 0x%x  %s' % (a, t))


def host_byte_gate(a_adrp, a_ldrb, a_nop, a_branch, expect, target, skip_if_guest):
    """adrp x8, HOST page; ldrb w8, [x8, #off]; [nop]; cbnz/cbz w8 -> target. Returns the new words."""
    ws = [(a_adrp, adrp(a_adrp, 8, HB_PAGE)), (a_ldrb, ldrb_w(8, 8, HB_OFF))]
    if a_nop is not None:
        ws.append((a_nop, NOP))
    ws.append((a_branch, (cbnz_w if skip_if_guest else cbz_w)(a_branch, 8, target)))
    for (a, w), (ea, e) in zip(ws, expect):
        assert a == ea
    return ws


# ---------------------------------------------------------------- the notes' cave candidate
def cave_candidate(lo=0x703660, hi=0x7036CC):
    """Every static way to reach lo..hi: b/bl/b.cond/cbz/tbz/adr/adrp+add in text, raw 8-byte pointers in
    ro/data (this NSO stores data pointers resolved, e.g. vtable 0x56F2580 -> 0x10EE028), raw u32 values."""
    hits = []
    for o in range(0, len(TXT) - 3, 4):
        w = struct.unpack_from('<I', TXT, o)[0]
        t = None
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            t = o + ((imm ^ 0x2000000) - 0x2000000) * 4
        elif (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000:
            imm = (w >> 5) & 0x7FFFF
            t = o + ((imm ^ 0x40000) - 0x40000) * 4
        elif (w & 0x7E000000) == 0x36000000:
            imm = (w >> 5) & 0x3FFF
            t = o + ((imm ^ 0x2000) - 0x2000) * 4
        elif (w & 0x9F000000) in (0x10000000, 0x90000000):
            imm = ((w >> 29) & 3) | (((w >> 5) & 0x7FFFF) << 2)
            imm = (imm ^ 0x100000) - 0x100000
            if w & 0x80000000:
                page = (o & ~0xFFF) + (imm << 12)
                if page == lo & ~0xFFF:
                    hits.append(('adrp to the page', o))
            else:
                t = o + imm
        if t is not None and lo <= t < hi and not lo <= o < hi:
            hits.append(('branch/adr', o))
    for seg, base, nm in ((RO, RO_BASE, 'ro'), (DATA, DATA_BASE, 'data')):
        for o in range(0, len(seg) - 7, 4):
            if lo <= struct.unpack_from('<Q', seg, o)[0] < hi:
                hits.append(('%s u64' % nm, base + o))
        for o in range(0, len(seg) - 3, 4):
            if lo <= struct.unpack_from('<I', seg, o)[0] < hi:
                hits.append(('%s u32' % nm, base + o))
    return hits


cand = cave_candidate()
listing.append('cave candidate 0x703660..0x7036CC: %s' % (
    ', '.join('%s @0x%X' % h for h in cand) if cand else 'no reference'))
CAVE_USABLE = not cand
listing.append('  -> %s' % ('free' if CAVE_USABLE else 'NOT used (a value in range exists; B4b left out)'))

# ================================================================ ZEPPELIN_GRANT (B1, host only)
listing.append('=== ZEPPELIN_GRANT')
context(((0xF0DB78, 'cbz x8, #0xf0dc30'), (0xF0DB8C, 'mov x19, x0'), (0xF0DB98, 'ldr x8, [sp, #8]'),
         (0xF0DC30, 'ldp x20, x19, [sp, #0x50]')))
g = host_byte_gate(0xF0DB7C, 0xF0DB80, 0xF0DB84, 0xF0DB88,
                   [(0xF0DB7C, 0), (0xF0DB80, 0), (0xF0DB84, 0), (0xF0DB88, 0)], 0xF0DC30, True)
exp = ['adrp x8, #0x5b65000', 'ldr x8, [x8, #0xc20]', 'ldrb w8, [x8, #0xbda]', 'cbz w8, #0xf0dc30']
why = ['HOST page', 'HOST byte', '(bda load gone)', 'guest: skip the grant']
groups['ZEPPELIN_GRANT'] = [text_patch(a, e, w, n) for (a, w), e, n in zip(g, exp, why)]

# ================================================================ ZEPPELIN_GRANT_ALL (alternative to B1)
listing.append('=== ZEPPELIN_GRANT_ALL (alternative: apply instead of ZEPPELIN_GRANT)')
groups['ZEPPELIN_GRANT_ALL'] = [text_patch(0xF0DB88, 'cbz w8, #0xf0dc30', NOP, 'every game grants')]

# ================================================================ ZEPPELIN_ROUTE (B2 route + B2b sender)
listing.append('=== ZEPPELIN_ROUTE')
ROUTE = 0x4C4B8A0                     # 0x4C4B3B0 + 0x9E * 8: the 0x9E attribute byte
ro = ROUTE - RO_BASE
assert struct.unpack_from('<I', RO, ro - 4)[0] == 0x9E, 'table entry before 0x4C4B8A0 is not id 0x9E'
assert struct.unpack_from('<I', RO, ro + 4)[0] == 0x9F, 'table entry after is not id 0x9F'
assert RO[ro] == 0x40, 'route byte is %02x, expected 40' % RO[ro]
assert ROUTE not in shipped and ROUTE not in others
listing.append('  0x%X  route 0x9E: 40 (server only) -> 20 (players)  (data)' % ROUTE)
context(((0xF107EC, 'cbz x19, #0xf10a58'), (0xF107FC, 'adrp x8, #0x56e6000'), (0xF108D4, 'mov w1, #0x9e'),
         (0xF108F0, 'adrp x8, #0x56e6000')))
g = host_byte_gate(0xF107F0, 0xF107F4, None, 0xF107F8,
                   [(0xF107F0, 0), (0xF107F4, 0), (0xF107F8, 0)], 0xF108F0, False)
exp = ['ldr w8, [x19, #0x1268]', 'cmp w8, #6', 'b.ne #0xf108f0']
why = ['HOST page', 'HOST byte', 'host: loop the request back; guest: send 0x9E']
groups['ZEPPELIN_ROUTE'] = [(ROUTE, '40', '20', False)] + [text_patch(a, e, w, n) for (a, w), e, n in zip(g, exp, why)]

# ================================================================ ZEPPELIN_STORE (B3)
listing.append('=== ZEPPELIN_STORE')
context(((0xF11ED8, 'b #0xf1209c'), (0xF11EE0, 'add x23, sp, #0x30'), (0xF11EF0, 'ldp x8, x9, [x19, #0x110]'),
         (0xF122CC, 'ldr x8, [x24]')))
g = host_byte_gate(0xF11EDC, 0xF11EE4, 0xF11EE8, 0xF11EEC,
                   [(0xF11EDC, 0), (0xF11EE4, 0), (0xF11EE8, 0), (0xF11EEC, 0)], 0xF122CC, True)
exp = ['adrp x8, #0x5b65000', 'ldr x8, [x8, #0xc20]', 'ldrb w8, [x8, #0xbda]', 'cbz w8, #0xf122cc']
why = ['HOST page', 'HOST byte (x23 at 0xF11EE0 kept)', '(bda load gone)', 'guest: do not store kind 0']
groups['ZEPPELIN_STORE'] = [text_patch(a, e, w, n) for (a, w), e, n in zip(g, exp, why)]

# ================================================================ ZEPPELIN_DECIDE (B4)
listing.append('=== ZEPPELIN_DECIDE')
context(((0xF11170, 'adrp x22, #0x5b65000'), (0xF11188, 'bl #0xf11d20'), (0xF11238, 'mov w21, wzr'),
         (0xF11544, 'ldr x8, [x22, #0xc20]')))       # later x22 use: x22 is not touched
g = host_byte_gate(0xF11174, 0xF11178, None, 0xF1117C,
                   [(0xF11174, 0), (0xF11178, 0), (0xF1117C, 0)], 0xF11238, True)
exp = ['ldr x8, [x22, #0xc20]', 'ldrb w8, [x8, #0xbda]', 'cbz w8, #0xf11238']
why = ['HOST page', 'HOST byte', 'guest: no decision']
groups['ZEPPELIN_DECIDE'] = [text_patch(a, e, w, n) for (a, w), e, n in zip(g, exp, why)]

# not patched, for the lead: the item-grant function's own bda gate (shared item code)
listing.append('  not patched: 0x%x %s (0xCF8E2C own bda gate; check live first)' % (0xCF8EEC, dis1(0xCF8EEC, word(0xCF8EEC))))

# ---------------------------------------------------------------- overlaps
ALTERNATIVES = {frozenset(('ZEPPELIN_GRANT', 'ZEPPELIN_GRANT_ALL'))}
seen = {}
for gname, rs in groups.items():
    for a, o, nw, c in rs:
        for i in range(len(nw) // 2):
            if a + i in seen:
                assert frozenset((gname, seen[a + i])) in ALTERNATIVES, 'overlap %x (%s, %s)' % (a + i, gname, seen[a + i])
            else:
                seen[a + i] = gname
            assert a + i not in shipped, 'collides with shipped %s at %x' % (shipped[a + i], a + i)
            assert a + i not in others, 'collides with %s at %x' % (others[a + i], a + i)
listing.append('no overlap with shipped records or other *_live.py groups (GRANT / GRANT_ALL are alternatives)')

print('\n'.join(listing))

ORDER = ['ZEPPELIN_GRANT', 'ZEPPELIN_ROUTE', 'ZEPPELIN_STORE', 'ZEPPELIN_DECIDE']
out = ['"""UNTESTED zeppelin (airship support, event 1120) groups: (offset_from_main, orig_hex, new_hex, is_code).',
       'Bytes little-endian as in memory. Generated by zeppelin_gen.py (original-word checks, capstone listing,',
       'collision checks against patch_manager.cpp and every other diag/net/*_live.py). NOT run in any game.',
       'Notes: startarea_fix_notes.md (what the lead must check) and startarea_zeppelin_notes.md B4.',
       'HOST byte = main+0x492AFD8 (0 = host). Apply on EVERY game. ZEPPELIN_GRANT_ALL is an ALTERNATIVE to',
       'ZEPPELIN_GRANT (same word 0xF0DB88): apply one, never both. No cave: remote requests are queued on the',
       'host but nothing decides them yet (B4b left out)."""', '']
notes = {
    'ZEPPELIN_GRANT': 'B1 support goods granted at PrepareSecond on the host only',
    'ZEPPELIN_GRANT_ALL': 'B1 alternative: every game grants (nop the bda gate); NOT with ZEPPELIN_GRANT',
    'ZEPPELIN_ROUTE': 'B2 0x9E to the players (data) + B2b host loops back, guests send',
    'ZEPPELIN_STORE': 'B3 kind-0 0x9E requests stored on the host only',
    'ZEPPELIN_DECIDE': 'B4 decision 0xF11140 on the host only',
}
for gname in ORDER + ['ZEPPELIN_GRANT_ALL']:
    out.append('%s = [  # UNTESTED: %s' % (gname, notes[gname]))
    for a, o, nw, c in groups[gname]:
        out.append('    (0x%X, "%s", "%s", %s),' % (a, o, nw, c))
    out.append(']')
out.append('')
out.append('ORDER = [%s]  # ZEPPELIN_GRANT_ALL not in ORDER (alternative)' % ', '.join(ORDER))
open(os.path.join(HERE, ME), 'w').write('\n'.join(out) + '\n')
print(ME + ' written')
