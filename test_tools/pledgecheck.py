"""Why does a pledge at a blood pledge pillar record nothing? Read-only replay of the game's own checks.
python diag/twin/pledgecheck.py [GAMES=AB]
Run it while standing at a pillar with the prompt shown (and once more right after a press / hold).
Only READS memory through mem.Mem (never writes). Design and addresses: diag/net/pledge_static_notes.md.
Lines: [PASS] / [FAIL] / [INFO] / [ ?? ] (not evaluable from memory), code address of the test, values.
The first FAIL per game is marked. [I] = approximation of a check the game makes with a call we cannot run."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

GL_G = 0x5B3CDB0        # shelter / name-list manager gl (GOT 0x59DFEE8)                      [V]
PAR_G = 0x5B3CDF8       # stage phase object par (GOT 0x59DFEF8)                              [V]
MGR3_G = 0x5B3CE08      # session manager / transport (GOT 0x59DFEC8), mode +0x1268           [V]
WCM_G = 0x5B3CD88       # world chr manager, local chr at +0x1A8 (GOT 0x59DFE68)              [V]
DEFPGD_G = 0x5B583B0    # fallback pgd when [chr+0x20]+0x1D0 is null (0x10868A8)              [V]
GDM_G = 0x5B57EB8       # game data man: +0x20 local pgd (0xCEA240)                           [V]
GAMEDATA_G = 0x5B65C20  # +0xBDA offline flag                                                 [V]
ROLE_B = 0x492AFD8      # emulator role byte, 0 = host (PLEDGE_DECIDE / PLEDGE_RESULT caves)  [V ritual_live.py]
BTN_A_G = 0x5B45728     # x0 of 0x1B5F6FC at 0x1086AD4                                       [V]
BTN_M_G = 0x5B45958     # action-button manager used by 0x1B5AB20 (0x1B5FCB4)                [V]
REPO_G = 0x5B3CE68      # param repository; ActionButtonParam slot 0xBB8                     [V]
P_ACTIONBUTTON = 0xBB8
STATE_GETTER = 0x11528A4  # par vt+0x60 = `ldr w0,[x0,#0x50]; ret` (vtable 0x56F4568)          [V bytes, I vtable]
ROUTE_4E = 0x4C4B620    # routing byte of type 0x4E (0x4C4B3AC + 8*0x4E + 4)                 [V]
PLEDGE_IDS = (0x1450, 0x1451, 0x1464, 0x1465, 0x14B4, 0x14BE)  # ActionButtonParam ids at 0x1086A20..0x1086A4C [V]

# (offset, original LE hex, patched LE hex, name) from diag/net/ritual_live.py
PATCHES = [
    (0x108C240, '082540F9', '082140F9', 'PLEDGE_REQUEST hook (vt+0x48 -> vt+0x40)'),
    (0x1094B04, 'E8170034', 'C7A71615', 'PLEDGE_DECIDE hook (b 0x563EA20)'),
    (0x563EA20, '00000000', '88000035', 'PLEDGE_DECIDE cave word 0'),
    (0x1094B90, '81130054', 'ACA71615', 'PLEDGE_RESULT hook (b 0x563EA40)'),
    (0x563EA40, '00000000', 'A1000054', 'PLEDGE_RESULT cave word 0'),
    (0x108C24C, '10000014', '11CA1615', 'PLEDGE_SELF hook (optional; must stay off if self delivery works)'),
    (0x10921B4, 'DBE8FF97', '2BB21695', 'PLEDGE_KILL hook (optional)'),
    (0x10878D4, '20060054', '0BDC1615', 'RITUAL_LAYOUT hook'),
    (0x1087798, '083140F9', '082940F9', 'RITUAL_READ reader'),
]


class G:
    """Null-safe readers on top of mem.Mem (reads only)."""
    def __init__(self, who):
        self.who = who
        self.m = Mem(who)
        self.base = self.m.base

    def rd(self, a, n):
        if not a or a < 0x10000 or a > 0xFFFFFFFFFFFF:
            return None
        try:
            return self.m.read(a, n)
        except Exception:
            return None

    def _u(self, a, f, n):
        b = self.rd(a, n)
        return struct.unpack(f, b)[0] if b and len(b) == n else None

    def q(self, a): return self._u(a, '<Q', 8)
    def d(self, a): return self._u(a, '<I', 4)
    def i(self, a): return self._u(a, '<i', 4)
    def h(self, a): return self._u(a, '<H', 2)
    def b(self, a): return self._u(a, '<B', 1)
    def f(self, a): return self._u(a, '<f', 4)
    def g(self, off): return self.q(self.base + off)

    def rel(self, a):
        if not a:
            return 'null'
        return 'main+0x%X' % (a - self.base) if self.base <= a < self.base + 0x7000000 else '0x%x' % a


first_fail = [None]


def out(state, addr, name, detail=''):
    tag = {True: 'PASS', False: 'FAIL', None: ' ?? ', 'i': 'INFO'}[state]
    mark = ''
    if state is False and first_fail[0] is None:
        first_fail[0] = (addr, name)
        mark = '   <-- first failing check'
    print('[%s] %-10s %-50s %s%s' % (tag, addr, name, detail, mark))


def hx(v):
    return '0x%X' % v if isinstance(v, int) else str(v)


# ---------- params (layout as promptcheck.py, 0x15588C4) ----------
def prows(w, slot):
    repo = w.g(REPO_G)
    if not repo or not w.d(repo + slot):
        return []
    res = w.q(repo + slot + 8)
    m = w.q(res + 0x70) if res else None
    f = w.q(m + 0x78) if m else None
    if not f:
        return []
    n, fmt, fl = w.h(f + 0xA) or 0, w.b(f + 0x2D) or 0, w.b(f + 0x2E) or 0
    t = (fmt & 0x7F) - 2
    if t == 0:
        start, size, wide = 0x30, 12, False
    elif t == 1 or (t == 3 and not fmt & 0x80):
        start, size, wide = 0x40, 12, False
    elif t in (2, 3):
        start, size, wide = (0x40, 0x18, True) if fl & 2 else (0x40, 12, False)
    else:
        return []
    raw = w.rd(f + start, n * size) if n else b''
    if not raw:
        return []
    rows = []
    for k in range(n):
        rid = struct.unpack_from('<i', raw, k * size)[0]
        off = struct.unpack_from('<Q', raw, k * size + 8)[0] if wide else struct.unpack_from('<I', raw, k * size + 4)[0]
        rows.append((rid, f + off))
    return rows


def slist(w, head, limit=64):
    """singly linked list, next at +0 (action-button manager lists +8 / +0x10 / +0x18, 0x1B5B394) [V]"""
    res, n = [], w.q(head)
    while n and len(res) < limit:
        res.append(n)
        n = w.q(n)
    return res


def flags25(v):
    if v is None:
        return '?'
    names = [(0, 'grayout'), (1, 'seen'), (2, 'f'), (3, 'changed'), (5, 'b5'), (6, 'DECIDED'), (7, 'consumed')]
    return '%02x[%s]' % (v, ' '.join(n for bit, n in names if v >> bit & 1))


def check(who):
    first_fail[0] = None
    w = G(who)
    print('=' * 100)
    gd = w.g(GAMEDATA_G)
    m3 = w.g(MGR3_G)
    off = w.b(gd + 0xBDA) if gd else None
    mode = w.i(m3 + 0x1268) if m3 else None
    role = w.b(w.base + ROLE_B)
    print('%s: base 0x%x  offline +0xBDA = %s  mode [mgr3+0x1268] = %s  role byte main+0x%X = %s (%s)' % (
        who, w.base, off, mode, ROLE_B, role, 'host' if role == 0 else 'guest' if role is not None else '?'))

    # ---- patch words ----
    for a, orig, new, name in PATCHES:
        v = w.rd(w.base + a, 4)
        hv = v.hex().upper() if v else None
        st = 'patched' if hv == new else 'ORIGINAL' if hv == orig else 'OTHER'
        need = 'optional' not in name
        out((hv == new) if need else 'i', '0x%X' % a, name, '%s (%s)' % (hv, st))
    rb = w.b(w.base + ROUTE_4E)
    out(rb is not None and not rb & 0x60, '0x%X' % ROUTE_4E, 'routing byte 0x4E: bits 5/6 clear = every member', hx(rb))

    gl, par = w.g(GL_G), w.g(PAR_G)
    wcm = w.g(WCM_G)
    chr_ = w.q(wcm + 0x1A8) if wcm else None
    cd = w.q(chr_ + 0x20) if chr_ else None
    p = w.q(cd + 0x1D0) if cd else None
    pd = p or w.g(DEFPGD_G)
    pno = w.i(pd + 0xD0) if pd else None
    ctype = w.i(cd + 0x18) if cd else None
    team_p = w.b(p + 0x104) if p else None
    gdm = w.g(GDM_G)
    lpgd = w.q(gdm + 0x20) if gdm else None

    # ---- state ----
    if not gl:
        out(False, '-', 'gl *(main+0x5B3CDB0)', 'null')
        return
    pb, pe = w.q(gl + 0x500), w.q(gl + 0x508)
    pillars = []
    if pb and pe and pb <= pe <= pb + 16 * 256:
        raw = w.rd(pb, pe - pb) if pe > pb else b''
        for k in range(0, len(raw or b''), 16):
            e = raw[k:k + 16]
            pillars.append((pb + k, struct.unpack_from('<I', e, 0)[0], e[4], struct.unpack_from('<I', e, 8)[0], e[0xD], e))
    pled = w.rd(gl + 0x520, 12)
    print('pledges gl+0x520..+0x52B (team -> side, FF none): %s' % (pled.hex(' ') if pled else None))
    print('pillar list gl+0x500..gl+0x508: %d entries' % len(pillars))
    ents = w.q(gl + 0x4F8) or 0
    sites = {}
    for k in range(min(ents, 16)):
        e = gl + 0x10 + k * 0x1A0
        sites[w.b(e)] = w.b(e + 0x188)
    for a, pid, side, hnd, fl, e in pillars:
        print('   %s id 0x%08X (site %d, open %s) side +4 = %s handle +8 = 0x%08X flag +0xD = %s  raw %s' % (
            w.rel(a), pid, pid & 0xFF, {0: 'yes', None: 'no site'}.get(sites.get(pid & 0xFF), 'NO (closed)'),
            side, hnd, fl, e.hex()))
    svt = w.q(par) if par else None
    getter = w.q(svt + 0x60) if svt else None
    st = w.i(par + 0x50) if par else None
    print('par %s vt %s vt+0x60 %s state par+0x50 = %s (6 UpdatePhase, 7..10 EndPhase/Result, 20 PrepareFirst, 21 '
          'PrepareSecond, 26 Intermission)' % (w.rel(par), w.rel(svt), w.rel(getter), st))
    print('local chr %s  [chr+0x20]+0x18 type %s  +0x1D0 pgd %s  player no %s  team pgd+0x104 %s  GDM local pgd %s '
          '(+0xD0 %s +0x104 %s)' % (w.rel(chr_), ctype, w.rel(p), pno, team_p, w.rel(lpgd),
                                    w.i(lpgd + 0xD0) if lpgd else None, w.b(lpgd + 0x104) if lpgd else None))

    # ---- transport ----
    mb, me = (w.q(m3 + 0x1248), w.q(m3 + 0x1250)) if m3 else (None, None)
    srv = w.q(m3 + 0x658) if m3 else None
    s668 = w.q(m3 + 0x668) if m3 else None
    nmem = (me - mb) // 0xF8 if mb and me and me >= mb else 0
    selfish = []
    for k in range(min(nmem, 16)):
        e = mb + k * 0xF8
        info = 'member %d %s +0x10 %s +0xD0 %s +0xD1 %s +0xE0(server) %s +0xE3(self) %s +0xE4(pending) %s%s' % (
            k, w.rel(e), hx(w.q(e + 0x10)), w.b(e + 0xD0), w.b(e + 0xD1), w.b(e + 0xE0), w.b(e + 0xE3), w.b(e + 0xE4),
            '  = mgr3+0x658 (server link)' if e == srv else '')
        print('   ' + info)
        if w.b(e + 0xE3) or e == srv:
            selfish.append(k)
    print('transport: members %d (stride 0xF8), mgr3+0x658 %s, mgr3+0x668 %s' % (nmem, w.rel(srv), w.rel(s668)))

    # ---- the press: 0x1086860 ----
    print('-- press path 0x1086860 (per frame) --')
    out(bool(wcm and chr_), '0x1086898', 'WCM and local chr [WCM+0x1A8]', w.rel(chr_))
    out(bool(pillars), '0x10868CC', 'pillar list gl+0x500 not empty', '%d' % len(pillars))
    out(pno is not None and pno != -1, '0x10868C0', 'player no [[chr+0x20]+0x1D0 or default]+0xD0 != -1',
        '%s (-1: 0x108CC3C skips the store, request still sent)' % pno)
    out(None, '0x1086924', '0x108BB40 can sign (site open, pillar listed)', 'see pillar lines (prompt shown = passed)')
    out(None, '0x1086A74', '0x108D540 range', 'prompt shown = passed')
    ab_a, ab_m = w.g(BTN_A_G), w.g(BTN_M_G)
    out(bool(ab_a and ab_m), '0x1086AD8', 'action-button objects', '%s / %s' % (w.rel(ab_a), w.rel(ab_m)))
    rows = dict(prows(w, P_ACTIONBUTTON))
    for rid in PLEDGE_IDS:
        r = rows.get(rid)
        if not r:
            print('   ActionButtonParam %d: not in the param' % rid)
            continue
        print('   ActionButtonParam %d %s: +2 input kind %s (0 press, 2 HOLD gauge, 1/3 other) +0x2C %s +0x30 %s '
              'invalid flag +0x34 %s grayout flag +0x38 %s +0x40 %s +0x44 %s +0x46 mode %s +0x47 %s' % (
                  rid, w.rel(r), w.b(r + 2), w.b(r + 0x2C), w.i(r + 0x30), w.i(r + 0x34), w.i(r + 0x38), w.f(r + 0x40),
                  w.b(r + 0x44), w.b(r + 0x46), w.b(r + 0x47)))
    if ab_m:
        print('   manager %s +0x21 %s +0x3A %s' % (w.rel(ab_m), w.b(ab_m + 0x21), w.b(ab_m + 0x3A)))
        shown = slist(w, ab_m + 0x18)
        for lname, head in (('+0x08', ab_m + 8), ('+0x18 shown', ab_m + 0x18)):
            for e in slist(w, head):
                bid = w.i(e + 0xC)
                if w.i(e + 8) != 0x10 and bid not in PLEDGE_IDS:
                    continue
                print('   entry %s list %s type %s button %s handle 0x%08X mode +0x24 %s flags +0x25 %s +0x40 %s '
                      '+0x50 %s hold +0x60 %s' % (w.rel(e), lname, w.i(e + 8), bid, w.d(e + 0x10) or 0, w.b(e + 0x24),
                                                  flags25(w.b(e + 0x25)), w.f(e + 0x40), w.f(e + 0x50), w.f(e + 0x60)))
        pe_ = [e for e in shown if w.i(e + 8) == 0x10]
        g0 = [e for e in pe_ if (w.b(e + 0x25) or 0) & 1]
        out(bool(pe_) if pe_ else None, '0x1B5B394', 'pillar entry in the shown list (mgr+0x18)', '%d' % len(pe_))
        out(not g0 if pe_ else None, '0x1B5B3C0', 'entry not grayed out (+0x25 bit 0 clear)',
            'grayout flag in the row is an event flag; bit 0 set = press ignored')
    out(None, '0x1086AEC', '0x1B5F6FC returned 1 (decided press)',
        'transient: bp 0x1086AF0; or watch +0x25 bit 6 / +0x60 above while holding')

    # ---- request ----
    print('-- request 0x108C194 -> receiver 0x1094940 --')
    out(nmem >= 1, '0x108C208', 'members >= 1 -> send with vt+0x40 (else loopback)', '%d' % nmem)
    out(bool(selfish) if nmem else None, '0x1CD7E8C', 'a member is the own self link (vt+0x40 reaches the sender)',
        'members %s [I: +0xE3 self / == mgr3+0x658]' % selfish)
    out(off != 0 or role == 0, '0x563EA20', 'PLEDGE_DECIDE: offline or host decides', 'off %s role %s' % (off, role))

    # ---- decision 0x108C520 (runs on the deciding game, for the presser's player no) ----
    print('-- decision 0x108C520 (values of THIS game for its own press) --')
    out(getter == w.base + STATE_GETTER if getter else None, '0x108C66C', 'par vt+0x60 is the par+0x50 getter',
        w.rel(getter))
    out(st is not None and not 7 <= st <= 0x1C, '0x108C680/69C', 'phase state not 7..0x1C', '%s' % st)
    out(bool(chr_), '0x108C76C', 'chr with player no found (0x17F1940, 0x407) [I: local chr]', w.rel(chr_))
    out(ctype in (0, 10, 30), '0x108C794', 'chr type [[chr+0x20]+0x18] in {0, 10, 30}', '%s' % ctype)
    out(bool(p), '0x108C79C', '[chr+0x20]+0x1D0 non-null', w.rel(p))
    out(team_p is not None and team_p <= 0xB, '0x108C7A8', 'team [[chr+0x20]+0x1D0]+0x104 <= 0xB', '%s' % team_p)
    out(True, '0x108C7B4', 'request rec+9 == 0 -> pillar search path', 'built as 0x00FF at 0x108C1B8 [V]')
    out(bool(pillars), '0x108C878', 'pillar id in gl+0x500 (any shown pillar)', '%d' % len(pillars))
    # ---- apply 0x108CB00 ----
    print('-- apply 0x108CB00 --')
    out(pno is not None and pno != -1, '0x108CC40', 'player no != -1', '%s' % pno)
    out(bool(lpgd) and w.i(lpgd + 0xD0) == pno, '0x108CC7C', 'pgd with +0xD0 == player no (0xCEA240) [I: GDM+0x20]',
        'GDM+0x20 +0xD0 %s' % (w.i(lpgd + 0xD0) if lpgd else None))
    sides = sorted(set(s for _, _, s, _, _, _ in pillars))
    out(all(s <= 1 for s in sides) if sides else None, '0x108CDF8', 'pillar side byte +4 is 0 or 1', '%s' % sides)
    tp = w.b(lpgd + 0x104) if lpgd else None
    out(tp is not None and tp <= 0xB, '0x108CE04', 'team pgd+0x104 <= 0xB -> store gl+0x520+team', '%s' % tp)
    if pled and tp is not None and tp <= 0xB:
        out('i', '0x108CE0C', 'current gl+0x520+team', '%02x' % pled[tp])
    print('first failing check on %s: %s' % (who, '%s %s' % first_fail[0] if first_fail[0] else 'none (see ?? lines)'))


def main():
    for who in (sys.argv[1] if len(sys.argv) > 1 else 'AB'):
        try:
            check(who)
        except Exception as e:  # a game not running must not stop the other
            print('%s: %s' % (who, e))


if __name__ == '__main__':
    main()
