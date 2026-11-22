"""zep3_gen.py: zeppelin support (event 1120) new code C1 / C2 / C3 of zeppelin2_notes.md section 4, built on
the far cave region with cave_lib. Static only: reads nso/*.bin, patch_manager.cpp, every *_live.py and
cave_registry.md; claims its ranges (owner zep3_gen, stable on re-runs); writes zep3_live.py; prints a capstone
listing and the patch_manager.cpp rows.        python zep3_gen.py [--dry]      (run from diag/net)
Notes: zep3_notes.md. In-place words: zeppelin_nc_live.py ZEP_S1..ZEP_S7 (not touched here, no shared word).

  ZEP3_C1  hook 0xF0C52C `bl 0xF11D20` (pump 0xF0BEC0) -> bl tramp -> C1: original drain, then (not offline) the
           decision 0xF11140(AS, &playerNo of the FIRST queued request); then, only if ZEP3_C3 is present
           (its last word != 0), C3(AS, playerNo). Returns to 0xF0C530.
  ZEP3_C2  hook 0xCF8F74 (bda gate of the item add 0xCF8E2C) -> b tramp -> C2: offline unchanged; LAN: one
           loop over a zero-terminated table of RETURN-ADDRESS OFFSETS (from main) in far data (C2_TABLE,
           FAR_DATA). Table today = forge 0x11A076C (= shipped FORGE_OWN) + zeppelin grant 0xF16198. The other
           16 callers stay refused (grantgate_notes.md: 12 have their own +0xBDA gate upstream, 4 are item-server
           paths that only the authority runs and that credit a possibly remote player's copy).
           W1 (sigil4_notes.md): when the plain table misses, C2 branches to C2L, which scans a second table
           (ZEP3_C2_LOCAL: sigil perfume 0x1179AB0 / 0x117A17C) and grants only when the receiving player
           [x19] == local pgd+0xD0. Hook word, trampoline and C2 address unchanged.
           SUPERSEDES the shipped FORGE_OWN hook word 0xCF8F74 (`b 0xCF0E84`): the built-in record
           DUSK_W_CF8F74 is UPDATED, not added. FORGE_OWN_CAVE words 0xCF0E84.. become unreferenced (harmless).
  ZEP3_C3  host: rebuild 0xF102C0's frame, 0x9E kind 1 {player, strike +8..+0x1B} to the players via the native
           send block 0xF107FC; exit through the native epilogue 0xF109EC. Only called by C1 (no text hook).
  ZEP3_D1  guests (kind-1 path after S6): hook 0xF11EA4 in the 0x9E drain. A granted kind-1 strike (result byte
           != 0) whose airship is already BUSY on this game (+0x38, set when this game fired it, cleared by the
           0xA1 end) is dropped: a repeated 0x9E (echo, resend) cannot give a second volley. Denied strikes and
           strikes for a free ship are stock. No mutable far data: the game's own busy byte is the strike key."""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

OUT = 'zep3_live.py'
DRY = '--dry' in sys.argv
g = C.Gen('zep3_gen', out=OUT, dry=DRY)

# ---------------------------------------------------------------- globals / addresses [V]
OFFL = 0x5B65C20      # *(OFFL)+0xBDA != 0: offline (0xF11170..0xF1117C stock, 0xCF8F68..0xCF8F70)
NETG = 0x5B3CE08      # *(NETG) = net manager (0xF107E0..0xF107E8)
HOST = 0x492AFD8      # HOST byte, 0 = host (zeppelin_nc_live S3..S6 use the same adrp/ldrb)
DRAIN, DECIDE = 0xF11D20, 0xF11140
SEND_IN, SEND_EPI = 0xF107FC, 0xF109EC
FORGE_RET, ZEP_RET = 0x11A076C, 0xF16198
GRANT, DENY = 0xCF8F78, 0xCF8FE4
# C2 table: return-address offsets that may pass the 0xCF8F74 gate in LAN (grantgate_notes.md section 2)
C2_ACCEPT = [FORGE_RET, ZEP_RET]
C2_TABLE_WORDS = 8                  # room for 7 offsets + 0 terminator (registry claim; only used words get records)
# W1 (sigil4_notes.md): callers that may pass ONLY when the receiving player [x19] (= x1 of 0xCF8E2C, {player no})
# is the local player of this game (*(GDM)+0x20 = local pgd, +0xD0 = player no). Sigil start / phase perfume:
# 0x1179970 / 0x1179EB8 run on every game for every module, so without the test every game would give every
# player's perfume. Second table ZEP3_C2_LOCAL, scanned by the C2L cave after the plain table missed.
GDM = 0x5B57EB8
SIGIL_START_RET, SIGIL_PHASE_RET = 0x1179AB0, 0x117A17C
C2_LOCAL = [SIGIL_START_RET, SIGIL_PHASE_RET]
C2_LOCAL_WORDS = 4                  # 3 offsets + 0 terminator
# every `bl 0xCF8E2C` in text (return address = site + 4), verified by a full text scan below
ITEM_ADD = 0xCF8E2C
ALL_CALLERS = [0xCF6FE0, 0xCF936C, 0xD4A2E4, 0xD4A6E0, 0xD52F30, 0xD53290, 0xF0FC40, 0xF16194, 0x1179AAC,
               0x117A178, 0x119123C, 0x11921D8, 0x119FFF0, 0x11A0768, 0x15A34A8, 0x15AF628, 0x15B2644, 0x15B4A9C]
# refused callers whose call is behind their own +0xBDA (offline) test: (call site, gate word, gate text)
UPSTREAM_GATE = [
    (0xCF6FE0, 0xD0123C, None),            # 0xCF6D10 runs only when mode != 6 (0xD01234..0xD0123C, notes)
    (0xCF936C, 0xCF934C, 'cbz w8, #0xcf9374'),
    (0xD4A2E4, 0xD4A2A8, 'cbz w9, #0xd4a328'),
    (0xD4A6E0, 0xD4A694, 'cbz w9, #0xd4a5a0'),
    (0xD52F30, 0xD52EDC, 'cbz w8, #0xd52f60'),
    (0xD53290, 0xD5323C, 'cbz w8, #0xd532c0'),
    (0xF0FC40, 0xF0FC18, 'cbz w8, #0xf0fe64'),
    (0x1179AAC, 0x117999C, 'cbz w8, #0x1179ab0'),
    (0x117A178, 0x1179F04, 'b.ne #0x117a17c'),   # cmp bda,#0; ccmp w9,#0,#0,ne: bda 0 -> skip
    (0x119123C, 0x119114C, 'cbz w8, #0x1191240'),
    (0x11921D8, 0x1191F6C, 'cbz w8, #0x1192200'),
    (0x119FFF0, 0x119FE7C, 'cbz w8, #0x119fff4')]
# refused item-server callers (run on the item authority only, recipient = a requester / chr that may be remote)
SERVER_PATHS = [0x15A34A8, 0x15AF628, 0x15B2644, 0x15B4A9C]


def stp_w(rt, rt2, rn, off):        # 32-bit pair, signed offset
    assert off % 4 == 0 and -256 <= off < 256
    return 0x29000000 | (((off // 4) & 0x7F) << 15) | (C.R(rt2) << 10) | (C.R(rn) << 5) | C.R(rt)


assert C.dis1(0, stp_w('w10', 'w1', 'sp', 0)) == 'stp w10, w1, [sp]'


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def func_range(s):
    assert C.text_word(s) == 0xD503237F, 'no pacibsp at %x' % s
    e = s + 4
    while C.text_word(e) != 0xD503237F:
        e += 4
    return s, e


def ip_uses(s):
    """(function range, list of (addr, text) naming x16/x17/w16/w17)."""
    s, e = func_range(s)
    hits = []
    for a in range(s, e, 4):
        t = C.dis1(a, C.text_word(a))
        if re.search(r'\b[xw]1[67]\b', t):
            hits.append((a, t))
    return (s, e), hits


# ---------------------------------------------------------------- stock context [V]
for a, t in (
        # pump 0xF0BEC0: x19 = AS for the whole pump, x0 = AS at the call, the call itself
        (0xF0BF04, 'mov x19, x0'), (0xF0C520, 'ldrb w8, [x19, #8]'), (0xF0C524, 'mov x0, x19'),
        (0xF0C528, 'str w8, [sp, #0x20]'), (0xF0C52C, 'bl #0xf11d20'), (0xF0C530, 'ldp x22, x23, [x19, #0x130]'),
        # decision 0xF11140(x0 = AS, x1 = &u32 player no); queue AS+0x110/0x118, 0x38 each, +0 player no
        (0xF11140, 'pacibsp'), (0xF11180, 'mov x21, x1'), (0xF11184, 'mov x19, x0'), (0xF11188, 'bl #0xf11d20'),
        (0xF1118C, 'ldp x20, x8, [x19, #0x110]'), (0xF11198, 'ldr w9, [x21]'), (0xF111A0, 'ldr w10, [x20]'),
        (0xF111AC, 'add x20, x20, #0x38'), (0xCF6E24, 'mov x1, x20'), (0xCF6E28, 'bl #0xf11140'),
        # item add 0xCF8E2C: frame, gate, grant / deny targets, both callers
        (0xCF8E2C, 'pacibsp'), (0xCF8E30, 'stp x29, x30, [sp, #-0x60]!'), (0xCF8E38, 'mov x29, sp'),
        (0xCF8F68, 'adrp x8, #0x5b65000'), (0xCF8F70, 'ldrb w8, [x8, #0xbda]'), (0xCF8F74, 'cbz w8, #0xcf8fe4'),
        (0xCF8F78, 'add x8, sp, #0x10'), (0xCF8F84, 'bl #0xcf3f08'), (0xCF8FE4, 'mov w25, wzr'),
        (0xCF8FE8, 'b #0xcf92c8'), (0xCF92C8, 'mov w0, w25'),
        (0xF16194, 'bl #0xcf8e2c'), (0x11A0768, 'bl #0xcf8e2c'),
        # request builder 0xF102C0: prologue (copied by C3), net mgr, send block, epilogue
        (0xF107E0, 'adrp x8, #0x5b3c000'), (0xF107E4, 'add x8, x8, #0xe08'), (0xF107E8, 'ldr x19, [x8]'),
        (0xF107FC, 'adrp x8, #0x56e6000'), (0xF10804, 'mov x9, sp'), (0xF10864, 'mov x0, sp'),
        (0xF10868, 'stur x20, [x29, #-0x90]'), (0xF10874, 'bl #0xf0b618'), (0xF10898, 'add x19, x19, #0x10'),
        (0xF108D4, 'mov w1, #0x9e'), (0xF108DC, 'ldr x8, [x8, #0x48]'), (0xF108E0, 'blr x8'),
        (0xF108E4, 'ldr x1, [sp, #0x18]'), (0xF108E8, 'cbnz x1, #0xf109d8'), (0xF108EC, 'b #0xf109ec'),
        (0xF109D8, 'ldr x0, [sp, #0x30]'), (0xF109EC, 'add sp, sp, #0x160'), (0xF10A18, 'retab'),
        # serializer 0xF0B618 kind 1: +0 kind, +4 player, +0x38 byte, +0x3C vec3, +0x48 u16, +0x4A u16
        (0xF0B63C, 'ldr w21, [x0]'), (0xF0B6C0, 'ldrb w1, [x20, #0x38]'), (0xF0B6D0, 'add x1, x20, #0x3c'),
        (0xF0B6E4, 'add x0, x20, #0x48'), (0xF0B6F4, 'add x0, x20, #0x4a'),
        # reader kind 1 copies record +0x38..+0x4B to strike +8..+0x1B, strike stride 0x20, pending +0x1C
        (0xF12080, 'ldp x8, x10, [x11]'), (0xF12084, 'ldr w11, [x11, #0x10]'), (0xF12088, 'stp x8, x10, [x9, #8]'),
        (0xF12090, 'str w11, [x9, #0x18]'), (0xF12094, 'strb w8, [x9, #0x1c]'), (0xF11ECC, 'add x9, x9, #0x20'),
        (0xF11EA4, 'ldp x9, x8, [x19, #0x130]'),
        # 0xCF8E2C epilogue after the deny target (C2 clobbers x9..x12 + flags: none read on either path)
        (0xCF92C8, 'mov w0, w25'), (0xCF92E8, 'retab'),
        # D1 context: 0x9E drain 0xF11D20 (x19 = AS), kind-1 body pointer [sp+0x28] = record +0x38,
        # strike copy (ship id = body +0x10 -> strike +0x18), next-message target 0xF122CC
        (0xF11D58, 'mov x19, x0'), (0xF11DE8, 'add x10, x10, #0x38'), (0xF11DF0, 'stp x9, x10, [sp, #0x20]'),
        (0xF11E00, 'add x22, x8, #0x10'), (0xF11E88, 'cmp w8, #1'), (0xF11EA8, 'ldr w10, [sp, #0x34]'),
        (0xF1207C, 'ldr x11, [sp, #0x28]'), (0xF1209C, 'ldr x11, [sp, #0x28]'), (0xF122CC, 'ldr x8, [x24]'),
        (0xF122D0, 'cbnz x8, #0xf11e00'),
        # airship list AS+0xF0 (0x40 each, +0 u16 id, +0x38 busy): pump fire sets busy via 0xF12440 rec+0x30 = 1,
        # the 0xA1 end handler writes rec+0x30 = 0; decision 0xF11140 refuses a busy ship (0xF11734)
        (0xF0CD00, 'ldp x8, x9, [x19, #0xf0]'), (0xF0CD20, 'ldrh w11, [x8]'), (0xF0CD2C, 'add x8, x8, #0x40'),
        (0xF0CD50, 'strb w10, [x8, #0x38]'), (0xF0CD70, 'strb w10, [sp, #0xb0]'), (0xF0CD80, 'bl #0xf12440'),
        (0xF0D264, 'ldrb w8, [x20, #0x38]'), (0xF0D454, 'strb wzr, [sp, #0xb0]'), (0xF0D470, 'bl #0xf12440'),
        (0xF12520, 'ldrb w8, [x1, #0x30]'), (0xF12524, 'strb w8, [x0, #0x30]'), (0xF11734, 'ldrb w12, [x10, #0x38]'),
        (0xF0CE28, 'bl #0xb0fba0')):
    stock(a, t)

# ---------------------------------------------------------------- caller census of the item add (TASK 1) [V]
_n = C.TEXT_END // 4
_ws = struct.unpack_from('<%dI' % _n, C.TXT, 0)
found = []
for _i, _w in enumerate(_ws):
    if (_w & 0x7C000000) == 0x14000000:
        _imm = _w & 0x3FFFFFF
        if _imm & (1 << 25):
            _imm -= 1 << 26
        if 4 * (_i + _imm) == ITEM_ADD:
            assert _w >> 31, 'tail call (b) to 0xCF8E2C at %x: LR would be the caller of the caller' % (4 * _i)
            found.append(4 * _i)
assert found == ALL_CALLERS, 'callers of 0xCF8E2C changed: %s' % ', '.join('%X' % a for a in found)
assert all(a + 4 in C2_ACCEPT or a in SERVER_PATHS or a in [u[0] for u in UPSTREAM_GATE] for a in ALL_CALLERS)
assert sorted([a + 4 for a in ALL_CALLERS if a + 4 in C2_ACCEPT]) == sorted(C2_ACCEPT)
assert sorted([a + 4 for a in ALL_CALLERS if a + 4 in C2_LOCAL]) == sorted(C2_LOCAL)
assert not set(C2_LOCAL) & set(C2_ACCEPT)
for site, gate, txt in UPSTREAM_GATE:
    if txt:
        stock(gate, txt)
stock(0xD01234, 'ldr w8, [x8, #0x1268]'); stock(0xD01238, 'cmp w8, #6'); stock(0xD0123C, 'b.eq #0xd0137c')
stock(0xD0127C, 'bl #0xcf6d10')
stock(0x1179EFC, 'cmp w8, #0'); stock(0x1179F00, 'ccmp w9, #0, #0, ne')
# no shipped record / other *_live.py opens any of those upstream gates (else that caller must be re-judged)
for site, gate, txt in UPSTREAM_GATE:
    if site + 4 in C2_LOCAL:
        continue    # re-judged (W1): sigil3_live.py SIGIL3_ACTIVATE opens these; C2L passes the local player only
    for b_ in range(gate, gate + 4):
        assert b_ not in C.SHIPPED and b_ not in g.others, 'upstream gate %x patched (%s): re-judge caller %x' % (
            gate, g.others.get(b_, 'patch_manager.cpp'), site)
PROLOGUE = [(0xF102C0 + 4 * i) for i in range(13)]
PRO_TEXT = ['pacibsp', 'stp d15, d14, [sp, #-0xa0]!', 'stp d13, d12, [sp, #0x10]', 'str x28, [sp, #0x50]',
            'stp d11, d10, [sp, #0x20]', 'stp d9, d8, [sp, #0x30]', 'stp x29, x30, [sp, #0x40]',
            'add x29, sp, #0x40', 'stp x26, x25, [sp, #0x60]', 'stp x24, x23, [sp, #0x70]',
            'stp x22, x21, [sp, #0x80]', 'stp x20, x19, [sp, #0x90]', 'sub sp, sp, #0x160']
for a, t in zip(PROLOGUE, PRO_TEXT):
    stock(a, t)
# epilogue 0xF109EC..0xF10A18 undoes exactly that prologue
EPI_TEXT = ['add sp, sp, #0x160', 'ldp d9, d8, [sp, #0x30]', 'ldr x28, [sp, #0x50]', 'ldp d11, d10, [sp, #0x20]',
            'ldp d13, d12, [sp, #0x10]', 'ldp x20, x19, [sp, #0x90]', 'ldp x22, x21, [sp, #0x80]',
            'ldp x24, x23, [sp, #0x70]', 'ldp x26, x25, [sp, #0x60]', 'ldp x29, x30, [sp, #0x40]',
            'ldp d15, d14, [sp], #0xa0', 'retab']
for i, t in enumerate(EPI_TEXT):
    stock(0xF109EC + 4 * i, t)
# the send block 0xF107FC..0xF109EC uses only x0..x3, x8, x9, x19..x22, sp, x29 (x23..x28 untouched)
for a in range(0xF107FC, 0xF109EC, 4):
    t = C.dis1(a, C.text_word(a))
    assert not re.search(r'\b[xw]2[3-8]\b', t), 'send block uses %x: %s' % (a, t)

# ---------------------------------------------------------------- x16/x17 proofs for every hook / return target
(PS, PE), hits = ip_uses(0xF0BEC0)
assert hits == [(0xF0C1AC, 'udiv x16, x11, x15'), (0xF0C1B0, 'msub x15, x16, x15, x11')], hits
WHY_C1 = ('the site is a `bl` (x16/x17 corruptible across it); pump 0x%X..0x%X names x16 only at 0xF0C1AC '
          '(udiv x16 = write) / 0xF0C1B0 (read of that value), never x17 (scanned)' % (PS, PE))
(FS, FE), hits = ip_uses(0xCF8E2C)
assert not hits, hits
WHY_C2 = ('0xCF8E2C 0x%X..0x%X never names x16/x17 (scanned); far_return targets 0xCF8F78 / 0xCF8FE4 in the '
          'same function; x9..x12 + flags not read on either path (0xCF8F78..0xCF8F84 add/mov/bl 0xcf3f08; '
          '0xCF8FE4 -> 0xCF92C8 epilogue, scanned)' % (FS, FE))
for _a in list(range(0xCF8F78, 0xCF8F88, 4)) + [0xCF8FE4, 0xCF8FE8] + list(range(0xCF92C8, 0xCF92EC, 4)):
    _t = C.dis1(_a, C.text_word(_a))
    assert not re.search(r'\b[xw](9|1[0-2])\b', _t) and not re.match(r'(b\.|csel|csinc|csinv|cset|ccmp|adc|sbc)', _t), \
        'C2 return path reads x9..x12 / flags at %x: %s' % (_a, _t)
# W1: x19 = x1 (&{player no}) is live at 0xCF8F74. 0xCF8E70 `mov x19, x1`; the only branches into the gate block
# 0xCF8F68..0xCF8F74 are 0xCF8ECC / 0xCF8EDC; x19 is not written on the straight path 0xCF8E74..0xCF8F74 except
# 0xCF8F04, which lies on the flask branch 0xCF8EE0..0xCF8F64 (ends in b / cbnz to 0xCF92B0 / 0xCF92B8, never
# falls into 0xCF8F68). The bl 0x1D26080 at 0xCF8EC4 keeps x19 (callee-saved).
stock(0xCF8E70, 'mov x19, x1'); stock(0xCF8EC4, 'bl #0x1d26080'); stock(0xCF8ECC, 'cbz x8, #0xcf8f68')
stock(0xCF8EDC, 'b.hi #0xcf8f68'); stock(0xCF8F04, 'ldr x19, [sp, #0x38]'); stock(0xCF8F64, 'b #0xcf92b0')
stock(0xCF8F60, 'cbnz x0, #0xcf92b8')
for _a in range(FS, FE, 4):
    _w = C.text_word(_a)
    _t = C.dis1(_a, _w)
    _m = re.search(r'#0x([0-9a-f]+)$', _t)
    if _m and re.match(r'(b|b\.\w+|cbn?z|tbn?z)$', _t.split()[0]):
        _tg = int(_m.group(1), 16)
        if 0xCF8F6C <= _tg <= 0xCF8F78:
            raise AssertionError('branch into the gate block at %x: %s' % (_a, _t))
        if _tg == 0xCF8F68:
            assert _a in (0xCF8ECC, 0xCF8EDC), 'other branch to 0xCF8F68 at %x: %s' % (_a, _t)
for _a in range(0xCF8E74, 0xCF8F68, 4):
    _t = C.dis1(_a, C.text_word(_a))
    if re.match(r'(mov|ldr|add|sub|orr|ldp|csel|cset)\b', _t) and re.match(r'\S+ (x19|w19)\b', _t):
        assert _a == 0xCF8F04, 'x19 written at %x: %s' % (_a, _t)
# the sigil callers: x1 = caller sp+0xC = player number decoded from the module key (same format as pgd+0xD0)
for _a, _t in ((0x1179A8C, 'stp w9, w8, [sp, #0xc]'), (0x1179A94, 'add x1, sp, #0xc'), (0x1179AAC, 'bl #0xcf8e2c'),
               (0x117A158, 'stp w9, w8, [sp, #0xc]'), (0x117A160, 'add x1, sp, #0xc'), (0x117A178, 'bl #0xcf8e2c'),
               (0xF1618C, 'ldr w9, [x9, #0xd0]'), (0x11A0760, 'ldr w9, [x9, #0xd0]'),
               # local pgd: *(GDM)+0x20, as the producer 0x1195EA4..0x1195EB0
               (0x1195EA4, 'adrp x8, #0x5b57000'), (0x1195EA8, 'add x8, x8, #0xeb8')):
    stock(_a, _t)
(DS, DE), hits = ip_uses(0xF11D20)
assert not hits, hits
WHY_D1 = ('0x9E drain 0x%X..0x%X never names x16/x17 (scanned); D1 returns to 0xF11EA8 (x9/x8 rewritten by the '
          'relocated ldp, w10 by 0xF11EA8, x11/x12 written before read on 0xF12074/0xF1209C/0xF11EC0) or to '
          '0xF122CC (x8 reloaded, loop head 0xF11E00..0xF11E5C reads no x9..x12, flags unused)' % (DS, DE))
# x19 = AS: written only by 0xF11D58 (and the epilogue) in the drain
for _a in range(DS, DE, 4):
    _t = C.dis1(_a, C.text_word(_a))
    _m = re.match(r'(\S+) (.*)', _t)
    if not _m or _m.group(1).startswith(('st', 'cmp', 'cmn', 'tst', 'cb', 'tb', 'b', 'ccmp', 'ret', 'prfm')):
        continue
    _ops = [o.strip() for o in _m.group(2).split(',')]
    _dst = _ops[:2] if _m.group(1).startswith('ldp') else _ops[:1]
    if any(o in ('x19', 'w19') for o in _dst):
        # 0xF122E4: discard-only loop for AS type != 0x0A (0xF11DD4 -> 0xF122D8), loops to itself, exits 0xF12364
        assert _a in (0xF11D58, 0xF122E4) or _t.startswith('ldp x20, x19'), 'x19 written at %x: %s' % (_a, _t)
stock(0xF11DD4, 'b.ne #0xf122d8'); stock(0xF12360, 'cbnz x8, #0xf122e4'); stock(0xF122E4, 'add x19, x8, #0x10')
(BS, BE), hits = ip_uses(0xF102C0)
assert not hits, hits
WHY_C3 = 'request builder 0x%X..0x%X never names x16/x17 (scanned): far_jump x16 into 0xF107FC / 0xF109EC' % (BS, BE)

groups = {}


def place(tag, build, purpose):
    n = len(build(C.FAR_LO, {}).words())
    start = g.alloc(tag, 'FAR_CODE', (n * 4 + 0x10 + 0xF) & ~0xF, purpose)
    a = build(start, {})
    return start, a, g.cave(tag, start, a)


# ================================================================ C3 (built first: C1 needs its address)
def build_c3(s, _):
    a = C.Asm(s)
    for pa, t in zip(PROLOGUE, PRO_TEXT):                      # 0xF102C0's exact frame (13 words)
        a(C.text_word(pa))
    a(lambda pc, L: C.adrp(pc, 'x8', HOST))                    # host only
    a(C.ldrb('w8', 'x8', C.lo12(HOST)))
    a(C.to(C.cbnz_w, 'w8', 'exit'))
    a(C.ldp_x('x8', 'x9', 'x0', 0x130))                        # strikes AS+0x130..+0x138, 0x20 each
    a.label('loop')
    a(C.cmp_xr('x8', 'x9'))
    a(C.to(C.bhs, 'exit'))
    a(C.ldr_w('w10', 'x8', 0))
    a(C.cmp_wr('w10', 'w1'))
    a(C.to(C.beq, 'found'))
    a(C.add_xi('x8', 'x8', 0x20))
    a(C.to(C.b, 'loop'))
    a.label('found')
    a(C.ldrb('w10', 'x8', 0x1C))                               # pending (set by the decision)
    a(C.to(C.cbz_w, 'w10', 'exit'))
    a(C.movz_w('w10', 1))                                      # message at sp: kind 1, player no
    a(stp_w('w10', 'w1', 'sp', 0))
    a(C.stp_x('xzr', 'xzr', 'sp', 0x18))                       # candidate vector empty (0xF108E4 frees nothing)
    a(C.stp_x('xzr', 'xzr', 'sp', 0x28))                       # +0x28 cap, +0x30 allocator
    a(C.ldp_x('x9', 'x10', 'x8', 8))                           # strike +8..+0x17
    a(C.ldr_w('w11', 'x8', 0x18))                              # strike +0x18..+0x1B (ship id, target id)
    a(C.stp_x('x9', 'x10', 'sp', 0x38))                        # -> message +0x38..+0x47
    a(C.str_w('w11', 'sp', 0x48))                              # -> message +0x48..+0x4B
    a(lambda pc, L: C.adrp(pc, 'x19', NETG))                   # net mgr, as 0xF107E0..0xF107EC
    a(C.ldr_x('x19', 'x19', C.lo12(NETG)))
    a(C.to(C.cbz_x, 'x19', 'exit'))
    a.many(lambda pc, L: C.far_jump(pc, SEND_IN, 'x16'))      # native send path (S2: 0x9E to players)
    a.label('exit')
    a.many(lambda pc, L: C.far_jump(pc, SEND_EPI, 'x16'))     # native epilogue + retab
    return a


C3, c3a, c3_recs = place('ZEP3_C3', build_c3, 'zeppelin C3: host sends 0x9E kind 1 (strike) via 0xF107FC')
C3_LAST = C3 + 4 * (len(c3a.words()) - 1)
groups['ZEP3_C3'] = c3_recs


# ================================================================ C1
def build_c1(s, _):
    a = C.Asm(s)
    a(C.stp_pre('x29', 'x30', 'sp', -0x20))
    a(C.mov_sp('x29', 'sp'))
    a.many(lambda pc, L: C.far_call(pc, DRAIN, 'x16'))        # the replaced call (x0 = AS from 0xF0C524)
    a(lambda pc, L: C.adrp(pc, 'x8', OFFL))                    # offline: stock (0xCF6E28 decides there)
    a(C.ldr_x('x8', 'x8', C.lo12(OFFL)))
    a(C.ldrb('w8', 'x8', 0xBDA))
    a(C.to(C.cbnz_w, 'w8', 'out'))
    a(C.ldp_x('x8', 'x9', 'x19', 0x110))                       # request queue begin / end
    a(C.cmp_xr('x8', 'x9'))
    a(C.to(C.beq, 'out'))                                      # empty (always on guests)
    a(C.ldr_w('w8', 'x8', 0))                                  # first request's player no
    a(C.str_w('w8', 'sp', 0x10))                               # copy: 0xF11140 drains again
    a(C.mov_x('x0', 'x19'))
    a(C.add_xi('x1', 'sp', 0x10))
    a.many(lambda pc, L: C.far_call(pc, DECIDE, 'x16'))       # host decides + erases; guests return (S5)
    a(lambda pc, L: C.adr(pc, 'x9', C3_LAST))                  # ZEP3_C3 applied? (its last word, written last)
    a(C.ldr_w('w9', 'x9', 0))
    a(C.to(C.cbz_w, 'w9', 'out'))
    a(C.ldr_w('w1', 'sp', 0x10))
    a(C.mov_x('x0', 'x19'))
    a(lambda pc, L: C.bl(pc, C3))                              # C3(AS, player no): host only, checks itself
    a.label('out')
    a(C.ldp_post('x29', 'x30', 'sp', 0x20))
    a(C.RET)
    return a


C1, c1a, c1_recs = place('ZEP3_C1', build_c1, 'zeppelin C1: pump drain + host decision 0xF11140 (+ C3 call)')
groups['ZEP3_C1'] = c1_recs + g.far_hook(
    0xF0C52C, 'bl #0xf11d20', C1, 'x16', link=True, why=WHY_C1,
    note='pump: drain, then decide the first queued request')


# ================================================================ C2 (replaces FORGE_OWN's hook target)
# 0xCF8F74 is the shipped FORGE_OWN hook (`b 0xCF0E84`, rewards_live.py; flame_live.py FORGE_TEST same word).
SHIP = C.shipped_word(0xCF8F74)
assert SHIP == C.b(0xCF8F74, 0xCF0E84), 'shipped 0xCF8F74 is not FORGE_OWN b 0xCF0E84: %08x' % SHIP
FORGE_CAVE = [0x350407A8, 0xF94007A9, 0x9000258A, 0x911DB14A, 0x6B0A013F, 0x54040700, 0x14002052]
for i, w in enumerate(FORGE_CAVE):
    assert C.shipped_word(0xCF0E84 + 4 * i) == w, 'FORGE_OWN cave word %x changed' % (0xCF0E84 + 4 * i)
assert C.dis1(0xCF0E88, FORGE_CAVE[1]) == 'ldr x9, [x29, #8]'
assert C.dis1(0xCF0E90, FORGE_CAVE[3]) == 'add x10, x10, #0x76c'
for i in range(4):
    held = g.others.get(0xCF8F74 + i)
    assert held in (None, 'rewards_live.py', 'flame_live.py'), '0xCF8F74 held by %s' % held
    g.others.pop(0xCF8F74 + i, None)


def sub_wr(rd, rn, rm):
    return 0x4B000000 | (C.R(rm) << 16) | (C.R(rn) << 5) | C.R(rd)


assert C.dis1(0, sub_wr('w9', 'w9', 'w12')) == 'sub w9, w9, w12'

# far data table (read-only constants): return-address offsets from main, 0-terminated
TAB = g.alloc('ZEP3_C2_TABLE', 'FAR_DATA', C2_TABLE_WORDS * 4, 'C2 table: return-address offsets allowed through 0xCF8F74')
assert len(C2_ACCEPT) < C2_TABLE_WORDS and all(0 < o < C.TEXT_END for o in C2_ACCEPT)


def data_words(name, start, words):
    """Far-data records (orig 00000000). is_code True: live tools write them SetCode-style (region is read-only
    to the guest); patch_manager takes every far record as {}, true."""
    g.listing.append('--- %s data at 0x%X (%d words) FAR_DATA' % (name, start, len(words)))
    recs = []
    for i, w in enumerate(words):
        a = start + 4 * i
        assert C.pool_of(a, 4) == 'FAR_DATA' and g.owned(a), 'data word %x not in own FAR_DATA claim' % a
        g.free_bytes(a, 4, 'data word')
        g.listing.append('  0x%x .word 0x%08X  (ret main+0x%X)' % (a, w, w) if w else '  0x%x .word 0  (end)' % a)
        recs.append((a, '00000000', C.hexw(w), True))
    return recs


tab_recs = data_words('ZEP3_C2_TABLE', TAB, C2_ACCEPT + [0])
TAB2 = g.alloc('ZEP3_C2_LOCAL', 'FAR_DATA', C2_LOCAL_WORDS * 4,
               'C2 table 2: return offsets allowed through 0xCF8F74 for the local player only (W1)')
assert len(C2_LOCAL) < C2_LOCAL_WORDS and all(0 < o < C.TEXT_END for o in C2_LOCAL)
tab2_recs = data_words('ZEP3_C2_LOCAL', TAB2, C2_LOCAL + [0])


def build_c2l(s, _):
    """Entered from C2 (plain b) when the return offset w9 is not in the plain table. x9 = offset, x19 = &player
    no of 0xCF8E2C (asserted above). Grants only when [x19] == local pgd+0xD0; null GDM / pgd -> deny."""
    a = C.Asm(s)
    a(lambda pc, L: C.adr(pc, 'x10', TAB2))
    a.label('loop')
    a(C.ldr_w('w11', 'x10', 0))
    a(C.to(C.cbz_w, 'w11', 'deny'))                            # not listed either: refused as today
    a(C.add_xi('x10', 'x10', 4))
    a(C.cmp_wr('w9', 'w11'))
    a(C.to(C.bne, 'loop'))
    a(lambda pc, L: C.adrp(pc, 'x10', GDM))                    # local PlayerGameData
    a(C.ldr_x('x10', 'x10', C.lo12(GDM)))
    a(C.to(C.cbz_x, 'x10', 'deny'))
    a(C.ldr_x('x10', 'x10', 0x20))
    a(C.to(C.cbz_x, 'x10', 'deny'))
    a(C.ldr_w('w10', 'x10', 0xD0))                             # local player number
    a(C.ldr_w('w11', 'x19', 0))                                # receiving player number
    a(C.cmp_wr('w10', 'w11'))
    a(C.to(C.bne, 'deny'))                                     # another player's copy: no item here
    a.many(lambda pc, L: C.far_return(pc, GRANT, 'x16'))
    a.label('deny')
    a.many(lambda pc, L: C.far_return(pc, DENY, 'x16'))
    return a


C2L, c2la, c2l_recs = place('ZEP3_C2L', build_c2l, 'C2L: local-player test for the ZEP3_C2_LOCAL callers (W1)')


def build_c2(s, _):
    a = C.Asm(s)
    a(C.to(C.cbnz_w, 'w8', 'grant'))                           # +0xBDA set (offline): unchanged
    a(C.ldr_x('x9', 'x29', 8))                                 # 0xCF8E2C's saved LR (PAC: low 32 bits exact)
    a(lambda pc, L: C.adrp(pc, 'x12', 0))                      # main base (page aligned)
    a(sub_wr('w9', 'w9', 'w12'))                               # w9 = return address - main = offset
    a(lambda pc, L: C.adr(pc, 'x10', TAB))
    a.label('loop')
    a(C.ldr_w('w11', 'x10', 0))
    a(C.to(C.cbz_w, 'w11', 'local'))                           # end of table: try the local-player table
    a(C.add_xi('x10', 'x10', 4))
    a(C.cmp_wr('w9', 'w11'))
    a(C.to(C.bne, 'loop'))
    a.label('grant')
    a.many(lambda pc, L: C.far_return(pc, GRANT, 'x16'))
    a.label('local')
    a(lambda pc, L: C.b(pc, C2L))                              # C2L: table 2 + local test, else deny (W1)
    return a


C2, c2a, c2_recs = place('ZEP3_C2', build_c2, 'zeppelin C2: 0xCF8E2C gate lets forge + zeppelin grant through')
groups['ZEP3_C2'] = tab_recs + tab2_recs + c2l_recs + c2_recs + g.far_hook(
    0xCF8F74, 'cbz w8, #0xcf8fe4', C2, 'x16', link=False, why=WHY_C2, replaces_shipped=True,
    note='SUPERSEDES FORGE_OWN hook (update DUSK_W_CF8F74)')


# ================================================================ D1 (guest dedupe of kind-1 strikes)
D1_SITE, D1_BACK, D1_NEXT = 0xF11EA4, 0xF11EA8, 0xF122CC


def build_d1(s, _):
    a = C.Asm(s)
    a(C.ldr_x('x11', 'sp', 0x28))                              # record body = record +0x38 (strike +8..+0x1B)
    a(C.ldrb('w10', 'x11', 0))                                 # result (strike +8): 0 = denied -> stock (notice)
    a(C.to(C.cbz_w, 'w10', 'keep'))
    a(C.ldrh('w10', 'x11', 0x10))                              # ship id (strike +0x18)
    a(C.ldp_x('x8', 'x9', 'x19', 0xF0))                        # airships AS+0xF0..+0xF8, 0x40 each
    a.label('loop')
    a(C.cmp_xr('x8', 'x9'))
    a(C.to(C.bhs, 'keep'))                                     # ship not listed: stock
    a(C.ldrh('w12', 'x8', 0))
    a(C.cmp_wr('w12', 'w10'))
    a(C.to(C.beq, 'found'))
    a(C.add_xi('x8', 'x8', 0x40))
    a(C.to(C.b, 'loop'))
    a.label('found')
    a(C.ldrb('w12', 'x8', 0x38))                               # busy: this game already fired that ship
    a(C.to(C.cbz_w, 'w12', 'keep'))
    a.many(lambda pc, L: C.far_return(pc, D1_NEXT, 'x16'))    # drop this 0x9E record, read the next one
    a.label('keep')
    a.many(lambda pc, L: C.relocate(D1_SITE, pc, 'x16'))      # the replaced `ldp x9, x8, [x19, #0x130]`
    a.many(lambda pc, L: C.far_return(pc, D1_BACK, 'x16'))
    return a


D1, d1a, d1_recs = place('ZEP3_D1', build_d1, 'zeppelin D1: guests drop a granted kind-1 strike for a busy ship')
groups['ZEP3_D1'] = d1_recs + g.far_hook(
    D1_SITE, 'ldp x9, x8, [x19, #0x130]', D1, 'x16', link=False, why=WHY_D1,
    note='kind-1 strike: drop when its airship is busy here')

# ---------------------------------------------------------------- no shared word with zeppelin_nc_live.py
nc = set(a for a, f in g.others.items() if f == 'zeppelin_nc_live.py')
for gname, rs in groups.items():
    for a, o, n, c in rs:
        assert not (set(range(a, a + 4)) & nc), '%s shares %x with zeppelin_nc_live.py' % (gname, a)

ORDER = ['ZEP3_C2', 'ZEP3_C1', 'ZEP3_D1', 'ZEP3_C3']
print('\n'.join(g.listing))
print('C1 0x%X  C2 0x%X (table 0x%X)  C3 0x%X (gate word 0x%X)  D1 0x%X' % (C1, C2, TAB, C3, C3_LAST, D1))
if DRY:
    print('dry run: nothing claimed or written')
    sys.exit(0)

C.write_live(OUT, groups, ORDER, """Zeppelin support C1 / C2 / C3 on the far cave region: (offset_from_main, orig_hex, new_hex, is_code).
Generated by zep3_gen.py (cave_lib checks: stock words, capstone, registry, collisions). NOT live-tested.
Notes: zep3_notes.md; design zeppelin2_notes.md section 4. Apply on EVERY game, AFTER zeppelin_nc_live.py
ZEP_S1..ZEP_S6 (+ optional ZEP_S7). Each group: far cave, trampoline, hook LAST.
ZEP3_C2 SUPERSEDES the built-in FORGE_OWN hook word 0xCF8F74 (must be applied after it; built-in record
DUSK_W_CF8F74 is UPDATED, not added). Live: apply ZEP3_C2_LIVE instead (its hook orig = FORGE_OWN's word).
ZEP3_C3 has no hook: C1 calls it once its LAST word is non-zero (write its records in list order).
ZEP3_C2 starts with its far-data table (C2_TABLE: return-address offsets, 0-terminated): write it first.
ZEP3_D1 (guest dedupe of kind-1 strikes, hook 0xF11EA4) goes in BEFORE ZEP3_C3. Notes: grantgate_notes.md.""")
c2_live = [r if r[0] != 0xCF8F74 else (r[0], C.hexw(SHIP), r[2], r[3]) for r in groups['ZEP3_C2']]
with open(os.path.join(HERE, OUT), 'a') as f:
    f.write('\n# live-apply form of ZEP3_C2 (apply_groups.py checks orig-or-new: memory holds the built-in\n'
            '# FORGE_OWN word C4DFFF17 at 0xCF8F74, not stock). Same new bytes as ZEP3_C2. Not for patch_manager.\n')
    f.write('ZEP3_C2_LIVE = [\n' + ''.join('    (0x%X, "%s", "%s", %s),\n' % r for r in c2_live) + ']\n')
    f.write('CAVES = {%s}\n' % ', '.join("'%s': 0x%X" % kv for kv in (('C1', C1), ('C2', C2), ('C3', C3),
                                                                      ('C3_GATE', C3_LAST), ('C2_TABLE', TAB),
                                                                      ('C2L', C2L), ('C2_LOCAL', TAB2),
                                                                      ('D1', D1))))

BEGIN, END = '<!-- CPP_ROWS_BEGIN -->', '<!-- CPP_ROWS_END -->'
parts = [BEGIN, '## patch_manager.cpp rows (generated by zep3_gen.py: `cave_lib.cpp_rows`)', '',
         'Far words use the `{}, true` form. Per group: far cave, trampoline, hook. For ZEP3_C2 the hook',
         '`DUSK_W_CF8F74` already EXISTS (FORGE_OWN): replace its new bytes, keep its _ORIGINAL, do not add a',
         'second row. FORGE_OWN_CAVE (0xCF0E84..) can stay (unreferenced) or be removed by the lead.', '']
for gname in ORDER:
    d, r = C.cpp_rows(gname, groups[gname])
    parts += ['### %s' % gname, '```cpp', d, r, '```', '']
parts.append(END)
notes = os.path.join(HERE, 'zep3_notes.md')
txt = open(notes, encoding='utf-8').read() if os.path.exists(notes) else ''
if BEGIN in txt and END in txt:
    txt = txt[:txt.index(BEGIN)] + txt[txt.index(END) + len(END):].lstrip('\n')
open(notes, 'w', encoding='utf-8').write(txt.rstrip('\n') + '\n\n' + '\n'.join(parts) + '\n')
print('zep3_notes.md: cpp rows section written')
