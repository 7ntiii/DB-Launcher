"""Trespassers (joint struggle) of the twin games, read-only: python diag/twin/trespassers.py [GAMES=AB] [foes]
Manager M = *(main+0x5B3CD90): +8..+0x10 vector of CSJointStruggleIns*, +0x28 u16 round. Instance (0x488 B, vt
0x56ECFE0): +0x50/+0x54 step/next (0 Init 1 WaitActivate 2 Activate 3 IsBattle 4 Cancel 5 End 6 WaitPerfectlyDead
7 WaitTextEffect 8 WaitFinishReturnWarp 9 Finish), +0xC0 id = round | enemy key << 16, +0x108 leader, +0x11C recruit
(kind 7) seen, +0x11D, +0x2B0..+0x2B8 participants (0x80: +0 player no, +0xC, +0xD in battle), +0x2D0..+0x2D8
pending requests (u32), +0x31C defeated, +0x320..+0x328 results (0x10), +0x360 state, +0x361 / +0x362 open flags.
Enemy chr: [chr+0x20]+0x78 low 16 bits == id >> 16 (functor 0x1045980); dead = [[chr+0x18]+0x30]+0x18 bit 0
(0x101FED0). Patch words: shipped mask 0x1023574, H1 0x1023564, H2 0x102006C..78, VIRTUE_OWN 0x102100C, LOT_OWN
0x1020F3C, INVITE 0x101FFE0 and the first word of each cave (trespasser_live.py; 'off' on a cave = region unmapped
or group not applied). +0x11C = 1 after a kind-7 apply (also set by the self-invite of JS_INVITE).
'foes': also list chrs with max HP >= 3000 that are not Trespassers (great-foe candidates, heuristic [I])."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, fmt3

STEPS = ['Init', 'WaitActivate', 'Activate', 'IsBattle', 'Cancel', 'End', 'WaitPerfectlyDead', 'WaitTextEffect',
         'WaitFinishReturnWarp', 'Finish']
M_G, MGR3, GAMEDATA, ROLE = 0x5B3CD90, 0x5B3CE08, 0x5B65C20, 0x492AFD8
WORDS = [(0x1023574, '6B288152', 'mask 0x943 (shipped)'), (0x1023564, 'EA000034', 'H1 cbz'),
         (0x102006C, '48C801D0', 'H2 adrp'), (0x1020070, '1F2003D5', 'H2 nop'), (0x1020074, '08617F39', 'H2 ldrb role'),
         (0x1020078, '480D0035', 'H2 cbnz'),
         # co-op completion (coop2_notes.md): hooks via trampolines into main+0xC500000..
         (0x102100C, '7D771815', 'VIRTUE_OWN'), (0x1020F3C, 'B4771815', 'LOT_OWN'), (0x101FFE0, '8E7B1895', 'INVITE'),
         (0xC500000, 'FD7BBCA9', 'cave INV'), (0xC500140, 'E00100B4', 'cave VOWN'), (0xC500190, '28B3FCB0', 'cave LOWN')]
PARK = '6A000014'


def vec(w, a, stride, cap=64):
    lo, hi = w.q(a), w.q(a + 8)
    if not lo or not hi or hi < lo or (hi - lo) // stride > cap:
        return lo, []
    return lo, [lo + k * stride for k in range((hi - lo) // stride)]


def chr_key(w, c):
    p = w.q(c + 0x20)
    v = w.d(p + 0x78) if p else None
    return None if v is None else v & 0xFFFF


def chr_dead(w, c):
    p = w.q(c + 0x18)
    p = w.q(p + 0x30) if p else None
    v = w.b(p + 0x18) if p else None
    return None if v is None else v & 1


def chr_maxhp(w, c):
    m = w.q(c + 0x2470)
    mod = w.q(m + 0x18) if m else None
    return w.i(mod + 0x294) if mod else None


ENEMY_VT, WCM_G, GL_G, SYNC = 0x572B108, 0x5B3CD88, 0x5B3CDB0, 0x540


def sync_slot(w, c):
    """(set i, entry j, owner i16, flags u16, status word) of chr c in the NetChrSync sets, as dusk_lan.cpp
    EnemyOwners reads them: SM = [WCM+0x540], S = [SM+0x10+8i], chr set [S+8] -> entries [+8] (0x38 each),
    count S+0x10, owner i16 [S+0x18]+2j, status word u32 [S+0x30]+4j, flags u16 [S+0x38]+0xC*j."""
    wcm = w.g(WCM_G)
    sm = w.q(wcm + SYNC) if wcm else None
    n = min(w.d(sm + 8) or 0, 16) if sm else 0
    for i in range(n):
        s = w.q(sm + 0x10 + 8 * i)
        cs = w.q(s + 8) if s else None
        cnt = w.d(s + 0x10) if s else 0
        first = w.q(cs + 8) if cs else None
        if not first or not cnt or cnt > 8192:
            continue
        for j in range(cnt):
            if w.q(first + 0x38 * j) == c:
                ow, st, fl = w.q(s + 0x18), w.q(s + 0x30), w.q(s + 0x38)
                return (i, j, w._u(ow + 2 * j, '<h', 2) if ow else None, w.h(fl + 0xC * j) if fl else None,
                        w.d(st + 4 * j) if st else None)
    return None


def hp_why(w, c, ins):
    """Read-only lines for 'Trespasser HP returns / chr hidden / no AI' (trespasser_hp_notes.md):
    - vt: the assist's EnemyOwners only handles chrs whose vtable is main+0x572B108;
    - owner: NetChrSync owner flag (>= 0 this game drives it), flags, status word (low 19 bits = HP field);
    - ent+0x10 (5 active / 2 far) and ent+0x20 flags: 0x173d99c returns 'no authority' (hits only predicted,
      rolled back to master) unless ent+0x10 == 5 and (flags & 9) == 0;
    - data+0xA0: set to 1 by the struggle hide 0x102828c (only writer in the struggle code); every WCM chr loop
      skips such chrs (0x17de220, 0x17dfd2c, ...); cleared only by the warp/respawn 0x176e3f8 <- 0x17cde90;
    - mod+0x240 b+0x10 and gl+0x750: the per-frame hide condition 0x101d45c..0x101d4b4 (ins+0x362 && mode 6 &&
      gl+0x750 == 0 && [[chr+0x2470]+0x240]+0x10 != 0);
    - HP net property P = [mod+0x1F8+0x168]: P+8 prediction mode, working P+0x10, master P+0x40 (heal notes 3);
      words equal to the HP value are marked '*'; mod+0x4A0 bit1 = no-damage."""
    vt = w.q(c)
    ent = w.q(c + 0x18)
    data = w.q(c + 0x20)
    m = w.q(c + 0x2470)
    mod = w.q(m + 0x18) if m else None
    m240 = w.q(m + 0x240) if m else None
    gl = w.g(GL_G)
    hp = w.chr_hp(c)
    ss = sync_slot(w, c)
    print('      why: vt %s (%s) | sync %s | ent+0x10 %s ent+0x20 0x%x chr+0x60 %s | data+0xA0 %s +0x128 %s | '
          'chr+0x1534 %s +0x1626 %s' % (
              w.rel(vt), 'enemy class, assist owns it by distance' if vt == w.base + ENEMY_VT else
              'NOT the enemy class: the assist never sets its owner',
              ('set %d/%d owner %s flags 0x%x word 0x%x (low19 %d)' % (
                  ss[0], ss[1], ss[2], ss[3] or 0, ss[4] or 0, (ss[4] or 0) & 0x7FFFF)) if ss else 'not in a sync set',
              w.d(ent + 0x10) if ent else None, (w.b(ent + 0x20) or 0) if ent else 0, hex(w.q(c + 0x60) or 0),
              w.b(data + 0xA0) if data else None, w.b(data + 0x128) if data else None,
              w.i(c + 0x1534), w.b(c + 0x1626)))
    print('      hide: ins+0x362 %s ins+0x390 %s ins+0x398 %s | mod240 %s b+0x10 %s b+0x11 %s | gl+0x750 %s' % (
        w.b(ins + 0x362), w.f(ins + 0x390), w.b(ins + 0x398), w.rel(m240),
        w.b(m240 + 0x10) if m240 else None, w.b(m240 + 0x11) if m240 else None,
        w.b(gl + 0x750) if gl else None))
    spawn_own(w, c, m, m240, data, hp)
    if mod:
        P = w.q(mod + 0x1F8 + 0x168)
        flags = w.h(mod + 0x4A0)
        if P:
            def row(a):
                out = []
                for k in range(12):
                    v = w.i(a + 4 * k)
                    out.append(('*%d' if v == hp else '%d') % v if v is not None else '?')
                return ' '.join(out)
            print('      hp prop P %s mode P+8 %s ring P+0xA0 %s | mod+0x4A0 0x%x' % (
                w.rel(P), w.b(P + 8), hex(w.q(P + 0xA0) or 0), flags or 0))
            print('        working P+0x10: %s' % row(P + 0x10))
            print('        master  P+0x40: %s' % row(P + 0x40))
        else:
            print('      hp prop: P null | mod+0x4A0 0x%x' % (flags or 0))


TF_WORDS = {0xE4A12C: {'E0050054': 'stock', '1F2003D5': 'SPECIAL_END', 'F40301AA': 'TIMER_ONLY'},
            0xE4A138: {'F30300AA': 'stock', '40000054': 'TIMER_ONLY'},
            0xE4A458: {'00050054': 'stock', '1F2003D5': 'timer on'},
            0x101D4B4: {'762B0094': 'stock', '1F2003D5': 'NOHIDE'}, 0x1024130: {'57100094': 'stock', '1F2003D5': 'NOHIDE'}}


def owner_by_handle(w, h):
    """0x17EE470's own test [V 0x17EE548..0x17EE5A8]: set = handle bits 12..15, entry = low 12 bits, owner i16."""
    if h is None or (h & 0xFFFF) == 0xFFFF:
        return None
    wcm = w.g(WCM_G)
    sm = w.q(wcm + SYNC) if wcm else None
    si, ei = (h >> 12) & 0xF, h & 0xFFF
    if not sm or si >= (w.d(sm + 8) or 0):
        return None
    s = w.q(sm + 0x10 + 8 * si)
    if not s or ei >= (w.d(s + 0x10) or 0):
        return None
    ow = w.q(s + 0x18)
    return w._u(ow + 2 * ei, '<h', 2) if ow else None


def spawn_own(w, c, m, m240, data, hp):
    """trespasser_flow2_notes.md: the deciding values of 'woke up, then back in spawn-in'.
    spawn: module [chr+0x2470]+0x240 (CSChrSpecialInitStateModule, 0x82): +0x10 in state, +0x11 timer running,
      f32 +0x14 timer, +0x19 = w2 of the last state-1 apply (1 = started on THIS game, 0 = from a peer's 0x82 [V
      0xE4A438]); auto-start gates (0xE4A1FC..0xE4A234: HP >= 1, chr+0x12C5 bit26 clear, data+0xA0 == 0, owned
      here); release gates (0x173F6AC..0x173F6C8: AI module [chr+0x2470]+0x88 +0xC90|+0xC91 and +0xD48, else
      no state 0 ever); owned-here = owner[handle] >= 0 as the game itself tests it (0x17EE470); the words.
    own: the inputs of dusk_lan.cpp EnemyOwners on this game: the chr's sync-entry physics position, every
      player entry (WCM+0x30, 0x38 each, physics +0x28 -> +0x70, HP), the distances, and the rule's verdict
      (nearer than every other player by 3 m -> ours; farther by 3 m -> theirs; else keep). Compare with owner."""
    gm = w.q(m + 0x88) if m else None
    h = w.d(data + 0x78) if data else None
    f12c5 = ((w.d(c + 0x12C5) or 0) | ((w.b(c + 0x12C9) or 0) << 32))
    f1a0 = ((w.h(data + 0x1A0) or 0) | ((w.b(data + 0x1A2) or 0) << 16)) if data else 0
    words = []
    for a, names in TF_WORDS.items():
        cur = (w.rd(w.base + a, 4) or b'').hex().upper()
        words.append('%X %s' % (a, names.get(cur, cur or '?')))
    m3 = w.g(MGR3)
    print('      spawn: b+0x10 %s b+0x11 %s timer %s b+0x18 %s b+0x19 %s (1 started here, 0 from a peer) | auto: hp %s '
          'b26 %s data+0xA0 %s | release: AI +0xC90 %s +0xC91 %s +0xD48 %s | owned-here %s (handle 0x%x, b21 %s) '
          'mode %s | words %s' % (
              w.b(m240 + 0x10) if m240 else None, w.b(m240 + 0x11) if m240 else None,
              ('%.2f' % w.f(m240 + 0x14)) if m240 and w.f(m240 + 0x14) is not None else None,
              w.b(m240 + 0x18) if m240 else None, w.b(m240 + 0x19) if m240 else None,
              hp, (f12c5 >> 26) & 1, w.b(data + 0xA0) if data else None,
              w.b(gm + 0xC90) if gm else None, w.b(gm + 0xC91) if gm else None, w.b(gm + 0xD48) if gm else None,
              owner_by_handle(w, h), h or 0, (f1a0 >> 21) & 1, w.d(m3 + 0x1268) if m3 else None, ', '.join(words)))
    # assist view: the physics pointer it uses is the sync chr-set entry +0x28 (entries[j*7+5])
    ss = sync_slot(w, c)
    epos = None
    if ss:
        wcm = w.g(WCM_G)
        s = w.q(w.q(wcm + SYNC) + 0x10 + 8 * ss[0])
        first = w.q(w.q(s + 8) + 8)
        ph = w.q(first + 0x38 * ss[1] + 0x28) if first else None
        epos = w.f3(ph + 0x70) if ph else None
    wcm = w.g(WCM_G)
    arr = w.q(wcm + 0x30) if wcm else None
    pl = []
    for k in range(16):
        e = w.rd(arr + 0x38 * k, 0x38) if arr else None
        if not e:
            break
        e = struct.unpack('<7Q', e)
        if not e[0] or not e[5]:
            continue
        p = w.f3(e[5] + 0x70)
        php = w.chr_hp(e[0])
        if p and epos:
            dist = sum((p[i] - epos[i]) ** 2 for i in range(3)) ** 0.5
            pl.append((k, dist, php))
    verdict = '?'
    if pl and pl[0][0] == 0:
        ours = pl[0][1]
        alive = (pl[0][2] or 0) > 0
        others = [x for x in pl[1:] if (x[2] or 0) > 0]
        theirs = min([x[1] for x in others], default=1e9)
        if not alive and others:
            verdict = 'theirs (our player dead)'
        elif not others:
            verdict = 'ours (no other live player)'
        elif ours < theirs - 3:
            verdict = 'ours'
        elif ours > theirs + 3:
            verdict = 'theirs'
        else:
            verdict = 'keep as is (within 3 m)'
    print('      own: enemy pos %s | players %s | rule says %s | sync owner %s' % (
        fmt3(epos) if epos else None,
        ' '.join('e%d %.1fm hp %s' % x for x in pl) or '-', verdict, ss[2] if ss else '-'))


def one(who, foes):
    w = W(who)
    gd, m3 = w.g(GAMEDATA), w.g(MGR3)
    mode = w.d(m3 + 0x1268) if m3 else None
    _, mem = vec(w, m3 + 0x1248, 0xF8, 16) if m3 else (0, [])
    ids = [w.q(e + 0x10) for e in mem]
    print('%s: mode %s offline %s role %s (0 host) | mgr3 +0x668 %s +0x678 %s | members %s' % (
        who, mode, w.b(gd + 0xBDA) if gd else None, w.b(w.base + ROLE),
        hex(w.q(m3 + 0x668) or 0) if m3 else None, hex(w.q(m3 + 0x678) or 0) if m3 else None,
        [hex(x or 0) for x in ids]))
    pw = []
    for a, new, name in WORDS:
        cur = (w.rd(w.base + a, 4) or b'').hex().upper()
        pw.append('%s %s' % (name, 'ON' if cur == new else ('PARK' if cur == PARK else 'off')))
    print('  patch words: ' + ', '.join(pw))

    chrs = w.all_chrs()
    bykey = {}
    for s, j, c in chrs:
        k = chr_key(w, c)
        if k is not None:
            bykey.setdefault(k, []).append(c)
    M = w.g(M_G)
    if not M:
        print('  no struggle manager (before PrepareThird / not in a match)')
        w.report_missing()
        return
    _, slots = vec(w, M + 8, 8, 64)
    print('  manager %s round %s byte+0x2C %s instances %d' % (w.rel(M), w.h(M + 0x28), w.b(M + 0x2C), len(slots)))
    tres = set()
    for sl in slots:
        ins = w.q(sl)
        if not ins:
            continue
        iid = w.d(ins + 0xC0) or 0
        st, nx = w.d(ins + 0x50), w.d(ins + 0x54)
        parts = []
        for e in vec(w, ins + 0x2B0, 0x80, 16)[1]:
            parts.append('p%s(c%s b%s)' % (w.d(e), w.b(e + 0xC), w.b(e + 0xD)))
        reqs = [w.d(e) for e in vec(w, ins + 0x2D0, 4, 16)[1]]
        res = []
        for e in vec(w, ins + 0x320, 0x10, 16)[1]:
            p = w.q(e)
            if p and p > 0x10000:
                res.append('p%s t%s f%s' % (w.d(p), w.b(p + 4), w.b(p + 5)))
            else:
                res.append((w.rd(e, 0x10) or b'').hex())
        print('  ins %s id 0x%08x step %s(%s) next %s | state %s open %s/%s defeated %s recruit %s/%s leader %s' % (
            w.rel(ins), iid, st, STEPS[st] if st is not None and st < 10 else '?', nx,
            w.b(ins + 0x360), w.b(ins + 0x361), w.b(ins + 0x362), w.b(ins + 0x31C),
            w.b(ins + 0x11C), w.b(ins + 0x11D), w.i(ins + 0x108)))
        print('      participants %s | requests %s | results %s' % (parts or '-', reqs or '-', res or '-'))
        key = iid >> 16
        for c in bykey.get(key, []):
            tres.add(c)
            pos = w.chr_pos(c)
            print('      enemy chr %s key 0x%x pos %s hp %s/%s dead %s marker yes (in manager list)' % (
                w.rel(c), key, fmt3(pos) if pos else None, w.chr_hp(c), chr_maxhp(w, c), chr_dead(w, c)))
            if pos:
                print('      goto: python diag/twin/goto.py %s %.2f %.2f %.2f' % (who, pos[0], pos[1] + 0.5, pos[2]))
            hp_why(w, c, ins)
        if not bykey.get(key):
            print('      enemy chr key 0x%x: not loaded on this game' % key)
    # player chrs: player number + per-chr struggle entry list [chr+0x2470]+0x2B0 -> +0x20..+0x28 (0x18)
    for e in w.players():
        c = e[0]
        m = w.q(c + 0x2470)
        mod = w.q(m + 0x2B0) if m else None
        ents = []
        if mod:
            for x in vec(w, mod + 0x20, 0x18, 16)[1]:
                ents.append('%s/%s' % (w.h(x + 8), w.h(x + 0xA)))
        # kind-7 / self-invite apply 0x102598C [V]: returns before the recruit entry when the entry list is not
        # empty; the invite record (+0x1C8 = 1/2, +0x1CC = enemy key) sits on an object reached through a virtual
        # call ([[chr+0x2470]+0x98]+8 vt+0x228 -> +0x160 -> +0xAE10), so it is not read here. Its gates that
        # are readable: chr+0x1C54 bit0 and data+0x1A0 bit21 (0x1025C5C..0x1025C74), else 0x17EE470(chr).
        sync = sync_slot(w, c)
        data = w.q(c + 0x20)
        f1a0 = ((w.h(data + 0x1A0) or 0) | ((w.b(data + 0x1A2) or 0) << 16)) if data else 0
        print('  player chr %s pos %s entries %s | chr+0x1C54 b0 %s data+0x1A0 b21 %s | sync owner %s' % (
            w.rel(c), fmt3(w.chr_pos(c)) if w.chr_pos(c) else None, ents or '-',
            (w.b(c + 0x1C54) or 0) & 1, (f1a0 >> 21) & 1, sync[2] if sync else '-'))
    if foes:
        for s, j, c in chrs:
            mx = chr_maxhp(w, c)
            if c not in tres and mx and mx >= 3000:
                pos = w.chr_pos(c)
                print('  foe? %s set %d/%d key %s pos %s hp %s/%s dead %s' % (
                    w.rel(c), s, j, chr_key(w, c), fmt3(pos) if pos else None, w.chr_hp(c), mx, chr_dead(w, c)))
    w.report_missing()


games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
for g in games:
    one(g, 'foes' in sys.argv[2:])
