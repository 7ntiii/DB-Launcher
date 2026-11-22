"""Generator + checker for the kin summoning circle groups in kincircle_live.py. Static only.
python kincircle_gen.py  -> rewrites kincircle_live.py and prints a capstone listing of every new word.

Design (kin_circle_notes.md):
  KIN_PRESS     0x11A46F8 (0x74 action-menu receiver 0x11A451C, kind 1 = "request"): the request is granted
                (0x11A36C0) on an offline game as before, and in LAN only on the game whose local player
                [*(main+0x5B3CD88)+0x1A8] is the requesting chr (x22). In LAN the request goes to the self link only.
  KIN_EXEC      0x119EF9C (CSBuddySummonDoorActionMenuAssetProcessor execute 0x119EF68): authority path
                (0xD89FD4) on an offline game, or when the acting chr x19 is the local player.
  KIN_CONTRACT  0xD8A004 (0xD89FD4, only caller 0x119F030 which KIN_EXEC gates): nop the offline check.
  KIN_PROMPT_DIAG (optional, NOT in ORDER) 0x119EF24/0x119EF28: availability slot 0x119EE00 returns
                "candidate list not empty" only (ignores the two buddy-manager list checks). Use it only to
                test which gate hides the prompt; see the notes before shipping it.
Caves: ro padding main+0x563E5C0..0x563E5FF (zero, unused by patch_manager.cpp and every *_live.py;
patch_manager's last word in that area is 0x563E5AC, the next used one is 0x563E600)."""
import os
import struct

import capstone

N = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nso')
TXT = open(os.path.join(N, 'main_text.bin'), 'rb').read()
RO = open(os.path.join(N, 'main_ro.bin'), 'rb').read()
RO_BASE = 0x492B000
md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)

WCM = 0x5B3CD88          # *(main+0x5B3CD88) = WorldChrMan, +0x1A8 = local player chr
CAVE_START, CAVE_END = 0x563E5C0, 0x563E600


def _rel(pc, t, bits):
    d = t - pc
    assert d % 4 == 0
    d //= 4
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'out of range'
    return d & ((1 << bits) - 1)


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bne(pc, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | 1
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | rt
def ldr_x(rt, rn, off): return 0xF9400000 | ((off // 8) << 10) | (rn << 5) | rt
def cmp_xr(rn, rm): return 0xEB00001F | (rm << 16) | (rn << 5)        # subs xzr, xn, xm
def cset_w_ne(rd): return 0x1A9F07E0 | rd                             # csinc wd, wzr, wzr, eq


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20)
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | rd


NOP = 0xD503201F


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hexw(w):
    return struct.pack('<I', w).hex().upper()


def text_of(addr):
    ins = next(md.disasm(TXT[addr:addr + 4], addr))
    return ins.mnemonic + ' ' + ins.op_str


recs = {}
listing = []


def cave(name, start, build):
    """build(pc0) -> list of words; checks the padding is zero."""
    ws = build(start)
    for i in range(len(ws)):
        o = start + i * 4 - RO_BASE
        # past the end of the ro file = segment padding (zero in memory)
        assert RO[o:o + 4] in (b'\0\0\0\0', b''), 'cave not zero at %x' % (start + i * 4)
    code = b''.join(struct.pack('<I', w) for w in ws)
    listing.append('--- %s cave at 0x%X (%d words)' % (name, start, len(ws)))
    n = 0
    for ins in md.disasm(code, start):
        listing.append('  0x%x %s %s' % (ins.address, ins.mnemonic, ins.op_str))
        n += 1
    assert n == len(ws), 'cave %s: undecodable word' % name
    return [(start + i * 4, '00000000', hexw(w), True) for i, w in enumerate(ws)], start + len(ws) * 4


def hook(addr, target, expect_text):
    assert text_of(addr) == expect_text, 'hook %x is %s' % (addr, text_of(addr))
    new = b(addr, target)
    listing.append('--- hook 0x%X: %s  ->  %s' % (addr, expect_text, text_of_word(new, addr)))
    return (addr, hexw(word(addr)), hexw(new), True)


def text_of_word(w, addr):
    ins = next(md.disasm(struct.pack('<I', w), addr))
    return ins.mnemonic + ' ' + ins.op_str


def patch(addr, expect_text, new):
    assert text_of(addr) == expect_text, 'patch %x is %s' % (addr, text_of(addr))
    listing.append('--- patch 0x%X: %s  ->  %s' % (addr, expect_text, text_of_word(new, addr)))
    return (addr, hexw(word(addr)), hexw(new), True)


# facts the caves rely on (assert the original code around the hooks)
assert text_of(0x119EF90) == 'mov x19, x1'              # x19 = acting chr in execute
assert text_of(0x119EF94) == 'ldrb w8, [x8, #0xbda]'
assert text_of(0x119EFA0) == 'ldr x8, [x20, #0x10]'     # authority path start (rewrites x8)
assert text_of(0x119F030) == 'bl #0xd89fd4'
assert text_of(0x11A45FC) == 'ldr x22, [sp, #0x50]'     # x22 = requesting chr in the 0x74 receiver
assert text_of(0x11A46F4) == 'ldrb w8, [x8, #0xbda]'
assert text_of(0x11A46FC) == 'mov x8, #-0x100000000'    # grant path start (rewrites x8)
assert text_of(0xD8A000) == 'ldrb w8, [x8, #0xbda]'

pc = CAVE_START


def local_gate(p, chr_reg, go, skip):
    """offline game or chr_reg == local player -> go, else skip. Uses x8 only (x8 is rewritten at go/skip)."""
    return [cbnz_w(p, 8, p + 0x18),                   # 00 offline game: unchanged
            adrp(p + 4, 8, WCM),                      # 04
            ldr_x(8, 8, WCM & 0xFFF),                 # 08 WCM (never null in a match; 0x119EFFC asserts on it)
            ldr_x(8, 8, 0x1A8),                       # 0C local player chr
            cmp_xr(8, chr_reg),                       # 10
            bne(p + 0x14, p + 0x1C),                  # 14 someone else: skip
            b(p + 0x18, go),                          # 18
            b(p + 0x1C, skip)]                        # 1C


# ---- KIN_PRESS (request kind 1 -> grant on the presser's own game)
kp_at = pc
r, pc = cave('KIN_PRESS', pc, lambda p: local_gate(p, 22, 0x11A46FC, 0x11A49C4))
recs['KIN_PRESS'] = r + [hook(0x11A46F8, kp_at, 'cbz w8, #0x11a49c4')]

# ---- KIN_EXEC (execute: authority path for the local presser)
ke_at = pc
r, pc = cave('KIN_EXEC', pc, lambda p: local_gate(p, 19, 0x119EFA0, 0x119F034))
recs['KIN_EXEC'] = r + [hook(0x119EF9C, ke_at, 'cbz w8, #0x119f034')]

# ---- KIN_CONTRACT
recs['KIN_CONTRACT'] = [patch(0xD8A004, 'cbz w8, #0xd8a1a0', NOP)]

# ---- KIN_PROMPT_DIAG (optional)
recs['KIN_PROMPT_DIAG'] = [patch(0x119EF24, 'csel w8, wzr, w8, eq', cset_w_ne(0)),
                           patch(0x119EF28, 'and w0, w8, w9', NOP)]

assert pc <= CAVE_END, hex(pc)
print('\n'.join(listing))
print('caves end at 0x%X (limit 0x%X)' % (pc, CAVE_END))

out = ['"""Live patch groups for the kin summoning circles: (offset_from_main, orig_hex, new_hex, is_code).',
       'Generated by kincircle_gen.py (design and listings there, reasoning in kin_circle_notes.md).',
       'ORDER = press + execute + contract (needs the shipped KIN_* records for 0xD8A200 and the map simulation that',
       'creates the circles). KIN_PROMPT_DIAG is a test-only group, not in ORDER."""', '']
for g in ('KIN_PRESS', 'KIN_EXEC', 'KIN_CONTRACT', 'KIN_PROMPT_DIAG'):
    out.append('%s = [' % g)
    for off, o, n, c in recs[g]:
        out.append('    (0x%X, "%s", "%s", True),' % (off, o, n))
    out.append(']')
    out.append('')
out.append('ORDER = [KIN_PRESS, KIN_EXEC, KIN_CONTRACT]')
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'kincircle_live.py'), 'w').write('\n'.join(out) + '\n')
print('kincircle_live.py written')
