"""Kin (buddy) state of the twin games, and a way to give the local player a kin.
python diag/twin/kin.py AB                 show both games (read only)
python diag/twin/kin.py A set 601000 [rule]   write pgd+0x4688 = (601000 << 32) | species 6010 on game A;
                                           'rule' also sets par+0xC0 bit 2 (the EndIntermission kin gate)
python diag/twin/kin.py A clear            write pgd+0x4688 = -1
python diag/twin/kin.py A press BTN [SECONDS]  press BTN and print the buddy node steps for SECONDS (default 3)
Recipe (diag/net/live_enumeration_notes.md section 3):
  local pgd = [*(main+0x5B57EB8)+0x20]; pgd+0xD0 player no; pgd+0x4688 u64 = {u32 species row, u32 BuddyParam id}  [V 0xD8BA9C]
  The kin is requested in STEP_EndIntermission (par+0x50 == 28, fn 0x1150884) when byte par+0xC0 bit 2 is set:
  0xD8BA70 -> BuddyParam lookup of pgd+0x4688 high -> 0xD8B710 -> our cave -> 0xD8A200      [V]
  Player setup 0xCE7280 rewrites pgd+0x4688 from CharaInitParam row +0x2A0 (0xCE83E8..0xCE8404)  [V]
  BM = [[WCM+0x5B8]+0x10]: count +0x20, list sentinel +0x10, first node +0x18 (node +8 next, +0x10 buddy chr,
  +0x28 flag, +0x30 state step, +0x38 step)                                                 [V notes / I node layout]"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, PGD_G, PAR_G, fmt3

# BuddyParam id -> BuddySpeciesParam row (the value 0xD7C000 would put in the low half) [V regulation]
BUDDY = {601000: 6010, 602000: 6020, 603000: 6030, 604000: 6040, 607000: 6070, 609000: 6090, 610000: 6100, 613000: 6130,
         960100: 6010, 960200: 6020, 960300: 6030, 960400: 6040, 960700: 6070, 960900: 6090, 961000: 6100, 961300: 6130}
STEP = {19: 'EvilGodChangeWait', 21: 'PrepareSecond', 26: 'Intermission', 27: 'VictoryDeclaration', 28: 'EndIntermission'}


def state(w):
    out = {}
    pgd = w.q(w.g(PGD_G) + 0x20) if w.g(PGD_G) else w.null('*(main+0x5B57EB8)')
    out['pgd'] = pgd
    chr_, _, pos = w.me()
    out['pos'] = pos
    if pgd:
        out['no'] = w.d(pgd + 0xD0)
        v = w.q(pgd + 0x4688)
        out['4688'] = v
        out['40d0'] = w.b(pgd + 0x40D0)
    else:
        w.null('local PlayerGameData')
    if chr_:
        data = w.q(chr_ + 0x20)
        out['pgd_chr'] = w.q(data + 0x1D0) if data else None
        out['13b4'] = w.d(chr_ + 0x13B4)
    par = w.g(PAR_G)
    out['par'] = par
    if par:
        out['phase'] = w.d(par + 0x50)
        out['c0'] = w.b(par + 0xC0)
    wcm = w.wcm()
    x = w.q(wcm + 0x5B8) if wcm else None
    bm = w.q(x + 0x10) if x else None
    out['bm'] = bm
    nodes = []
    if bm:
        out['count'] = w.d(bm + 0x20)
        out['delcount'] = w.d(bm + 0x40)
        out['pending'] = ((w.q(bm + 0x58) or 0) - (w.q(bm + 0x50) or 0)) // 0x70
        node, k = w.q(bm + 0x18), 0
        while node and node != bm + 0x10 and k < 16:
            c = w.q(node + 0x10)
            cd = w.q(c + 0x20) if c else None
            nodes.append({'node': node, 'chr': c, 'flag': w.b(node + 0x28), 'step': w.q(node + 0x30), 'step2': w.q(node + 0x38),
                          'owner': w.i(cd + 0xB8) if cd else None, 'pos': w.chr_pos(c) if c else None,
                          'stepstate': [w.d((w.q(node + 0x30) or 0) + o) for o in (0x50, 0x54)] if w.q(node + 0x30) else None})
            node, k = w.q(node + 8), k + 1
    else:
        w.null('BuddyManager [[WCM+0x5B8]+0x10]')
    out['nodes'] = nodes
    return out


def show(w, s):
    v = s.get('4688')
    lo, hi = (v & 0xFFFFFFFF, v >> 32) if v is not None else (None, None)
    print('%s: player no %s pos %s | pgd %s (via chr %s) | pgd+0x4688 species %s buddy %s %s | pgd+0x40D0 %s | chr+0x13B4 %s' % (
        w.who, s.get('no'), fmt3(s.get('pos')), w.rel(s.get('pgd')), w.rel(s.get('pgd_chr')),
        None if lo is None else struct.unpack('<i', struct.pack('<I', lo))[0],
        None if hi is None else struct.unpack('<i', struct.pack('<I', hi))[0],
        '(valid)' if hi in BUDDY else '(NOT a BuddyParam id)', s.get('40d0'),
        None if s.get('13b4') is None else '%x' % s['13b4']))
    c0 = s.get('c0')
    print('   phase par+0x50 = %s %s | par+0xC0 = %s (bit2 kin gate %s) | BM %s count %s delete-pending %s 0x36-queue %s' % (
        s.get('phase'), STEP.get(s.get('phase'), ''), None if c0 is None else hex(c0),
        None if c0 is None else bool(c0 & 4), w.rel(s.get('bm')), s.get('count'), s.get('delcount'), s.get('pending')))
    for n in s['nodes']:
        print('   node %s chr %s owner %s flag %s step %s state %s pos %s' % (
            w.rel(n['node']), w.rel(n['chr']), n['owner'], n['flag'], w.rel(n['step']), n['stepstate'], fmt3(n['pos'])))


def main():
    games = sys.argv[1]
    verb = sys.argv[2] if len(sys.argv) > 2 else 'show'
    if verb == 'show':
        for g in games:
            w = W(g)
            show(w, state(w))
            w.report_missing()
        return
    w = W(games[0])
    s = state(w)
    if verb in ('set', 'clear'):
        if not s.get('pgd'):
            print('no local PlayerGameData; nothing written')
            return
        if verb == 'clear':
            val = 0xFFFFFFFFFFFFFFFF
        else:
            bid = int(sys.argv[3])
            if bid in BUDDY:
                val = (bid << 32) | BUDDY[bid]
            elif bid in BUDDY.values():
                bid2 = next(k for k, v in BUDDY.items() if v == bid)
                val = (bid2 << 32) | bid
            else:
                print('%d is not a BuddyParam / species id; known: %s' % (bid, sorted(BUDDY)))
                return
        w.write(s['pgd'] + 0x4688, struct.pack('<Q', val))
        print('%s: pgd+0x4688 %s -> %016x' % (w.who, None if s.get('4688') is None else '%016x' % s['4688'], val))
        if 'rule' in sys.argv and s.get('par'):
            w.write(s['par'] + 0xC0, bytes([(s.get('c0') or 0) | 4]))
            print('%s: par+0xC0 %s -> %s' % (w.who, s.get('c0'), (s.get('c0') or 0) | 4))
        print('the kin is requested when this game passes par+0x50 == 28 (EndIntermission); now %s' % s.get('phase'))
    elif verb == 'press':
        btn, secs = sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 3.0
        w.press(btn, 6, 10)
        t0 = time.time()
        while time.time() - t0 < secs:
            s = state(w)
            print('%.1f s: count %s nodes %s' % (time.time() - t0, s.get('count'),
                                                 [(w.rel(n['step']), n['stepstate'], n['flag']) for n in s['nodes']]))
            time.sleep(0.5)
    w.report_missing()


if __name__ == '__main__':
    main()
