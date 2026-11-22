"""trespasser_flow_gen.py -> trespasser_flow_live.py (static, run from the workspace root or diag/net).

Topic: why the client switches the Trespasser chr off when a joint struggle forms, and the faithful LAN fix.
Notes: trespasser_flow_notes.md. Nothing is applied or built by this script; it only reads the nso dumps,
asserts the static facts the notes rely on, checks the patch words and writes the live data file.

Groups written (offset_from_main, orig_hex, new_hex, is_code):
  TF_SPECIAL_END  the server's part of CSChrSpecialInitStateModule (0x82) in LAN: every game runs the 2-s
                  special-init timer (GameSystemParam row 0 +0x20C) and ends the state itself, as offline does.
                  Byte-identical to smallgaps2_live.py SPECIAL_INIT (apply one of the two names, not a mix).
  TF_NOHIDE_A     fallback only: drop the per-frame removal call 0x101D4B4 (path a). Path b (0x1024130) is the
                  kind-4 mirror of path a on the deciding game and cannot fire without it. Narrower than
                  JS_NOHIDE (js_nohide_live.py), which nops both.
"""
import array
import glob
import os
import re
import struct
import sys

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.dirname(os.path.dirname(HERE))
NSO = os.path.join(HERE, 'nso')
TEXT = open(os.path.join(NSO, 'main_text.bin'), 'rb').read()
DATA = open(os.path.join(NSO, 'main_data.bin'), 'rb').read()
DATA_BASE = 0x563F000
W = array.array('I')
W.frombytes(TEXT[:len(TEXT) // 4 * 4])
MD = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
NOP = 0xD503201F
OUT = os.path.join(HERE, 'trespasser_flow_live.py')


def word(a):
    return W[a // 4]


def dis(a):
    i = next(MD.disasm(TEXT[a:a + 4], a))
    return f'{i.mnemonic} {i.op_str}'.strip()


def hx(v):
    return struct.pack('<I', v).hex().upper()


def ctx(a, text):
    got = dis(a)
    assert got == text, f'{a:#x}: expected {text!r}, got {got!r}'


def bl_callers(tgt):
    out = []
    for i, x in enumerate(W):
        if (x >> 26) in (0x25, 0x05):
            off = x & 0x3FFFFFF
            if off & (1 << 25):
                off -= 1 << 26
            if i * 4 + off * 4 == tgt:
                out.append(i * 4)
    return sorted(out)


def data_q(a):
    return struct.unpack_from('<Q', DATA, a - DATA_BASE)[0]


# ---------------------------------------------------------------- static facts the notes rely on [V]
# 1. the removal ("hide") 0x102828C: clear ins+0x362, set chr data +0xA0, re-evaluate, queue the chr id
ctx(0x10282DC, 'strb wzr, [x19, #0x362]')
ctx(0x10282F0, 'strb w9, [x8, #0xa0]')
ctx(0x10282F4, 'bl #0x173b1ec')
ctx(0x1028314, 'bl #0x10293c0')                      # functor 0x56ED870 -> 0x1032CC0 pushes chr id to ins+0x368
ctx(0x1032CF0, 'strh w9, [x10], #2')
assert bl_callers(0x102828C) == [0x101D4B4, 0x1024130]
# 2. the guard 0x1022C78: "mode 6" is the MATCH PHASE (par vt+0x60 == 6 = UpdatePhase), not the net mode
ctx(0x1022CCC, 'adrp x8, #0x5b3c000')
ctx(0x1022CD0, 'add x8, x8, #0xdf8')                 # par = *(main+0x5B3CDF8)
ctx(0x1022CE0, 'ldr x8, [x8, #0x60]')
ctx(0x1022CE8, 'cmp w0, #6')
ctx(0x1022D00, 'ldrb w8, [x8, #0x750]')              # gl = *(main+0x5B3CDB0): Ritual-Site manager, 0 = sites open
# 3. per-frame path a: +0x362 && guard && [chr+0x2470]+0x240 (CSChrSpecialInitStateModule) byte +0x10
ctx(0x101D45C, 'ldrb w8, [x19, #0x362]')
ctx(0x101D4A0, 'ldr x8, [x8, #0x240]')
ctx(0x101D4A8, 'ldrb w8, [x8, #0x10]')
ctx(0x101D4B4, 'bl #0x102828c')
ctx(0x1024130, 'bl #0x102828c')
# 4. +0x362 is set only by the instance ctor (one-shot per instance and round)
ctx(0x101A6F4, 'strb w8, [x19, #0x362]')
# 5. after removal: wait for the chr's asset (chr+0xA8C) and set it to GameSystemParam +0x2E0
ctx(0x101D524, 'add x1, x0, #0xa8c')
ctx(0x101D680, 'ldr w1, [x8, #0x2e0]')
ctx(0x101D68C, 'bl #0xfce6c0')
# 6. CSChrSpecialInitStateModule (0x82): update returns in mode 6, timer only offline, state 2 only from server
ctx(0xE4A124, 'ldr w8, [x8, #0x1268]')
ctx(0xE4A12C, 'b.eq #0xe4a1e8')
ctx(0xE4A23C, 'bl #0xe4a26c')                        # offline auto start (owner only, 0x17EE470 in 0xE4A26C)
ctx(0xE4A29C, 'bl #0x17ee470')
ctx(0xE4A458, 'b.eq #0xe4a4f8')
ctx(0xE4A4EC, 'ldr s0, [x8, #0x20c]')                # timer = GameSystemParam row 0 +0x20C (= 2)
ctx(0xE4A404, 'tbz w2, #0, #0xe4a418')               # state 2 only with w2 = 1
ctx(0xED5D34, 'cset w2, eq')                         # reader: w2 = (sender == server member mgr3+0x678)
ctx(0xED5D38, 'bl #0xe4a374')
assert bl_callers(0xE4A26C) == [0xE4A23C, 0x193E730]  # auto start + tail call from TAE/behaviour code
ctx(0x193E730, 'b #0xe4a26c')
ctx(0x173F78C, 'bl #0xe4a5c4')                       # release (state 0) when +0x10 && !+0x11
# 7. who clears data+0xA0 again: the warp 0x176E3F8 has one caller, a vtable slot (not the enemy's)
assert bl_callers(0x176E3F8) == [0x17CDED4]
assert data_q(0x572D000) == 0x17CDE90               # slot 0x870 of vtable 0x572C790
assert data_q(0x572B108 + 0x870) == 0x1788FDC       # EnemyIns overrides slot 0x870 (no +0xA0 clear)
ctx(0xE8A36C, 'strb wzr, [x8, #0xa0]')               # "enable chr" 0xE8A340
ctx(0x1114C3C, 'bl #0xe8a340')                       # phase map apply 0x1114A60 ...
ctx(0x114FC4C, 'bl #0x1114a60')                      # ... from PrepareThird, right before ...
ctx(0x114FC60, 'bl #0x10430c0')                      # ... the struggle manager rebuild

# ---------------------------------------------------------------- round 2 facts (trespasser_flow2_notes.md) [V]
# 8. every writer of the module state: the 4 callers of the apply 0xE4A374 (no other code sets +0x10 / +0x11 = 1)
assert bl_callers(0xE4A374) == [0xE4A1E4, 0xE4A328, 0xE4A674, 0xED5D38]
ctx(0xE4A414, 'cbz w8, #0xe4a428')                   # state 1 applies only when +0x10 == 0
ctx(0xE4A430, 'strh w9, [x19, #0x10]')               # ... +0x10 = +0x11 = 1
ctx(0xE4A438, 'strb w8, [x19, #0x19]')               # +0x19 = w2 of that state 1 (1 = local start, 0 = a peer's 0x82)
ctx(0xE4A3B0, 'strb wzr, [x19, #0x10]')              # state 0 clears +0x10 only (+0x11 kept)
ctx(0xE4A408, 'strb wzr, [x19, #0x11]')              # state 2 clears +0x11 (needs w2 = 1)
# 9. auto start (0xE4A1FC..0xE4A23C, reached only when mode != 6 or TF_SPECIAL_END): +0x10 == 0, HP >= 1,
#    !chr+0x12C5 bit 26, data+0xA0 == 0 -> 0xE4A26C, which runs only on the game where 0x17EE470 says "owned here"
ctx(0xE4A13C, 'cbz w8, #0xe4a1fc')
ctx(0xE4A20C, 'cmp w9, #1')
ctx(0xE4A228, 'tbnz w9, #0x1a, #0xe4a140')
ctx(0xE4A234, 'cbnz w8, #0xe4a140')
ctx(0x17EE5A0, 'ldrsh w8, [x9, x8, lsl #1]')         # owned = NetChrSync owner[handle] >= 0 (|| vt+0x688, bit21)
# 10. release (state 0, broadcast) is in the chr update 0x173F3C0 and needs the AI module [chr+0x2470]+0x88 active
assert bl_callers(0xE4A5C4) == [0x173F78C]
ctx(0x173F6B4, 'ldrb w10, [x9, #0xc90]')
ctx(0x173F6B8, 'ldrb w11, [x9, #0xc91]')
ctx(0x173F6C4, 'ldrb w9, [x9, #0xd48]')
ctx(0x173F6C8, 'cbz w9, #0x173f7ac')                 # AI not active -> no release at all
assert bl_callers(0x173F3C0) == [0x1784F1C, 0x17AE56C]
assert data_q(0x572B108 + 0xF8) == 0x1784F00        # EnemyIns vt+0xF8 -> chr update (release)
assert bl_callers(0xE4A0FC) == [0x1740D30, 0x17440F4]
assert data_q(0x572B108 + 0x170) == 0x1743D60       # EnemyIns vt+0x170 -> module update (auto start, timer)
# 11. TAE / behaviour start: event case in 0x193C800 -> +0x10 == 0 -> tail call 0xE4A26C (owner only)
ctx(0x193E70C, 'ldrb w8, [x0, #0x10]')
ctx(0x193E710, 'cbnz w8, #0x193c910')
# 12. 0x82 receiver: applied to the chr whatever its owner; w2 = (sender == server member)
ctx(0xED5D08, 'bl #0x17e7828')
ctx(0xED5D24, 'ldr x8, [x8, #0x678]')
# 13. the struggle code never writes HP / max HP (no str to +0x290 / +0x294 in 0x1018000..0x1048000)
_hp_st = []
for _i in MD.disasm(TEXT[0x1018000:0x1048000], 0x1018000):
    if _i.mnemonic.startswith('st') and ('#0x290]' in _i.op_str or '#0x294]' in _i.op_str):
        _hp_st.append((hex(_i.address), _i.op_str))
assert not _hp_st, _hp_st

# ---------------------------------------------------------------- groups
GROUPS = {}


def nop_patch(a, text):
    ctx(a, text)
    return (a, hx(word(a)), hx(NOP), True)


def word_patch(a, text, new, new_text):
    ctx(a, text)
    got = next(MD.disasm(struct.pack('<I', new), a))
    got = f'{got.mnemonic} {got.op_str}'.strip()
    assert got == new_text, f'{a:#x}: new word {new:#010x} is {got!r}, expected {new_text!r}'
    return (a, hx(word(a)), hx(new), True)


GROUPS['TF_SPECIAL_END'] = [
    nop_patch(0xE4A12C, 'b.eq #0xe4a1e8'),   # module update (auto start owner-only + 2-s timer + state 2) runs in LAN
    nop_patch(0xE4A458, 'b.eq #0xe4a4f8'),   # state-1 apply arms the timer (GameSystemParam +0x20C) in LAN
]
# Round 2: TF_SPECIAL_END also turns on the OFFLINE AUTO START in LAN (0xE4A1FC..0xE4A23C): the owning game
# restarts the spawn-in whenever +0x10 is 0, i.e. right after every release - also on an owner whose copy is
# dormant (no AI -> never released). Online clients never auto start (the update returns in mode 6). TF_TIMER_ONLY
# keeps the online client behaviour (no auto start) and only adds the server's part: the 2-s timer and state 2.
# Same registers, same flags: cmp w8, #6 at 0xE4A128 is still live at 0xE4A138 (mov / ldrb set no flags).
GROUPS['TF_TIMER_ONLY'] = [
    word_patch(0xE4A12C, 'b.eq #0xe4a1e8', 0xAA0103F4, 'mov x20, x1'),
    word_patch(0xE4A130, 'ldrb w8, [x0, #0x10]', 0xAA0003F3, 'mov x19, x0'),
    word_patch(0xE4A134, 'mov x20, x1', 0x39404268, 'ldrb w8, [x19, #0x10]'),
    word_patch(0xE4A138, 'mov x19, x0', 0x54000040, 'b.eq #0xe4a140'),  # mode 6: skip the auto start, keep the timer
    nop_patch(0xE4A458, 'b.eq #0xe4a4f8'),   # state-1 apply arms the timer in LAN (same word as TF_SPECIAL_END)
]
GROUPS['TF_NOHIDE_A'] = [
    nop_patch(0x101D4B4, 'bl #0x102828c'),   # fallback only: no per-frame removal (path a)
]
COMMENTS = {
    'TF_SPECIAL_END': '[V code, I effect] SUPERSEDED by TF_TIMER_ONLY (round 2): also enables the offline auto start '
                      'in LAN (= smallgaps2 SPECIAL_INIT, byte-identical)',
    'TF_TIMER_ONLY': '[V code, I effect] server part of the 0x82 special-init state only: 2-s timer + local state 2 '
                     'on every game, no auto start in LAN (offline path unchanged). Undo TF_SPECIAL_END first',
    'TF_NOHIDE_A': '[V code, I effect] FALLBACK only if TF_SPECIAL_END is not enough: no per-frame removal 0x101D4B4',
}
# groups that share a word with a different new value: apply only one of each pair
EXCLUSIVE = {('TF_TIMER_ONLY', 'TF_SPECIAL_END'), ('TF_TIMER_ONLY', 'smallgaps2_live.py')}

# ---------------------------------------------------------------- collision checks
same, clash, alt = [], [], []
for g, recs in GROUPS.items():
    for a, o, n, _ in recs:
        for g2, recs2 in GROUPS.items():
            for a2, o2, n2, _ in recs2:
                if g2 != g and a2 == a and n2 != n:
                    assert (g, g2) in EXCLUSIVE or (g2, g) in EXCLUSIVE, (g, g2, hex(a))
for f in sorted(glob.glob(os.path.join(WS, 'diag', '*', '*_live.py'))):
    if os.path.abspath(f) == os.path.abspath(OUT):
        continue
    s = open(f, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'\(\s*(0x[0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]*)"', s):
        a = int(m.group(1), 16)
        for g, recs in GROUPS.items():
            for a2, o2, n2, _ in recs:
                if a2 != a:
                    continue
                rec = (g, os.path.basename(f), hex(a), m.group(3))
                if m.group(3).upper() == n2:
                    same.append(rec)
                elif (g, os.path.basename(f)) in EXCLUSIVE:
                    alt.append(rec)
                else:
                    clash.append(rec)
assert not clash, clash
mine = {a: (o, n) for g in GROUPS.values() for a, o, n, _ in g}
cpp = open(os.path.join(WS, r'src\lichii\src\core\file_sys\patch_manager.cpp'), encoding='utf-8',
           errors='replace').read()
for a in mine:
    assert f'DUSK_W_{a:X}' not in cpp, f'{a:#x} already a built-in record'

# ---------------------------------------------------------------- write
lines = ['"""Trespasser flow (static, trespasser_flow_notes.md): (offset_from_main, orig_hex, new_hex, is_code).',
         'Generated by trespasser_flow_gen.py (stock words via capstone, context asserts, collisions vs every',
         'diag/*/*_live.py and patch_manager.cpp). In-place words, no caves. Not live-tested. Apply on EVERY game.',
         'Round 2 (trespasser_flow2_notes.md): TF_TIMER_ONLY + JS_NOHIDE (js_nohide_live.py). TF_TIMER_ONLY and',
         'TF_SPECIAL_END / smallgaps2 SPECIAL_INIT share 0xE4A12C with different words: undo one before the other.',
         'TF_NOHIDE_A is a subset of JS_NOHIDE (same word 0x101D4B4, same bytes)."""', '']
for name, recs in GROUPS.items():
    lines.append(f'{name} = [  # {COMMENTS[name]}')
    for a, o, n, c in recs:
        nt = next(MD.disasm(bytes.fromhex(n), a))
        lines.append(f'    (0x{a:X}, "{o}", "{n}", {c}),  # {dis(a)} -> {nt.mnemonic} {nt.op_str}'.rstrip())
    lines.append(']')
lines.append('')
lines.append('ORDER = [' + ', '.join(g for g in GROUPS if g != 'TF_SPECIAL_END') + ']  # TF_SPECIAL_END superseded')
open(OUT, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('wrote', OUT)
print('identical records in other files (fine):', same)
print('alternative records (apply only one of the pair):', alt)
