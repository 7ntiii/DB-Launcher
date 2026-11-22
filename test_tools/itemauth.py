"""READ-ONLY checker for itemauth_live.py (diag/net/itemauth_notes.md, itemauth2_notes.md). Writes nothing.
    python diag/twin/itemauth.py [GAMES=AB] [GOODS_ID ...]
Per game: ITEMAUTH_DROP words (D1 hook 0xCF8F70, D2 hook 0x15B4430, table 0xC50F24C), ITEMAUTH_GIVE words
(G1 hook 0x159CB44, G2 hook 0x15978D4), role byte (main+0x492AFD8, 0 = authority), offline flag, own player
number, own count of each goods id (inventory pgd+0x2E8; default: Fire Flask 4260, Bastard's Heart 4470,
Virtue (1) 8000 = the GIVE goods, and Star Fragment 40000 = DROP) and the world-item ids (MapItemMan lists).
DROP: before/after the death the dropper's 40000 count falls once and every game lists the same new world item.
GIVE: before/after a rewarded kill exactly ONE game (the killer's) shows +1 of one GIVE goods; the others and the
world-item lists stay unchanged. The goods are real inventory entries (pgd+0x2E8 -> list at pgd+0x5D0, entry
{id, ?, count}); goods 8000 is stored too (0xCF8E2C keeps +0xCC goods when the enemy-lot flag is set), so this
count is the right reading (itemauth3_notes.md). Needs ITEMAUTH_DROP's D1 + table (15A34AC) and the G7 cave.
Review 9: also D3/D4 (a guest's own death drops on his own game), G3..G6 (the enemy owner's killer handle carried
in the 0x14 request, KH = the handle while the host serves it), ids shown with their creator tag '(pN)'.
`take` [i:ID ...]: take-request / removal conditions per game (pickup2_notes.md): role, mode, self id, member ids,
players (pgd, player no, slot), and per world item flags / kind / taken / allowed masks with the host's verdict."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

GAMES = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].isalpha() else 'AB'
IDS = [int(x, 0) for x in sys.argv[1:] if not x.isalpha() and ':' not in x] or [4260, 4470, 8000, 40000]
# pickup2_notes.md: `take` prints the take-request / removal conditions; `i:0x12` (repeatable) limits it to those items
TAKE = 'take' in sys.argv[1:]
TAKE_IDS = [int(x[2:], 0) for x in sys.argv[1:] if x.startswith('i:')]
HOOKS = {0xCF8F70: 'D1 gate hook', 0x15B4430: 'D2 drop hook', 0x159CB44: 'G1 give hook', 0x15978D4: 'G2 award hook',
         # review 9 (review9_fix_notes.md)
         0x15AAD2C: 'D3 own-death hook (+ D3B local chr 0xC5014F0)', 0x15B4A50: 'D4 guest-create hook', 0x15AAF64: 'G3 owner-killer hook',
         0x1597CAC: 'G4 serve-0x14 hook', 0x159CA94: 'G5 give-killer hook', 0x15B4E90: 'G6 rose-killer hook'}
TABLE = 0xC50F24C
KH = 0xC50F208          # 0x10000 + carried killer handle while the host serves a 0x14 (0 otherwise)
STOCK = {0xCF8F70: 0x396F6908, 0x15B4430: 0xB40033D8,   # ldrb w8,[x8,#0xbda] / cbz x24,#0x15b4aa8
         0x159CB44: 0x940019FF, 0x15978D4: 0xB9439BE8}  # bl #0x15a3340 / ldr w8,[sp,#0x398]
G7 = None               # itemauth3: GIVE receiver's own inventory add (0x15A3340) before the popup
G7_WORD = None
try:                    # stock words of every hook from the data file (follows a re-generation)
    sys.path.insert(0, 'diag/net')
    import itemauth_live as _IA
    for _g in (_IA.ITEMAUTH_DROP, _IA.ITEMAUTH_GIVE):
        for _a, _o, _n, _c in _g:
            if _a in HOOKS:
                STOCK[_a] = int.from_bytes(bytes.fromhex(_o), 'little')
    KH = _IA.CAVES.get('KH', KH)
    G7 = _IA.CAVES.get('G7')
    G7_WORD = {a: int.from_bytes(bytes.fromhex(n), 'little') for a, o, n, c in _IA.ITEMAUTH_GIVE}.get(G7)
except Exception:
    pass
STOCK = {a: STOCK.get(a) for a in HOOKS}


def id_txt(i):
    """world-item id; bits 27..30 = creator's player number for guest-made drops / Power drops (review 9 tag)."""
    t = (i >> 27) & 0xF
    return '%x%s' % (i, '(p%d)' % t if t else '')
NAMES = {4260: 'FireFlask', 4470: 'BastardsHeart', 8000: 'Virtue1', 40000: 'StarFragment'}


def goods_count(m, pgd, gid):
    inv = pgd + 0x2E8
    n1, total = m.u32(inv + 0x2FC), m.u32(inv + 0x368)
    a1, a2 = m.u64(inv + 0x330), m.u64(inv + 0x320)
    if total + 1 > 4096:
        return None
    cnt = 0
    for k in range(total + 1):
        e = (a1 + k * 16) if k < n1 else (a2 + (k - n1) * 16 if a2 else 0)
        if not e:
            continue
        try:
            w0, w1, c = struct.unpack_from('<III', m.read(e, 16), 0)
        except Exception:
            continue
        if w0 and ((w0 & 0x0FFFFFFF) == gid or (w1 & 0x0FFFFFFF) == gid):
            cnt += c
    return cnt


for w in GAMES:
    m = Mem(w)
    b = m.base
    words = {a: m.u32(b + a) for a in HOOKS}
    state = ', '.join('%s %s' % (HOOKS[a], 'STOCK' if v == STOCK[a] else 'patched %08X' % v) for a, v in words.items())
    try:
        tab = [m.u32(b + TABLE + 4 * i) for i in range(4)]
    except Exception:
        tab = None
    role = m.read(b + 0x492AFD8, 1)[0]
    offl = m.u64(b + 0x5B65C20)
    bda = m.read(offl + 0xBDA, 1)[0] if offl else None
    gdm = m.u64(b + 0x5B57EB8)
    pgd = m.u64(gdm + 0x20) if gdm else 0
    pno = m.u32(pgd + 0xD0) if pgd else None
    counts = {'%d %s' % (gid, NAMES.get(gid, '')): (goods_count(m, pgd, gid) if pgd else None) for gid in IDS}
    im = m.u64(b + 0x5B3CDC0)
    lists = []
    for off in (0x18, 0x48, 0x78):
        node, ids = (m.u64(im + off) if im else 0), []
        while node and len(ids) < 200:
            try:
                ids.append(id_txt(m.u32(node + 0x30)))
                node = m.u64(node + 0x10)
            except Exception:
                break
        lists.append(ids)
    try:
        kh = m.u32(b + KH)
    except Exception:
        kh = None
    try:
        g7 = None if G7 is None else m.u32(b + G7)
    except Exception:
        g7 = None
    g7s = 'n/a' if G7 is None else ('present' if g7 == G7_WORD else 'MISSING (old GIVE: award = popup only)')
    print('%s: %s; table %s (GIVE needs 15A34AC); G7 cave %s; KH %s' % (
        w, state, None if tab is None else ['%X' % x for x in tab], g7s,
        None if kh is None else ('%04x' % (kh & 0xFFFF) if kh >> 16 & 1 else 'none')))
    print('   role %d (%s), offline %s, own player %s, goods %s' % (
        role, 'authority' if role == 0 else 'guest', bda, pno, counts))
    print('   world items %s %s' % ([len(x) for x in lists], lists))
    # pickup_notes.md: a world-item pick-up award (subtype 6 -> 0x15981B8 -> 0x15A5020 -> 0x15B5400) adds to the
    # inventory only in the branch 0x15B57FC, taken when the online world *(main+0x5B57E90) is null; in a match it is
    # set, so 0x15B5564 only queues the notice. Hooks that change that: STARFRAG_PICK 0x15B555C, POWERS_PICK 0x15B5560.
    try:
        world = m.u64(b + 0x5B57E90)
        w555c, w5560, w8f74 = m.u32(b + 0x15B555C), m.u32(b + 0x15B5560), m.u32(b + 0xCF8F74)
        print('   pickup path: world %s -> award %s; 0x15B555C %s, 0x15B5560 %s; item-get gate 0xCF8F74 %s' % (
            '%x' % world if world else 'null',
            'adds (0x15B57FC)' if not world else 'NOTICE ONLY (0x15B5564) unless a hook below forces the add',
            'stock' if w555c == 0xF9400108 else 'hooked %08X (STARFRAG_PICK: fragment 0x20009C40 only)' % w555c,
            'stock' if w5560 == 0xB40014E8 else 'hooked %08X (POWERS_PICK: dialog OK only)' % w5560,
            'stock' if w8f74 == 0x34000388 else 'built-in table gate %08X (ZEP3_C2)' % w8f74))
    except Exception as e:
        print('   pickup path: unreadable (%s)' % e)


# ---------------------------------------------------------------- `take`: pickup2_notes.md (read only)
# Host (role 0) serving a take request 0x1E subtype 5 {0x50001, id, count, taker player no} in 0x15A3F00:
#   H1 0x15A3F44 item id in the host's MapItemMan; H4 0x15A410C a chr with pgd+0xD0 == taker (local player
#   WCM+0x1A8 or a WCM+0x30 entry, 0x17F1940 filter 0x407); H4b 0x15A4118 its pgd [chr+0x20]+0x1D0 non-null;
#   H5 0x15A4124 slot pgd+0x104 <= 11; H6 kinds 1/2/4/5 (+0x15C): taken +0x288 bit clear (0x15A4158) and allowed
#   +0x290 bit set (0x15A4164). Reply / removal go to the member whose +0x10 == the sender id (0x15A462C, 0x15A5660).
KIND = {0: 'shared', 1: 'per-player (each once)', 2: 'owner only', 3: 'shared (all but owner)', 4: 'per-player 4',
        5: 'per-player 5'}
PER_PLAYER = (1, 2, 4, 5)


def _b(m, a):
    return m.read(a, 1)[0]


def take_report(w):
    m = Mem(w)
    b = m.base
    role = _b(m, b + 0x492AFD8)
    mgr3 = m.u64(b + 0x5B3CE08)
    mode = m.u32(mgr3 + 0x1268) if mgr3 else None
    try:
        o = m.u64(b + 0x5B44E48)
        self_id = m.u64(m.u64(o + 0xC8) + 0xB78) if o else None
    except Exception:
        self_id = None
    members = []
    mflags = []
    if mgr3:
        lo, hi = m.u64(mgr3 + 0x1248), m.u64(mgr3 + 0x1250)
        if lo and hi and 0 <= hi - lo <= 0xF8 * 40:
            members = [m.u64(e + 0x10) for e in range(lo, hi, 0xF8)]
            # pickup4_notes.md 1: the authority's own creates (subtype 4), takes (5) and answers (6) reach it only
            # over its own member link: M_SERVER +0xE0, M_SELF +0xE3 (dusk_lan.cpp constants)
            mflags = [(m.u64(e + 0x10), _b(m, e + 0xE0), _b(m, e + 0xE3)) for e in range(lo, hi, 0xF8)]
            # selflink_notes.md 1: per-member send gates in 0x1CD7340 (skip when +0xD0 != 0, when the connection
            # +0xC0 is null or its byte +0xC bit 0 is clear) and the manager's send gates
            for e in range(lo, hi, 0xF8):
                conn = m.u64(e + 0xC0)
                print('%s   member %x: server %d self %d pending %d | +0xD0 %d | conn +0xC0 %s open(+0xC bit0) %s' % (
                    w, m.u64(e + 0x10) or 0, _b(m, e + 0xE0), _b(m, e + 0xE3), _b(m, e + 0xE4), _b(m, e + 0xD0),
                    '%x' % conn if conn else 'NULL (no send)', (_b(m, conn + 0xC) & 1) if conn else '-'))
            print('%s   mgr3: state +0x126C %s (8 = match; else 0x1E needs routing bit 1 = never) | hold queue +0x15B8 %s'
                  ' with +0x14D0 %d (queue set and byte 0 = EVERY send held) | loopback +0x15C0 %s | server member '
                  '+0x658 %s id +0x668 %s' % (
                      w, m.u32(mgr3 + 0x126C), '%x' % (m.u64(mgr3 + 0x15B8) or 0), _b(m, mgr3 + 0x14D0),
                      '%x' % (m.u64(mgr3 + 0x15C0) or 0), '%x' % (m.u64(mgr3 + 0x658) or 0),
                      '%x' % (m.u64(mgr3 + 0x668) or 0)))
    if mgr3:
        # selflink_notes.md: in LAN the game's own copy travels over the SERVER member (server 1, our own game);
        # the M_SELF member is skipped by every send (0x1CD73B0: id == the +0xB78 self id)
        selfs = [x for x in mflags if x[1]]
        print('%s links: %s | server (self-link) member %s | M_SELF member %s' % (
            w, ' '.join('%x(server %d self %d)' % x for x in mflags) or '-',
            'present' if selfs else 'MISSING',
            ('id = self id (skipped by sends, normal)' if self_id is not None and
             any(x[2] and x[0] == self_id for x in mflags) else 'id != self id (sends go to it)')))
    print('%s take: role %d (%s), mode %s, self id %s, members %d %s' % (
        w, role, 'host serves subtype 5' if role == 0 else 'guest: sends subtype 5, drops others', mode,
        None if self_id is None else '%x' % self_id, len(members), ['%x%s' % (x, '=self' if x == self_id else '')
                                                                  for x in members]))
    wcm = m.u64(b + 0x5B3CD88)
    dflt = m.u64(b + 0x5B583B0)
    local = m.u64(wcm + 0x1A8) if wcm else 0
    chrs = [local] if local else []
    if wcm:
        n, arr = m.u32(wcm + 0x28), m.u64(wcm + 0x30)
        for k in range(min(n, 16)):
            c = m.u64(arr + 0x38 * k) if arr else 0
            if c and c not in chrs:
                chrs.append(c)
    slot_of = {}
    for c in chrs:
        pgd = m.u64(m.u64(c + 0x20) + 0x1D0)
        num = m.u32((pgd or dflt) + 0xD0) if (pgd or dflt) else None
        slot = _b(m, pgd + 0x104) if pgd else None
        if num is not None and pgd and slot is not None and slot <= 11:
            slot_of.setdefault(num, slot)
        print('   chr %x%s: pgd %s, player no %s, slot %s%s' % (
            c, ' (local)' if c == local else '', '%x' % pgd if pgd else 'NULL (H4b fails)', num, slot,
            '' if slot is not None and slot <= 11 else ' (H5 fails)'))
    im = m.u64(b + 0x5B3CDC0)
    seen = set()
    for li, off in enumerate((0x18, 0x48, 0x78)):
        node, k = (m.u64(im + off) if im else 0), 0
        while node and k < 200:
            k += 1
            iid = m.u32(node + 0x30)
            nxt = m.u64(node + 0x10)
            if TAKE_IDS and iid not in TAKE_IDS:
                node = nxt
                continue
            fl, typ, kind = m.u32(node + 0x58), m.u32(node + 0x68), _b(m, node + 0x15C)
            taken, allowed, owner = m.u64(node + 0x288), m.u64(node + 0x290), m.u32(node + 0x1A0)
            v = []
            if role == 0:
                for num, slot in sorted(slot_of.items()):
                    bit = 1 << slot
                    if kind in PER_PLAYER and taken & bit:
                        r = 'refuse: taken bit (H6)'
                    elif kind in PER_PLAYER and not allowed & bit:
                        r = 'refuse: not allowed (H6)'
                    else:
                        r = 'accept'
                    v.append('p%d %s' % (num, r))
            rm = ('removal to the requester only; host keeps it until all allowed bits are taken'
                  if kind in PER_PLAYER else 'removal broadcast to all + local')
            print('   item %s list %d: flags %08x (shown %d, request mark 0x4000 %d), +0x68 %d, id kind %d, '
                  'kind %d %s, owner %s [I +0x1A0], taken %03x allowed %03x | %s%s' % (
                      id_txt(iid), li, fl, fl >> 3 & 1, fl >> 14 & 1, typ, iid & 0xF, kind, KIND.get(kind, '?'),
                      owner, taken & 0xFFF, allowed & 0xFFF, rm, (' | host verdict: ' + ', '.join(v)) if v else ''))
            seen.add((li, iid))
            node = nxt
    num = None
    try:
        t = m.u64(b + 0x5B57EB8)
        p = (m.u64(t + 0x28) or m.u64(t + 0x20)) if t else 0
        num = m.u32(p + 0xD0) if p else None
    except Exception:
        pass
    return role, num, seen


if TAKE:
    # pickup3_notes.md: per game role + player number, and the items only one game lists (a drop made by a game
    # that is not the authority, or never pushed / never received)
    got = {}
    for w in GAMES:
        try:
            got[w] = take_report(w)
        except Exception as e:
            print(w, 'take: unreadable (%s)' % e)
    if len(got) >= 2:
        auth = [w for w, (r, n, s) in got.items() if r == 0]
        print('roles: %s%s' % (', '.join('%s role %d player no %s' % (w, r, n) for w, (r, n, s) in got.items()),
                               ' | !!! %d games act as authority (role 0): %s' % (len(auth), ''.join(auth))
                               if len(auth) != 1 else ''))
        for w, (r, n, s) in got.items():
            others = set().union(*[x[2] for k, x in got.items() if k != w])
            only = sorted(s - others)
            if only:
                print('only on %s: %s' % (w, ' '.join('L%d:%s' % (li, id_txt(i)) for li, i in only)))
