"""Generator + checker for events_live.py (groups C9 and SUBQUEST). Static only.
python events_gen.py  -> writes events_live.py next to this file and prints capstone listings / checks."""
import struct, os, capstone
from capstone import arm64_const as A

N = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
RO = open(os.path.join(N, 'main_ro.bin'), 'rb').read(); RO_BASE = 0x492B000
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM); md.detail = True

CAVE_LO, CAVE_HI = 0x563EB00, 0x563F000
ROLE = 0x492AFD8          # role byte: 0 = host
MGR3 = 0x5B3CE08          # pointer cell holding mgr3
MODE_OFF = 0x1268

# ---------------- encoders ----------------
def _rel(pc, t, bits):
    d = t - pc; assert d % 4 == 0; d //= 4
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'out of range'
    return d & ((1 << bits) - 1)
def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
COND = {'eq': 0, 'ne': 1}
def bcond(pc, t, c): return 0x54000000 | (_rel(pc, t, 19) << 5) | COND[c]
def cbz_w(pc, rt, t): return 0x34000000 | (_rel(pc, t, 19) << 5) | rt
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | rt
def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12); assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd
def ldr_x(rt, rn, off): assert off % 8 == 0 and 0 <= off < 0x8000; return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def ldr_w(rt, rn, off): assert off % 4 == 0 and 0 <= off < 0x4000; return 0xB9400000 | ((off // 4) << 10) | (rn << 5) | rt
def ldrb(rt, rn, off): assert 0 <= off < 0x1000; return 0x39400000 | (off << 10) | (rn << 5) | rt
def _pair(base, rt, rt2, rn, off): assert off % 8 == 0; return base | (((off // 8) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt
def stp_pre(rt, rt2, rn, off): return _pair(0xA9800000, rt, rt2, rn, off)
def ldp_post(rt, rt2, rn, off): return _pair(0xA8C00000, rt, rt2, rn, off)
def stp_off(rt, rt2, rn, off): return _pair(0xA9000000, rt, rt2, rn, off)
def ldp_off(rt, rt2, rn, off): return _pair(0xA9400000, rt, rt2, rn, off)
def add_xi(rd, rn, imm): assert 0 <= imm < 0x1000; return 0x91000000 | (imm << 10) | (rn << 5) | rd
def sub_xi(rd, rn, imm): assert 0 <= imm < 0x1000; return 0xD1000000 | (imm << 10) | (rn << 5) | rd
def cmp_wi(rn, imm): return 0x7100001F | (imm << 10) | (rn << 5)
def movz_w(rd, imm): assert 0 <= imm < 0x10000; return 0x52800000 | (imm << 5) | rd
def mov_xr(rd, rm): return 0xAA0003E0 | (rm << 16) | rd   # orr rd, xzr, rm
def blr(rn): return 0xD63F0000 | (rn << 5)
SP, FP, LR = 31, 29, 30

# ---------------- cave builders ----------------
class Cave:
    def __init__(s, at, name): s.at, s.name, s.w = at, name, []
    def pc(s): return s.at + 4 * len(s.w)
    def end(s): return s.pc()

def gate(at, name, prod, online):
    """w8 = offline flag. offline or host -> prod; guest -> online. Clobbers x9 only."""
    c = Cave(at, name); a = at
    c.w = [cbnz_w(a, 8, a + 0x10), adrp(a + 4, 9, ROLE), ldrb(9, 9, ROLE & 0xFFF),
           cbnz_w(a + 0xC, 9, a + 0x14), b(a + 0x10, prod), b(a + 0x14, online)]
    return c

def mgr3_mode6(c, skip_label_fix):
    """append: x8 = mgr3; if 0 or mode != 6 -> skip (patched later). returns indices to fix."""
    a = c.pc(); c.w += [adrp(a, 8, MGR3), ldr_x(8, 8, MGR3 & 0xFFF)]
    fix = [len(c.w)]; c.w.append(None)                       # cbz x8, skip
    c.w += [ldr_w(9, 8, MODE_OFF), cmp_wi(9, 6)]
    fix.append(len(c.w)); c.w.append(None)                   # b.ne skip
    return fix

def send_stub(at, name, mtype, length, tail):
    """bl hook target: broadcast (mgr3+0x10)->vt[+0x40](x0, type, x1_saved, length) in mode 6, then b tail."""
    c = Cave(at, name)
    c.w += [stp_pre(FP, LR, SP, -0x20), add_xi(FP, SP, 0), stp_off(0, 1, SP, 0x10)]
    fix = mgr3_mode6(c, None)
    c.w += [add_xi(0, 8, 0x10), ldr_x(9, 0, 0), ldr_x(9, 9, 0x40), movz_w(1, mtype),
            ldr_x(2, SP, 0x18), movz_w(3, length), blr(9)]
    skip = c.pc()
    c.w[fix[0]] = cbz_x(c.at + 4 * fix[0], 8, skip)
    c.w[fix[1]] = bcond(c.at + 4 * fix[1], skip, 'ne')
    c.w += [ldp_off(0, 1, SP, 0x10), ldp_post(FP, LR, SP, 0x20)]
    c.w.append(b(c.pc(), tail))
    return c

def reread_stub(at, name, func, tail):
    """bl hook target: guests only (mgr3, mode 6, role != 0) call func(); keep x0/x1; then b tail."""
    c = Cave(at, name)
    c.w += [stp_pre(FP, LR, SP, -0x20), add_xi(FP, SP, 0), stp_off(0, 1, SP, 0x10)]
    fix = mgr3_mode6(c, None)
    a = c.pc(); c.w += [adrp(a, 9, ROLE), ldrb(9, 9, ROLE & 0xFFF)]
    fix.append(len(c.w)); c.w.append(None)                   # cbz w9, skip (host)
    c.w.append(bl(c.pc(), func))
    skip = c.pc()
    c.w[fix[0]] = cbz_x(c.at + 4 * fix[0], 8, skip)
    c.w[fix[1]] = bcond(c.at + 4 * fix[1], skip, 'ne')
    c.w[fix[2]] = cbz_w(c.at + 4 * fix[2], 9, skip)
    c.w += [ldp_off(0, 1, SP, 0x10), ldp_post(FP, LR, SP, 0x20)]
    c.w.append(b(c.pc(), tail))
    return c

def align16(x): return (x + 15) & ~15

# ---------------- layout ----------------
caves = []
p = CAVE_LO
g_c9 = gate(p, 'gate_c9', 0x116ACE4, 0x116AE14); caves.append(g_c9); p = align16(g_c9.end())
s_c9 = send_stub(p, 'send_c9', 0xC9, 12, 0x116C0C0); caves.append(s_c9); p = align16(s_c9.end())
g_88 = gate(p, 'gate_88', 0x1181E4C, 0x1181E54); caves.append(g_88); p = align16(g_88.end())
s_88 = send_stub(p, 'send_88', 0x88, 0xB0, 0x1195C40); caves.append(s_88); p = align16(s_88.end())
r_88 = reread_stub(p, 'reread_88', 0x1195B00, 0x100AFE8); caves.append(r_88); p = align16(r_88.end())
assert p <= CAVE_HI, hex(p)

def word_at(a): return struct.unpack_from('<I', TXT, a)[0]
def ro_byte(a): return RO[a - RO_BASE]
def h(wd): return struct.pack('<I', wd).hex().upper()
def dis1(wd, at):
    i = next(md.disasm(struct.pack('<I', wd), at)); return f'{i.mnemonic} {i.op_str}'

# hooks / code edits: (addr, expected orig disasm, new word, comment)
C9_CODE = [
    (0x116AC54, 'mov x2, x22', sub_xi(2, FP, 0xD0), 'C9 guest: read raw record straight into x29-0xd0'),
    (0x116AC58, 'ldr x8, [x8, #0x60]', ldr_x(8, 8, 0x50), 'C9 guest: read from anyone (+0x60 -> +0x50)'),
    (0x116AC78, 'blr x8', movz_w(0, 1), 'C9 guest: skip parser, report success'),
    (0x116B6B8, 'bl #0x116c0c0', bl(0x116B6B8, s_c9.at), 'C9 host: bl send_c9 (broadcast, then 0x116C0C0)'),
    (0x116ACE0, 'cbz w8, #0x116ae14', b(0x116ACE0, g_c9.at), 'C9 gate: b gate_c9 (apply last)'),
]
C9_DATA = [(0x4C4B9F8, 0x60, 0x20, 'C9 routing 0xC9: 0x60 -> 0x20')]
SQ_CODE = [
    (0x1195BB4, 'mov x2, x20', mov_xr(2, 23), '0x88 guest: read raw record straight into sp (x23)'),
    (0x1195BB8, 'ldr x8, [x8, #0x60]', ldr_x(8, 8, 0x50), '0x88 guest: read from anyone (+0x60 -> +0x50)'),
    (0x1195BD8, 'blr x8', movz_w(0, 1), '0x88 guest: skip parser, report success'),
    (0x1196404, 'bl #0x1195c40', bl(0x1196404, s_88.at), '0x88 host: bl send_88 (broadcast, then 0x1195C40)'),
    (0x1140B10, 'bl #0x100afe8', bl(0x1140B10, r_88.at), '0x88 guest: per-frame bl reread_88'),
    (0x1181E48, 'cbz w8, #0x1181e54', b(0x1181E48, g_88.at), '0x88 gate: b gate_88 (apply last)'),
]
SQ_DATA = [(0x4C4B7F0, 0x02, 0x22, '0x88 routing: 0x02 -> 0x22')]

errors = []
def check_code(lst):
    for a, exp, new, cm in lst:
        got = dis1(word_at(a), a)
        if got != exp: errors.append(f'{a:#x}: binary has "{got}", expected "{exp}"')
def check_data(lst):
    for a, o, n, cm in lst:
        if ro_byte(a) != o: errors.append(f'{a:#x}: ro byte {ro_byte(a):#x} != {o:#x}')
check_code(C9_CODE); check_code(SQ_CODE); check_data(C9_DATA); check_data(SQ_DATA)
for c in caves:
    off = c.at - RO_BASE
    assert off >= len(RO), 'cave inside ro file'   # beyond file end -> zero-filled
    assert c.at >= CAVE_LO and c.end() <= CAVE_HI

# ---------------- listings ----------------
def listing(c):
    out = []
    for k, wd in enumerate(c.w):
        a = c.at + 4 * k; out.append(f'  {a:#x}: {h(wd)}  {dis1(wd, a)}')
    return '\n'.join(out)

print(f'caves {CAVE_LO:#x}..{p:#x} ({p - CAVE_LO} bytes incl. alignment)')
for c in caves:
    print(f'{c.name} @ {c.at:#x} ({4 * len(c.w)} bytes)'); print(listing(c))
print('hooks / edits:')
for a, exp, new, cm in C9_CODE + SQ_CODE:
    print(f'  {a:#x}: {h(word_at(a))} "{exp}" -> {h(new)} "{dis1(new, a)}"   ; {cm}')
for a, o, n, cm in C9_DATA + SQ_DATA:
    print(f'  {a:#x}: {o:02X} -> {n:02X}  ; {cm}')

# ---------------- liveness checks: callee arg regs read before written ----------------
ARGS = {f'x{i}' for i in range(8)} | {f'w{i}' for i in range(8)} | {f'{p}{i}' for p in 'sdqvbh' for i in range(8)}
def canon(r):
    return ('x' if r[0] in 'xw' else 'v') + r[1:]
def args_read(fn, limit=0x400):
    """paths from fn entry until first call/ret: arg regs read before written."""
    seen, res, work = set(), set(), [(fn, frozenset())]
    while work:
        a, wr = work.pop()
        while True:
            if (a, wr) in seen or a > fn + limit: break
            seen.add((a, wr))
            i = next(md.disasm(TXT[a:a + 4], a))
            rd, wt = i.regs_access()
            for r in rd:
                n = i.reg_name(r)
                if n in ARGS and canon(n) not in wr: res.add((hex(a), n))
            wr = wr | {canon(i.reg_name(r)) for r in wt}
            m = i.mnemonic
            if m in ('bl', 'blr', 'ret', 'retab', 'br') or m.startswith('udf'): break
            if m == 'b' or m.startswith('b.') or m in ('cbz', 'cbnz', 'tbz', 'tbnz'):
                t = i.operands[-1].imm
                if m == 'b': a = t; continue
                work.append((t, wr))
            a += 4
    return sorted(res)
for fn in (0x116C0C0, 0x1195C40, 0x100AFE8, 0x1195B00):
    r = [x for x in args_read(fn) if canon(x[1]) not in ('x0', 'x1')]
    print(f'args other than x0/x1 read by {fn:#x} before its first call: {r or "none"}')

# x9 dead after the gate targets (written before read on the straight path)
def first_use(a, reg, n=40):
    for k in range(n):
        i = next(md.disasm(TXT[a:a + 4], a)); rd, wt = i.regs_access()
        names_r = {canon(i.reg_name(r)) for r in rd}; names_w = {canon(i.reg_name(r)) for r in wt}
        if reg in names_r: return f'READ at {a:#x} ({i.mnemonic} {i.op_str})'
        if reg in names_w: return f'written at {a:#x} ({i.mnemonic} {i.op_str})'
        if i.mnemonic in ('bl', 'blr'): return f'clobbered by call at {a:#x}'
        if i.mnemonic == 'b': a = i.operands[0].imm; continue
        a += 4
    return 'undecided'
for t in (0x116ACE4, 0x116AE14, 0x1181E4C, 0x1181E54):
    print(f'x9 after {t:#x}: {first_use(t, "x9")}')

if errors:
    print('ERRORS:'); print('\n'.join(errors)); raise SystemExit(1)
print('all originals match the binary')

# ---------------- write events_live.py ----------------
def recs_cave(c, tag):
    return [(c.at + 4 * k, '00000000', h(wd), True, f'{c.name} ({tag})') for k, wd in enumerate(c.w)]
def recs_code(lst): return [(a, h(word_at(a)), h(new), True, cm) for a, e, new, cm in lst]
def recs_data(lst): return [(a, f'{o:02X}', f'{n:02X}', False, cm) for a, o, n, cm in lst]

groups = [
    ('C9_CAVES', 'C9 caves (inert until hooked)', recs_cave(g_c9, 'offline/host -> producer, guest -> online') + recs_cave(s_c9, 'broadcast 0xC9, 12 bytes')),
    ('C9', 'C9 routing + guest read + hooks (gate last)', recs_data(C9_DATA) + recs_code(C9_CODE)),
    ('SUBQUEST_CAVES', '0x88 caves (inert until hooked)', recs_cave(g_88, 'offline/host -> producer, guest -> reader') + recs_cave(s_88, 'broadcast 0x88, 0xB0 bytes') + recs_cave(r_88, 'guest per-frame re-read')),
    ('SUBQUEST', '0x88 routing + guest read + hooks (gate last)', recs_data(SQ_DATA) + recs_code(SQ_CODE)),
]
L = ['"""Paste-ready patch records: (offset_from_main, orig_hex, new_hex, is_code). Bytes are little-endian as in memory.',
     f'Cave records have orig "00000000" (zero padding past the ro file end; this set uses 0x{CAVE_LO:X}..0x{p - 1:X}).',
     'Apply each group in list order; within a group the hook that makes it live comes last.',
     'Generated by events_gen.py (encoders + capstone check + original-word check against diag/net/nso). Not live-tested."""', '']
for var, title, recs in groups:
    L.append(f'{var} = [  # {title}')
    for a, o, n, ic, cm in recs:
        L.append(f'    ({a:#09X}, "{o}", "{n}", {ic}),  # {cm}'.replace('0X', '0x', 1))
    L.append(']')
L.append('')
L.append('ORDER = [C9_CAVES, C9, SUBQUEST_CAVES, SUBQUEST]  # 0xDA (TIMED) intentionally not included')
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'events_live.py'), 'w', newline='\n').write('\n'.join(L) + '\n')
print('wrote events_live.py,', sum(len(g[2]) for g in groups), 'records')
