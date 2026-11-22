"""Rule set state (Standard / No Alliances / Bloodbound) as each twin game holds it. READ-ONLY (only Mem.read).
Static basis and [V]/[I] marks: diag/net/rulesets_notes.md.
python diag/twin/rules.py [GAMES=AB] [-v]        (-v: also the PhaseInfo row ids of the four rounds)

Per game:
  rule      byte main+0x5B65C70: 0 Standard, 1 No Alliances, 2 Bloodbound (text 40101 + rule, 0x1313DFC) [V].
            Written only by message 0x19 (0x14DEB88), the stage reset 0x113F380 (strb wzr) and the
            single-play copy 0x1147608 [V].
  phases5   byte main+0x5B65C48 (0x19 +0x49; 1 = 5 phases, unused by the data)
  mtype     byte main+0x5A4D404: 1 Casual, 0 Ranked text (menu functor 0x141EB00 writes 1) [V]
  scorekind byte main+0x5A4D405 (0x19 +0x48; score manager kind, PhaseInfo 'm')
  gd        gamedata = *(main+0x5B65C20): +0xBDA offline flag, +0xB10 map variant (EnvEventLot 0x114E3C8 /
            0x19 +0x4C), +0xAD8 row key (assist writes 0x0A000000)
  menu      room = *(*(main+0x5B44248)+0xC0), u32 room+0xE4 = the rule list's checked items: bit0 Standard,
            bit1 No Alliances, bit2 Bloodbound (confirm functor 0x141F220) [V]; 'pick' = the rule the
            rulesets design would derive from it (lowest set bit) [I design choice]
  host      byte main+0x492AFD8 (0 = host)
  mode      mgr3 = *(main+0x5B3CE08): +0x1268 (6 = online/guest mode, every LAN game), +0x126C session state
  players   every PlayerGameData (local at GDM+0x20/+0x28, pool GDM+0x30 + i*0x47F0): no +0xD0, team u8 +0x104
            (message 4 byte; the assist gives team = index), +0x46A0 takes part, +0x42A4 spare lives
  pairs     alliance deque AM = *(main+0x5B3CDD0): entries {a, b, c, flag +0xC, slot +0x10} (32 bytes,
            map +0x10, start +0x30, count +0x38, 128 per block). In Bloodbound the pairs ARE these entries
            (team Virtue 0xD17880, result-row team +0x18C = entry slot 0x1162BF8) [V]
  rows      result rows par+0x3968 (0x190 each, count par+0x45F0): no +0, state +0x10, rank +0x20,
            place +0x50 (Outcome), team +0x18C
Bloodbound additions (diag/net/bloodbound_notes.md):
  entries   every alliance entry in full: a +0, b +4, leader +8, u8 +0xC (w4: 1 = phase-start pact, not
            discardable [I]), slot +0x10 (= team id), SpEffect ids +0x14/+0x18, u8 +0x1C apply-pending,
            u8 +0x1D formed at phase start (AM+0x174) [V 0x10AD600 / 0x10B1B40]; there is no Bloodbound flag
            in the entry (the kind stays in the 0x4B message) [V]
  hook      word at 0x10AC510: stock 81 00 00 54 (b.ne 0x10AC520) or BB_PAIRS (b to the trampoline)
  bbbox     BB_BOX design address (FAR_DATA, NOT claimed yet; set BB_BOX below once cave_lib claims it):
            {u8 rule 2 = valid, u8 k, k x (a, b)}
  partner   u32 *(main+0x5B55D30)+0x170: the local player's partner (0x10B3224, rule 2) [V]
  -v        also: phase entries par+0x33D0 (0x60 each, count par+0x3858): no, rank +0x10, team rank +0x20,
            state +0x40; team list R+0xCB8 (R = par+0x3940; 0x40 each, count R+0xDC0: slot +0, +0x10, +0x20,
            state +0x30) and the same in the Outcome copy par[0x4708] (+0xCB8 / +0xDC0)
At the end: whether the pairs (a, b, slot) are the same on every game read.
"""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

RULE, PHASES5, MTYPE, SCOREKIND = 0x5B65C70, 0x5B65C48, 0x5A4D404, 0x5A4D405
GAME_GLOBAL, G2, MGR3, GDM, AM_PTR, PAR, HOST = 0x5B65C20, 0x5B44248, 0x5B3CE08, 0x5B57EB8, 0x5B3CDD0, 0x5B3CDF8, 0x492AFD8
RULE_NAMES = {0: 'Standard', 1: 'No Alliances', 2: 'Bloodbound'}
NONE = 0xFFFFFFFF
BB_HOOK, BB_HOOK_STOCK = 0x10AC510, 0x54000081
BB_BOX = 0xC50F210            # design value only (bloodbound_notes 1d); not claimed in cave_registry.md
PARTNER_G = 0x5B55D30         # GOT 0x59E18F0 -> this global; +0x170 partner id (0x10B3224)
R_OFF = 0x3940                # R = par+0x3940 (R+4 team flag = par+0x3944, R+0x28 rows = par+0x3968)
MR_PTR = 0x4708               # par[0x4708] = the Outcome's copy of R

args = [a for a in sys.argv[1:] if not a.startswith('-')]
verbose = '-v' in sys.argv
games = args[0] if args else 'AB'


def u8(b, o): return b[o]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def i32(b, o): return struct.unpack_from('<i', b, o)[0]
def u64(b, o): return struct.unpack_from('<Q', b, o)[0]


def mask_text(m):
    if m is None:
        return 'n/a'
    names = [n for bit, n in ((1, 'Standard'), (2, 'No Alliances'), (4, 'Bloodbound')) if m & bit]
    return '%#x (%s)' % (m, ', '.join(names) or 'none')


def pick(m):
    if not m:
        return None
    return 0 if m & 1 else (1 if m & 2 else (2 if m & 4 else None))


def pgds(m):
    g = m.u64(m.base + GDM)
    if not g:
        return []
    head = m.read(g, 0x38)
    local = u64(head, 0x28) or u64(head, 0x20)
    cand = [('gdm+%x' % o, u64(head, o)) for o in (0x20, 0x28)]
    pool = u64(head, 0x30)
    if pool:
        cand += [('pool%d' % i, pool + i * 0x47F0) for i in range(12)]
    out, seen = [], set()
    for tag, p in cand:
        if not p or p in seen:
            continue
        seen.add(p)
        try:
            no = m.u32(p + 0xD0)
            team = m.read(p + 0x104, 1)[0]
            part = m.read(p + 0x46A0, 1)[0]
            stock = m.read(p + 0x42A4, 1)[0]
        except Exception:
            continue
        if no == NONE:
            continue
        out.append((tag + ('*' if p == local else ''), no, team, part, stock))
    return out


def alliances(m):
    am = m.u64(m.base + AM_PTR)
    if not am:
        return None, []
    h = m.read(am, 0x40)
    mp, start, count = u64(h, 0x10), u64(h, 0x30), u64(h, 0x38)
    out = []
    for i in range(min(count, 16)):
        k = start + i
        block = m.u64(mp + 8 * (k >> 7))
        e = m.read(block + (k & 0x7F) * 0x20, 0x20)
        out.append({'a': i32(e, 0), 'b': i32(e, 4), 'c': i32(e, 8), 'flag': e[0xC], 'slot': i32(e, 0x10),
                    'sp': (i32(e, 0x14), i32(e, 0x18)), 'pending': e[0x1C], 'start': e[0x1D]})
    return am, out


def try_read(m, a, n):
    try:
        return m.read(a, n)
    except Exception:
        return None


def team_list(m, r, tag):
    n = m.u64(r + 0xDC0)
    if n > 4:
        print('    %s team list: count %d (bad)' % (tag, n))
        return
    for i in range(n):
        t = m.read(r + 0xCB8 + 0x40 * i, 0x40)
        print('    %s team %d: slot %d +0x10 %d +0x20 %d state(+0x30) %08x +0x38 %d' % (
            tag, i, i32(t, 0), i32(t, 0x10), i32(t, 0x20), u32(t, 0x30), i32(t, 0x38)))


pair_sets = {}
for w in games:
    try:
        m = Mem(w)
    except Exception as e:
        print(w, 'no debug server:', e)
        continue
    b = m.base
    rule = m.read(b + RULE, 1)[0]
    p5, mt, sk = m.read(b + PHASES5, 1)[0], m.read(b + MTYPE, 1)[0], m.read(b + SCOREKIND, 1)[0]
    host = m.read(b + HOST, 1)[0]
    gd = m.u64(b + GAME_GLOBAL)
    gdt = 'gd none'
    if gd:
        gdt = 'bda %d variant(B10) %d key(AD8) %08x' % (m.read(gd + 0xBDA, 1)[0], i32(m.read(gd + 0xB10, 4), 0),
                                                       m.u32(gd + 0xAD8))
    g2 = m.u64(b + G2)
    room = m.u64(g2 + 0xC0) if g2 else 0
    menu = m.u32(room + 0xE4) if room else None
    mgr3 = m.u64(b + MGR3)
    mode = '%d/%d' % (m.u32(mgr3 + 0x1268), m.u32(mgr3 + 0x126C)) if mgr3 else '-'
    pk = pick(menu)
    print('%s %s | rule %d (%s) | phases5 %d | mtype %d (%s) | scorekind %d | %s | mode/state %s' % (
        w, 'HOST' if host == 0 else 'guest(%d)' % host, rule, RULE_NAMES.get(rule, '?'), p5, mt,
        {0: 'Ranked', 1: 'Casual'}.get(mt, '?'), sk, gdt, mode))
    print('  menu choice room+0xE4 %s -> pick %s' % (mask_text(menu), RULE_NAMES.get(pk, '-') if pk is not None else '-'))
    for tag, no, team, part, stock in pgds(m):
        print('  %-8s player no %d team %d takes-part %d spare-lives %d' % (tag, no, team, part, stock))
    hook = u32(m.read(b + BB_HOOK, 4), 0)
    box = try_read(m, b + BB_BOX, 12)
    if box is None:
        boxt = 'unreadable'
    else:
        k = min(box[1], 4)
        boxt = 'rule %d k %d pairs %s' % (box[0], box[1], ' '.join('(%d,%d)' % (box[2 + 2 * i], box[3 + 2 * i])
                                                                  for i in range(k)) or '-')
    pg = m.u64(b + PARTNER_G)
    partner = i32(m.read(pg + 0x170, 4), 0) if pg else None
    print('  bloodbound: hook 0x10AC510 %08x (%s) | box main+%#x %s | local partner(+0x170) %s' % (
        hook, 'stock b.ne' if hook == BB_HOOK_STOCK else 'PATCHED', BB_BOX, boxt,
        partner if partner is not None else '-'))
    am, al = alliances(m)
    if am is None:
        print('  alliances: no manager')
    else:
        print('  alliances (AM %x, +0x8C %d, +0x174 %d, count +0x38 %d): %d read' % (
            am, m.read(am + 0x8C, 1)[0], m.read(am + 0x174, 1)[0], m.u64(am + 0x38), len(al)))
        for e in al:
            print('    %d + %d (leader %d) slot %d flag(+0xC) %d speffects %d/%d pending %d phase-start %d' % (
                e['a'], e['b'], e['c'], e['slot'], e['flag'], e['sp'][0], e['sp'][1], e['pending'], e['start']))
        pair_sets[w] = sorted((min(e['a'], e['b']), max(e['a'], e['b']), e['slot']) for e in al)
    par = m.u64(b + PAR)
    if not par:
        print('  no stage')
        continue
    print('  stage step %d round %d' % (m.u32(par + 0x50), m.u32(par + 0xB8)))
    if verbose:
        for r in range(1, 5):
            cfg = m.u64(par + 0xD0 + 8 * (r - 1))
            print('    round %d PhaseInfo row %s' % (r, m.u32(cfg + 8) if cfg else '-'))
        en = m.u64(par + 0x3858)
        for i in range(min(en, 12)):
            e = m.read(par + 0x33D0 + 0x60 * i, 0x60)
            print('    entry %d no %d rank %d team rank %d state %08x' % (i, i32(e, 0), i32(e, 0x10), i32(e, 0x20),
                                                                         u32(e, 0x40)))
    tm = m.read(par + R_OFF + 4, 1)[0]
    print('  result team mode (R+4) %d' % tm)
    rn = m.u32(par + 0x45F0)
    for i in range(min(rn, 8)):
        row = m.read(par + 0x3968 + 0x190 * i, 0x190)
        print('  row %d no %d state %08x rank %d place %d team %d' % (i, i32(row, 0), u32(row, 0x10), u32(row, 0x20),
                                                                     i32(row, 0x50), i32(row, 0x18C)))
    if verbose:
        team_list(m, par + R_OFF, 'R')
        mr = m.u64(par + MR_PTR)
        if mr:
            team_list(m, mr, 'Outcome copy')

if len(pair_sets) >= 2:
    first = next(iter(pair_sets.values()))
    same = all(v == first for v in pair_sets.values())
    print('pairs (a, b, slot) equal on all games read: %s' % ('yes' if same else 'NO'))
    for w, v in pair_sets.items():
        print('  %s %s' % (w, v))
