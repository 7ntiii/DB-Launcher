"""zep5_gen.py -> zep5_live.py: ZEP5 groups for the zeppelin event 1120 (zeppelin5_notes.md).
Static only. python zep5_gen.py   (from diag/net). cave_lib appends its claim rows (owner zep5_gen) to
cave_registry.md (stable: re-runs reuse them).

v1 (BUILT IN since 2026-11-15, frozen here, checked against stock AND the built-in rows):
ZEP5_READY  : new strikes are made ready (+4 = 0) at the host decision (0xF114D0) and at a guest's kind-1 append
              (0xF120A8): fire / deny in the frame they are made, no 0x9F, no placeholders.
ZEP5_END    : same words as ZEP4_END (0xA0 / 0xA1 -> vt+0x40 broadcast, attr 0x00 = guests + own echo).
ZEP5_FIREANY_CAVE + ZEP5_FIREANY : host only, granted strike whose requester chr is not found here (remote
              requester): fire anyway with requester handle -1 (0xB0FBA0 handles -1 at 0xB0FC5C).
v2 (new, zeppelin5_notes 7):
ZEP5_ONCE_CAVE + ZEP5_ONCE : the host decision ignores a request of a player who already has a BUSY ship
              (ship +8 = that player, +0x38 != 0) or a pending strike: one Transmitter use = one ship.
"""
import importlib.util
import os
import re

import cave_lib as C

HERE = os.path.dirname(os.path.abspath(__file__))
CPP = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')
HOST = 0x492AFD8        # HOST byte, 0 = host (same as ZEP_S3..S6 / ZEP3_C3)
SITE = 0xF0CD84         # fire path: cbz x21,#0xf0ce2c (skip the fire order when the requester chr is not found)
BACK = 0xF0CD88         # next word: ldr x0,[x27]
SKIP = 0xF0CE2C         # erase the strike
OSITE = 0xF11410        # decision: b #0xf11698 (into the ship choice loop)
OBACK = 0xF11698        # ship choice loop
OSKIP = 0xF11584        # queue-entry erase + return w21 (no strike made)

# context that must be stock (capstone text)
CTX = [(0xF0CD80, 'bl #0xf12440'), (0xF0CD88, 'ldr x0, [x27]'), (0xF0CE08, 'ldr w10, [x21, #8]'),
       (0xF0CE20, 'str w10, [x8, #0xd8]'), (0xF0CE28, 'bl #0xb0fba0'), (0xF0CE2C, 'ldr x8, [x19, #0x138]'),
       (0xF0CE34, 'subs x21, x8, x1'),          # x21 rewritten right after the erase target: substitute is dead
       (0xF0CCFC, 'cbz w8, #0xf0ce2c'),          # result 0 never reaches the site (denials untouched)
       (0xF114C8, 'mov w9, #1'), (0xF114E4, 'strb w9, [sp, #0x2c]'),
       (0xF120A4, 'mov w12, #1'), (0xF120B4, 'sturb w12, [x29, #-0x54]'),
       (0xF10BE4, 'mov w1, #0xa0'), (0xF10BF0, 'blr x8'), (0xF10F2C, 'mov w1, #0xa1'), (0xF10F38, 'blr x8'),
       (0xB0FC58, 'ldr w8, [x21, #8]'), (0xB0FC5C, 'cmn w8, #1'), (0xB0FC60, 'b.eq #0xb10130'),
       # ZEP5_ONCE: busy is set only by the fire path, ship+8 = strike player (0xF0CD58/0xF0CD64 -> 0xF12440)
       (0xF0CD50, 'strb w10, [x8, #0x38]'), (0xF0CD58, 'ldr w9, [x20]'), (0xF0CD64, 'str w9, [sp, #0x80]'),
       (0xF0CD4C, 'add x0, x8, #8'), (0xF12450, 'ldp x8, x9, [x1]'), (0xF1245C, 'stp x8, x9, [x0]'),
       # decision: x19 = AS, x20 = queue entry (+0 player), x8 = ships end (kept), loop 0xF11698 writes x9..x13
       (0xF11184, 'mov x19, x0'), (0xF113C4, 'ldp x26, x8, [x19, #0xf0]'), (0xF11698, 'ldp x10, x9, [x20, #0x18]'),
       (0xF1170C, 'ldrb w14, [x11, #0x1c]'), (0xF11734, 'ldrb w12, [x10, #0x38]'),
       (0xF11584, 'ldr x23, [x19, #0x118]'), (0xF11588, 'add x22, x20, #0x38'), (0xF11618, 'mov w0, w21')]


def load_v1():
    p = os.path.join(HERE, 'zep5_live.py')
    spec = importlib.util.spec_from_file_location('zep5_v1', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return {k: list(getattr(m, k)) for k in ('ZEP5_FIREANY_CAVE', 'ZEP5_FIREANY', 'ZEP5_READY', 'ZEP5_END')}


def main():
    for a, t in CTX:
        got = C.dis1(a, C.text_word(a))
        assert got == t, 'context %#x: %s != %s' % (a, got, t)
    cpp = open(CPP, encoding='utf-8', errors='replace').read()

    def built_in(off):
        m = re.search(r'DUSK_W_%X\{([^}]*)\}' % off, cpp)
        return bytes(int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]+)', m.group(1))).hex().upper() if m else None

    v1 = load_v1()
    expect = {0xF114D0: 'FF530039', 0xF120A8: 'BF431938', 0xF10BEC: '082140F9', 0xF10F34: '082140F9',
              SITE: '97C81C15', 0x563EFE0: '107603F0', 0xC501810: 'B50000B5', 0xC50183C: 'FFFFFFFF'}
    for g_ in v1.values():
        for off, orig, new, _ in g_:
            if not C.is_far(off) and not 0x563EE00 <= off < 0x563F000:
                assert C.hexw(C.text_word(off)) == orig, 'v1 stock %#x' % off
            else:
                assert orig == '00000000' and C.image_is_zero(off), 'v1 cave %#x' % off
            assert expect.get(off, new) == new
            assert built_in(off) == new, 'v1 %#x built in as %s, not %s' % (off, built_in(off), new)
    assert sum(map(len, v1.values())) == 20

    g = C.Gen('zep5_gen', out='zep5_live.py')
    n = 30
    far = g.alloc('ZEP5_ONCE', 'FAR_CODE', n * 4, 'host decision: ignore a request of a player with a busy ship '
                                                  'or a pending strike (one use = one ship)')
    a = C.Asm(far)
    a(C.ldr_x('x10', 'x19', 0xF0))                         # ships begin
    a(C.ldr_x('x11', 'x19', 0xF8))                         # ships end
    a(C.ldr_w('w12', 'x20', 0))                            # requester pno (queue entry +0)
    a.label('ship')
    a(C.cmp_xr('x10', 'x11'))
    a(C.to(C.beq, 'strikes'))
    a(C.ldrb('w16', 'x10', 0x38))                          # busy
    a(C.to(C.cbz_w, 'w16', 'nship'))
    a(C.ldr_w('w16', 'x10', 8))                            # player of the volley (fire path 0xF0CD64)
    a(C.cmp_wr('w16', 'w12'))
    a(C.to(C.beq, 'dup'))
    a.label('nship')
    a(C.add_xi('x10', 'x10', 0x40))
    a(C.to(C.b, 'ship'))
    a.label('strikes')
    a(C.ldr_x('x10', 'x19', 0x130))                        # strikes begin
    a(C.ldr_x('x11', 'x19', 0x138))                        # strikes end
    a.label('strike')
    a(C.cmp_xr('x10', 'x11'))
    a(C.to(C.beq, 'go'))
    a(C.ldrb('w16', 'x10', 0x1C))                          # pending
    a(C.to(C.cbz_w, 'w16', 'nstrike'))
    a(C.ldr_w('w16', 'x10', 0))                            # strike player
    a(C.cmp_wr('w16', 'w12'))
    a(C.to(C.beq, 'dup'))
    a.label('nstrike')
    a(C.add_xi('x10', 'x10', 0x20))
    a(C.to(C.b, 'strike'))
    a.label('go')
    a.many(lambda pc, L: C.far_return(pc, OBACK))           # stock: choose the nearest free ship
    a.label('dup')
    a(C.mov_w('w21', 'wzr'))                               # return 0, no strike, no answer
    a.many(lambda pc, L: C.far_return(pc, OSKIP))          # erase the queue entry
    words = a.words()
    assert len(words) <= n, len(words)
    cave = g.cave('ZEP5_ONCE', far, a)
    hook = g.far_hook(OSITE, 'b #0xf11698', far, scratch='x16',
                      why='x16/x17 are not used anywhere in the decision 0xF11140..0xF11D20; x10..x12 are '
                          'written before read at 0xF11698 and 0xF11584; x8 (ships end) is kept')

    def rows(rs):
        return '\n'.join('    (0x%X, "%s", "%s", %s),' % r for r in rs)

    def live_rows(rs):            # built in: the live orig IS the new word (already applied)
        return '\n'.join('    (0x%X, "%s", "%s", %s),' % (o, nw, nw, c) for o, _, nw, c in rs)

    doc = ('"""ZEP5 groups for the zeppelin event 1120. Generated by zep5_gen.py (stock words + context checked).\n'
           '(offset_from_main, orig_hex, new_hex, is_code). Apply on EVERY game after the v3.6 built-ins.\n'
           'v1 groups ZEP5_FIREANY_CAVE, ZEP5_FIREANY, ZEP5_READY, ZEP5_END are BUILT IN (2026-11-15): their stock\n'
           'lists keep the stock originals (bake: SAME); their _LIVE lists have orig == the built-in word (already\n'
           'applied on such a build: nothing to write). v2: ZEP5_ONCE_CAVE then ZEP5_ONCE (not built in; _LIVE ==\n'
           'stock). ZEP5_END has the same words as zep4_live.ZEP4_END. FAR records (0xC500000..) must be built in\n'
           'as BuiltinPatchRecord{off, NAME, {}, true} (cave_lib.cpp_rows). zeppelin5_notes.md. ONCE NOT live-tested."""\n')
    parts = [doc]
    notes = {'ZEP5_FIREANY_CAVE': '# host: granted strike, requester chr not found -> fire with requester handle -1',
             'ZEP5_FIREANY': '# trampoline + site 0xF0CD84 cbz x21,#0xf0ce2c -> b trampoline (hook LAST)',
             'ZEP5_READY': '# new strikes ready (+4 = 0): decision 0xF114D0, guest kind-1 append 0xF120A8',
             'ZEP5_END': '# 0xA0 / 0xA1: vt+0x40 broadcast attr 0x00 (= ZEP4_END)'}
    for k in ('ZEP5_FIREANY_CAVE', 'ZEP5_FIREANY', 'ZEP5_READY', 'ZEP5_END'):
        far_c = '  # FAR cave records' if any(C.is_far(r[0]) for r in v1[k]) else ''
        parts.append('%s\n%s = [%s\n%s\n]\n%s_LIVE = [  # built in: already applied\n%s\n]\n'
                     % (notes[k], k, far_c, rows(v1[k]), k, live_rows(v1[k])))
    parts.append('# v2: host decision ignores a request of a player who already has a busy ship / pending strike\n'
                 'ZEP5_ONCE_CAVE = [  # FAR cave records\n%s\n]\nZEP5_ONCE_CAVE_LIVE = list(ZEP5_ONCE_CAVE)\n'
                 % rows(cave))
    parts.append('# trampoline + site 0xF11410 b #0xf11698 -> b trampoline (hook LAST)\n'
                 'ZEP5_ONCE = [\n%s\n]\nZEP5_ONCE_LIVE = list(ZEP5_ONCE)\n' % rows(hook))
    parts.append('ORDER = [ZEP5_FIREANY_CAVE, ZEP5_FIREANY, ZEP5_READY, ZEP5_END, ZEP5_ONCE_CAVE, ZEP5_ONCE]\n'
                 'ORDER_LIVE = [ZEP5_ONCE_CAVE_LIVE, ZEP5_ONCE_LIVE]\n')
    out = '\n'.join(parts)
    print('\n'.join(g.listing))
    open(os.path.join(HERE, 'zep5_live.py'), 'w', newline='\n').write(out)
    print('wrote zep5_live.py')
    d, r = C.cpp_rows('ZEP5_ONCE_CAVE', cave)
    print(r)


if __name__ == '__main__':
    main()
