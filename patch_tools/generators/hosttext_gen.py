"""hosttext_gen.py: HOSTTEXT, DRAFT (static, never run live, never baked). Design in hosttext_notes.md.
Static generator, Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows).
python hosttext_gen.py --dry      (from diag/net)   -> prints the listing; with no --dry it writes hosttext_live.py
                                                       (do NOT do that before the notes' open points are closed)

Two caves, one box in FAR_DATA:
  HTREQ  hook 0x116EF18 (the epilogue word of the last-phase-notice update 0x116ED24, game thread, the function
         that itself requests TextEffect rows 13100 / 13110): when HTBOX.state == 1 and the TextEffect request
         queue (menu+0x900..0x908) is empty, set state 2 and request TextEffectParam row 13010 ("1 Minute
         Remaining", the phase-warning banner) with 0x12A85E0(menu, 13010, 0), the stock call.
  HTTEXT hook 0x1A2C354 (`cbz x0` after the message getter in 0x1A2C2FC, UI script thread): when the lookup is
         text id 10810 from the TextEffect wrapper (x22 == main+0x4B65962) and state == 2, x0 = our UTF-16 string
         and state = 3 (shown); else the stock word.
The assist (dusk_lan.cpp, not in this file) writes the text then state = 1, and clears 3 -> 0 after ~8 s
(2 -> 0 after 5 s: lost request)."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cave_lib as C  # noqa: E402

DRY = '--dry' in sys.argv
OUT = 'hosttext_live.py'
W = struct.unpack_from('<%dI' % (C.TEXT_END // 4), C.TXT, 0)
PACIBSP = 0xD503237F

REQ_SITE, REQ_BACK = 0x116EF18, 0x116EF1C          # epilogue of 0x116ED24: `ldp x20, x19, [sp, #0x60]`
LK_SITE, LK_STOCK_TARGET, LK_BACK = 0x1A2C354, 0x1A2C3E4, 0x1A2C358
REQUEST = 0x12A85E0                                  # TextEffectMenu::Request(menu, row id, arg)
ROW = 13010                                          # TextEffectParam row 13010 -> text 10810, style 1301, SE 41010
TEXT_ID = 10810                                      # TextEffect_Text 10810 "1 Minute Remaining"
WRAPPER_X2 = 0x4B65962                               # the wrapper 0x1A2D7C8 passes this string as x2 (fallback text)
MGR_PAGE_PTR = 0x5B99BB0                             # [main+0x5B99BB0] + 0x49BB0 = the TextEffect menu
listing = []
PLANNED = []   # rows other helpers have claimed but the lead has not added yet: fill in before a real run


def stock(a, t):
    got = C.dis1(a, C.text_word(a))
    assert got == t, 'stock %x: %s, expected %s' % (a, got, t)


def dis(a):
    return C.dis1(a, W[a // 4])


def targets_in(lo, hi):
    out = []
    for i, w in enumerate(W):
        pc, t = 4 * i, None
        if (w & 0x7C000000) == 0x14000000:
            imm = w & 0x3FFFFFF
            t = pc + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
        elif (w & 0xFF000010) == 0x54000000 or (w & 0x7E000000) == 0x34000000 or (w & 0x3B000000) == 0x18000000:
            imm = (w >> 5) & 0x7FFFF
            t = pc + ((imm - (1 << 19)) if imm & (1 << 18) else imm) * 4
        elif (w & 0x7E000000) == 0x36000000:
            imm = (w >> 5) & 0x3FFF
            t = pc + ((imm - (1 << 14)) if imm & (1 << 13) else imm) * 4
        elif (w & 0x9F000000) == 0x10000000:
            d = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
            t = pc + (d - (1 << 21) if d & (1 << 20) else d)
        if t is not None and lo <= t < hi:
            out.append(pc)
    return out


def qwords_in(lo, hi):
    out = []
    for base, blob in ((C.DATA_BASE, C.DATA), (C.RO_BASE, C.RO)):
        n = len(blob) // 8
        for i, x in enumerate(struct.unpack_from('<%dQ' % n, blob, 0)):
            if lo <= x < hi:
                out.append(base + 8 * i)
    return out


# ================================================================ code facts [V = read in main_text]
for a, t in ((REQ_SITE, 'ldp x20, x19, [sp, #0x60]'), (REQ_BACK, 'ldp x22, x21, [sp, #0x50]'),
             (0x116EF28, 'retab'),                                  # the epilogue ends in retab
             (0x116ED24, 'pacibsp'),
             (0x116EEB4, 'bl #0x12a85e0'), (0x116EF14, 'bl #0x12a85e0'),   # the stock requests 13100 / 13110
             (REQUEST, 'pacibsp'),
             (0x12E36C4, 'bl #0x12a85e0'),                           # the stock 1-minute request (row 13010)
             (LK_SITE, 'cbz x0, #0x1a2c3e4'), (LK_BACK, 'adrp x8, #0x5b99000'),
             (0x1A2C350, 'blr x8'), (0x1A2C334, 'mov x22, x2'), (0x1A2C330, 'mov x21, x3'),
             (0x1A2C338, 'mov w20, w1'),
             (0x1A2D7C8, 'pacibsp')):
    stock(a, t)
# the three branches that end in the epilogue word, all via 0x116EF18 (no other exit skips it)
listing.append('0x116EF18: reached by the fall-through of 0x116EF14 and by tbz 0x116EEF4 / '
               'cbz 0x116EF00 [V]: the one epilogue; x0..x18 are dead there (return value unused [I]), x30 is '
               'reloaded by 0x116EF20')
assert not any(x in C.SHIPPED for x in range(REQ_SITE, REQ_SITE + 4)), 'REQ site is already patched'
assert not any(x in C.SHIPPED for x in range(LK_SITE, LK_SITE + 4)), 'LOOKUP site is already patched'

others = C.live_records(exclude=(OUT,))
assert not any(x in others for x in range(REQ_SITE, REQ_SITE + 4)), 'REQ site taken by another live file'
assert not any(x in others for x in range(LK_SITE, LK_SITE + 4)), 'LOOKUP site taken by another live file'


def find_pad(site, n):
    for a in range(site - 0x80000, site + 0x80000, 4):
        if all(W[a // 4 + k] == 0 for k in range(n)) and W[a // 4 - 1] != 0:
            z = a
            while W[z // 4] == 0:
                z += 4
            if W[z // 4] != PACIBSP:
                continue
            if dis(a - 4).startswith('bl '):
                continue
            if any(x in C.SHIPPED or x in others for x in range(a, a + 4 * n)):
                continue
            if targets_in(a, z) or qwords_in(a, z):
                continue
            if C.reach(site, a):
                return a
    return None


PAD_REQ = find_pad(REQ_SITE, 3)
assert PAD_REQ
PAD_LK = find_pad(LK_SITE, 3)
assert PAD_LK and PAD_LK != PAD_REQ
listing.append('trampoline padding REQ 0x%X, LOOKUP 0x%X' % (PAD_REQ, PAD_LK))

g = C.Gen('hosttext_gen', out=OUT, dry=True)
for owner, tag, lo, hi in PLANNED:
    g._dry_rows.append(dict(owner=owner, tag=tag, lo=lo, hi=hi, purpose='planned'))

# HTBOX layout (assist writes text then state):
#  +0x00 u32 state  0 idle, 1 text ready (assist), 2 requested (HTREQ), 3 shown (HTTEXT; assist -> 0 after ~8 s)
#  +0x04 u32 seq    (assist, for logs)
#  +0x08 u32 shown  count (HTTEXT)
#  +0x0C u32 asked  count (HTREQ)
#  +0x10 u16 text[128]  NUL-terminated UTF-16LE, at most 120 units + NUL, written only while state == 0
BOX_SIZE = 0x10 + 128 * 2
BOX = g.alloc('HTBOX', 'FAR_DATA', BOX_SIZE, 'HOSTTEXT box {state, seq, shown, asked, u16 text[128]} (FAR_DATA)')
BUF = BOX + 0x10

# ---------------------------------------------------------------- HTREQ
SIZE1 = 40
T1 = g.alloc('HTREQ', 'FAR_CODE', SIZE1 * 4, 'HOSTTEXT request: row 13010 from the epilogue of 0x116ED24')
a = C.Asm(T1)
a(lambda pc, L: C.adrp(pc, 9, BOX))
a(C.add_xi(9, 9, C.lo12(BOX)))
a(C.ldr_w(10, 9, 0))
a(C.cmp_wi(10, 1))
a(C.to(C.bne, 'back'))
a(lambda pc, L: C.adrp(pc, 8, MGR_PAGE_PTR))
a(C.ldr_x(8, 8, MGR_PAGE_PTR & 0xFFF))
a(C.to(C.cbz_x, 'x8', 'back'))
a(C.add_xi(8, 8, 0x49, True))                                # + 0x49000
a(C.add_xi(0, 8, 0xBB0))                                     # x0 = menu = [main+0x5B99BB0] + 0x49BB0
a(C.ldr_x(10, 0, 0x908))
a(C.ldr_x(11, 0, 0x900))
a(C.cmp_xr(10, 11))
a(C.to(C.bne, 'back'))                                       # a request is still queued: ask again next frame
a(C.movz_w(10, 2))
a(C.str_w(10, 9, 0))                                         # state = 2 BEFORE the call (the UI thread may be fast)
a(C.ldr_w(10, 9, 0xC))
a(C.add_wi(10, 10, 1))
a(C.str_w(10, 9, 0xC))
a(C.movz_w(1, ROW))
a(C.mov_w(2, 'wzr'))
a.many(lambda pc, L: C.far_call(pc, REQUEST))
a.label('back')
a.many(lambda pc, L: C.relocate(REQ_SITE, pc))               # ldp x20, x19, [sp, #0x60]
a.many(lambda pc, L: C.far_jump(pc, REQ_BACK))
assert len(a.words()) <= SIZE1, len(a.words())
assert 0 not in a.words(), 'an encoder is missing in cave_lib'
cave1 = g.cave('HTREQ', T1, a)

# ---------------------------------------------------------------- HTTEXT
SIZE2 = 40
T2 = g.alloc('HTTEXT', 'FAR_CODE', SIZE2 * 4, 'HOSTTEXT text: x0 = our string for TextEffect text 10810 (0x1A2C354)')
b = C.Asm(T2)
b(C.movz_w(9, TEXT_ID))
b(C.cmp_wr(20, 9))                                           # w20 = text id (0x1A2C338)
b(C.to(C.bne, 'stock'))
b(lambda pc, L: C.adrp(pc, 9, BOX))
b(C.add_xi(9, 9, C.lo12(BOX)))
b(C.ldr_w(10, 9, 0))
b(C.cmp_wi(10, 2))
b(C.to(C.bne, 'stock'))
b(lambda pc, L: C.adrp(pc, 10, WRAPPER_X2))
b(C.add_xi(10, 10, C.lo12(WRAPPER_X2)))
b(C.cmp_xr(22, 10))                                          # x22 = fallback string of the caller (0x1A2C334)
b(C.to(C.bne, 'stock'))
b(C.movz_w(10, 3))
b(C.str_w(10, 9, 0))                                         # state = 3: the string is in use, the assist keeps off
b(C.ldr_w(10, 9, 8))
b(C.add_wi(10, 10, 1))
b(C.str_w(10, 9, 8))
b(C.add_xi(0, 9, 0x10))                                      # x0 = BUF (BOX + 0x10, 4-aligned; UTF-16 NUL-terminated)
b.label('stock')
b.many(lambda pc, L: C.relocate(LK_SITE, pc))                # cbz x0, #0x1a2c3e4 (4 words: inverted cbnz + far_jump)
b.many(lambda pc, L: C.far_jump(pc, LK_BACK))
assert len(b.words()) <= SIZE2, len(b.words())
assert 0 not in b.words(), 'an encoder is missing in cave_lib'
cave2 = g.cave('HTTEXT', T2, b)

tramp1 = [g.text_patch(PAD_REQ + 4 * k, 'udf #0', w, 'trampoline -> HTREQ 0x%X (x16 dead at 0x116EF18)' % T1)
          for k, w in enumerate(C.far_jump(PAD_REQ, T1))]
tramp2 = [g.text_patch(PAD_LK + 4 * k, 'udf #0', w, 'trampoline -> HTTEXT 0x%X (x16 dead at 0x1A2C354)' % T2)
          for k, w in enumerate(C.far_jump(PAD_LK, T2))]
hook1 = [g.text_patch(REQ_SITE, 'ldp x20, x19, [sp, #0x60]', C.b(REQ_SITE, PAD_REQ), 'HTREQ')]
hook2 = [g.text_patch(LK_SITE, 'cbz x0, #0x1a2c3e4', C.b(LK_SITE, PAD_LK), 'HTTEXT')]

groups = {'HOSTTEXT_CAVE': cave1 + cave2 + tramp1 + tramp2, 'HOSTTEXT_REQ': hook1, 'HOSTTEXT_TEXT': hook2}
order = ['HOSTTEXT_CAVE', 'HOSTTEXT_REQ', 'HOSTTEXT_TEXT']
print(chr(10).join(listing))
print(chr(10).join(g.listing))
print('registry rows (lead adds):')
print('| hosttext_gen | HTBOX | 0x%X..0x%X | HOSTTEXT box (FAR_DATA) |' % (BOX, BOX + BOX_SIZE))
print('| hosttext_gen | HTREQ | 0x%X..0x%X | HOSTTEXT request 0x116EF18; trampoline 0x%X..0x%X |' % (T1, T1 + SIZE1 * 4, PAD_REQ, PAD_REQ + 12))
print('| hosttext_gen | HTTEXT | 0x%X..0x%X | HOSTTEXT text 0x1A2C354; trampoline 0x%X..0x%X |' % (T2, T2 + SIZE2 * 4, PAD_LK, PAD_LK + 12))
if DRY:
    print('--dry: nothing written')
else:
    C.write_live(OUT, groups, order, __doc__.split('Two caves')[0].strip())
