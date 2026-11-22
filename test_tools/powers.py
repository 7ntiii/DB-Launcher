"""Powers of Blood: blood roses, Trespasser Power drops, pending offers, owned Powers. READ ONLY (never writes).
python diag/twin/powers.py [GAMES=AB] [noroses] [watch SECONDS]
  noroses  skip the action-menu asset scan (slow: every world geom is visited)
  watch S  repeat every 2 s for S seconds, print a game's block only when it changed

Facts (diag/net/powers_notes.md) [V = read in code / data, I = inferred]:
  words      POWERS_TRESPASSER hooks 0x10211F0 / 0x15B12C8 / 0x1020FF8 (powers_live.py), caves TLOT 0xC500C70,
             CREATE 0xC500CD0, KSKIP 0xC500D60, FLAG byte main+0xC50F204 (1 only during the local Power lot call);
             built-in LOWN hook 0x1020F3C (COOP2_REWARD_OWN) [V]
  Trespasser manager *(main+0x5B3CD90) +8 vector of instances; ins +0x50 step, +0xC0 id, +0x320 results {player,
             tier, participant}, +0x3A8 = handle of the own Power drop (set in End 0x1020FCC, -0x20 = none),
             +0x3AC second handle (0x1028B44 -> 0x15B1540: MOVES the drop to the owner's feet, it does not
             take it; clears item +0x58 bit 21; powers2_notes 2), +0x3B8 timer [V]
  drops      MapItemMan *(main+0x5B3CDC0) +0x1B8 list of per-player world items (next +8, +0x30 id, +0x290 owner
             slot mask = one bit) [V 0x15B1540]; +0x40 position [I: same as the +0x18 lists]
  item mgr   *(*(main+0x59DFED8)) (End's x0 for 0x15B0B40) +0x378..+0x380 u32 handle vector checked by the
             per-frame step 0x101DA0C [V], meaning [I]
  lot gate   0x15B0B40 returns -0x20 when the table main+0x5A5AB30 (0x18-byte rows {u32 key, .., u8 +6}) row
             for pgd+0x154 has byte +6 == 0 [V 0x15B0C30..0x15B0D04], key meaning [I]
  roses      action-menu assets 99260..99271 (kind 2, 'Gain Power of Blood'): no processor in this build [V ctor
             0x11A17AC] -> never usable; flames.py state fields (mask / all / hold / en)
  offers     skill-enhancement (blood crystal) offers: item mgr *(main+0x5B57E90) +0x21D8 + slot*0x20 (two u64,
             count +0x18) [V 0xCFF4A0]; local only [V 0x15B05B0]
  owned      pgd = *(*(main+0x5B57EB8)+0x20): +0x28F0, +0xED0, +0x1C6C (16 u32) equip-skill / Power fields [I layout]
  pick       powers3_notes.md: dialog OK 0x15B7EC4, hooks PICK 0x15B7F18 / GIVE 0x15B5560 (stock words printed as
             'stock'), MapItemMan +0x330 take-pending list, dialog entry list *(main+0x5B76648) +0x20 [I layout]"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W, fmt3

GDM, WCM_G, MAPITEM, ITEM_MGR, JS_MGR, MGR3, GAMEDATA, ROLE = (0x5B57EB8, 0x5B3CD88, 0x5B3CDC0, 0x5B57E90,
                                                               0x5B3CD90, 0x5B3CE08, 0x5B65C20, 0x492AFD8)
GOT_IM = 0x59DFED8
LOT_TAB = 0x5A5AB30
FLAG = 0xC50F204
STEPS = ['Init', 'WaitActivate', 'Activate', 'IsBattle', 'Cancel', 'End', 'WaitPerfectlyDead', 'WaitTextEffect',
         'WaitFinishReturnWarp', 'Finish']
ROSES = {99260, 99261, 99262, 99263, 99264, 99265, 99266, 99267, 99270, 99271}
# (address, value when ON, name); hook words are `bl` to the trampolines in powers_live.py
WORDS = [(0x10211F0, '43771895', 'TLOT hook'), (0x15B12C8, '10370295', 'CREATE hook'),
         (0x1020FF8, 'C7771895', 'KSKIP hook'), (0xC500C70, '30B3FCB0', 'cave TLOT'),
         (0xC500CD0, '700000F0', 'cave CREATE'), (0xC500D60, '30B3FCB0', 'cave KSKIP'),
         (0x1020F3C, 'B4771815', 'LOWN (built in)'),
         # review 9: RETRY hook (auto-take waits for the own drop), caves CTAG (id tag) / KS2 (send -0x20) / RETRY
         (0x101DA58, None, 'RETRY hook'), (0xC500D80, None, 'cave CTAG'), (0xC500DB0, None, 'cave KS2'),
         (0xC500DD0, None, 'cave RETRY'), (0xC5014B0, None, 'cave RFREE')]
RT = 0xC50F25C          # RETRY table: 4 x {u32 id, u32 calls left}


def live_words():
    """Read the ON values from diag/net/powers_live.py (so the checker follows a re-generation)."""
    try:
        sys.path.insert(0, 'diag/net')
        import powers_live as P
        recs = {a: n for grp in (P.POWERS_CAVES, P.POWERS_TRESPASSER) for a, o, n, c in grp}
        return [(a, recs.get(a, v), name) for a, v, name in WORDS]
    except Exception:
        return WORDS


def vec(w, a, stride, cap=64):
    lo, hi = w.q(a), w.q(a + 8)
    if not lo or not hi or hi < lo or (hi - lo) // stride > cap:
        return []
    return [lo + k * stride for k in range((hi - lo) // stride)]


def local_pgd(w):
    gdm = w.g(GDM)
    return w.q(gdm + 0x20) if gdm else None


def local_no_slot(w):
    chr_, _, _ = w.me()
    d = w.q(chr_ + 0x20) if chr_ else None
    p = w.q(d + 0x1D0) if d else None
    if not p:
        p = w.base + 0x5B583B0
    return w.i(p + 0xD0), w.b(p + 0x104)


def handle_txt(h):
    if h is None:
        return '?'
    if h >= 0xFFFFFFE0 or (h & 0xF) == 0:
        return 'none(%d)' % (h - (1 << 32) if h >= 0x80000000 else h)
    t = (h >> 27) & 0xF                                   # review 9 tag: creator's player number
    return '%08x%s' % (h, '(p%d)' % t if t else '')


def roses(w, slot):
    out = []
    for blockid, k, ins in w.all_geoms(limit=200000):
        info = w.q(ins + 0x10)
        aid = w.i(info + 0x18) if info else None
        if aid is None or aid % 10000000 not in ROSES:
            continue
        row = w.q(info + 0x20)
        kind = w.b(info + 0x304) or (w.b(row + 0x128) if row else None)
        mask = (w.q(info + 0x468) or 0) & 0xFFF
        out.append('    rose %d k%s h=%08x pos %s en=%d mask=%03x all=%s hold=%s%s | usable: NO (kind %s has no '
                   'action-menu processor in this build)' % (
                       aid % 10000000, kind, w.d(ins + 8) or 0, fmt3(w.geom_pos(ins)), (w.b(ins + 0x126) or 0) & 3,
                       mask, w.b(info + 0x470), w.i(info + 0x460),
                       ' USED-BY-ME' if slot is not None and slot < 12 and mask >> slot & 1 else '', kind))
    return out


def block(who, do_roses):
    w = W(who)
    L = []
    gd, m3 = w.g(GAMEDATA), w.g(MGR3)
    no, slot = local_no_slot(w)
    pgd = local_pgd(w)
    L.append('%s: mode %s offline %s role %s (0 host) | local player %s slot %s | FLAG %s' % (
        who, w.d(m3 + 0x1268) if m3 else None, w.b(gd + 0xBDA) if gd else None, w.b(w.base + ROLE), no, slot,
        w.b(w.base + FLAG)))
    ws = []
    for a, new, name in live_words():
        cur = (w.rd(w.base + a, 4) or b'').hex().upper()
        ws.append('%s %s' % (name, ('ON' if cur == new else 'off') if new else ('ON' if cur and cur != '00000000'
                                                                              else 'off (region / group)')))
    L.append('  words: ' + ', '.join(ws))
    rt = w.rd(w.base + RT, 32)
    if rt:
        ents = [struct.unpack_from('<II', rt, 8 * k) for k in range(4)]
        L.append('  RETRY table: %s' % (' '.join('%s/%d' % (handle_txt(i), n) for i, n in ents if n) or 'empty'))
    # lot gate (0x15B0B40 table by pgd+0x154)
    key = w.i(pgd + 0x154) if pgd else None
    gate = '?'
    for k in range(16):
        r = w.rd(w.base + LOT_TAB + 0x18 * k, 0x18)
        if not r:
            break
        if struct.unpack_from('<i', r, 0)[0] == (key if key is not None and 0 <= key + 1 < 0x65 else -1):
            gate = 'row %d byte+6 %d (%s)' % (k, r[6], 'lot allowed' if r[6] else 'LOT REFUSED (-0x20)')
            break
    L.append('  lot gate: pgd+0x154 = %s -> %s' % (key, gate))
    # Trespasser instances
    M = w.g(JS_MGR)
    for sl in (vec(w, M + 8, 8, 64) if M else []):
        ins = w.q(sl)
        if not ins:
            continue
        st = w.d(ins + 0x50)
        res = []
        for e in vec(w, ins + 0x320, 0x10, 16):
            p = w.q(e)
            if p and p > 0x10000:
                res.append('p%s t%s f%s%s' % (w.d(p), w.b(p + 4), w.b(p + 5), ' (ME)' if w.d(p) == no else ''))
        L.append('  trespasser id 0x%08x step %s(%s) results %s | own Power drop +3A8 %s +3AC %s +3B8 %s' % (
            w.d(ins + 0xC0) or 0, st, STEPS[st] if st is not None and st < 10 else '?', res or '-',
            handle_txt(w.d(ins + 0x3A8)), handle_txt(w.d(ins + 0x3AC)), w.f(ins + 0x3B8)))
    # item mgr handle vector
    gv = w.q(w.base + GOT_IM)
    im = w.q(gv) if gv else None
    hv = [w.d(e) for e in vec(w, im + 0x378, 4, 64)] if im else []
    L.append('  item mgr %s +0x378 handles %s' % (w.rel(im), ' '.join('%08x' % (h or 0) for h in hv) or '-'))
    # per-player world items (Power drops / great-foe roses)
    mi = w.g(MAPITEM)
    node, n = (w.q(mi + 0x1B8) if mi else None), 0
    _, _, here = w.me()
    while node and n < 64:
        iid, mask = w.d(node + 0x30), w.q(node + 0x290) or 0
        slots = [b for b in range(12) if mask >> b & 1]
        pos = w.f3(node + 0x40)
        # powers2_notes 2: the step 0x101DE98 -> 0x1028B44 -> 0x15B1540 does NOT take the drop, it MOVES it to the
        # owner's feet (writes +0x40..+0x48 from the owner chr, needs +0x5A bit 5) on the owner's own game only;
        # +0x59 bit 6 set = the step skips the item. 'near me' = within 2.5 m of the local player (coarse on purpose,
        # so `watch` prints only when it changes).
        near = ''
        if here and pos:
            near = ' near me' if sum((a - b) ** 2 for a, b in zip(pos, here)) < 2.5 ** 2 else ' far from me'
        f58 = w.d(node + 0x58)
        L.append('    per-player item %s owner slot %s%s pos %s%s | +58 %s (59b6 skip %s, 5Ab5 not-yet-moved %s)' % (
            handle_txt(iid), slots or '-', ' MINE' if slot in slots else '', fmt3(pos), near,
            '%08x' % f58 if f58 is not None else '?', (f58 >> 14 & 1) if f58 is not None else '?',  # 0x101DE9C
            (f58 >> 21 & 1) if f58 is not None else '?'))
        node, n = w.q(node + 8), n + 1
    L.append('  per-player world items (MapItemMan +0x1B8): %d' % n)
    if do_roses:
        rl = roses(w, slot)
        L.extend(rl)
        L.append('  action-menu rose assets: %d' % len(rl))
    # pending offers (local only) and owned Powers
    imr = w.g(ITEM_MGR)
    idx = w.b(pgd + 0x104) if pgd else None
    if imr and idx is not None and idx <= 0xB:
        e = imr + 0x21D8 + idx * 0x20
        cnt = w.q(e + 0x18)
        opts = [(w.rd(e + 8 * k, 8) or b'').hex() for k in range(min(cnt or 0, 2))] if (cnt or 0) <= 2 else ['bad']
        L.append('  skill-enhancement offers pending %s: %s' % (cnt, ' '.join(opts) or '-'))
    if pgd:
        sk = w.rd(pgd + 0x1C6C, 0x40)
        sk = struct.unpack('<16I', sk) if sk else ()
        L.append('  owned Powers [I]: +28F0 %08x +ED0 %08x +1C6C %s' % (
            w.d(pgd + 0x28F0) or 0, w.d(pgd + 0xED0) or 0, ' '.join('%x' % v for v in sk if v) or '-'))
        # powers4_notes.md: the stock add of a Power (type 7) is 0x15B57FC -> 0x15A2C40 -> 0xCCF8E0 -> 0xD52650(pgd,
        # id), an editor over pgd+0xED0 (active-block flag byte +0xEE0, block +0xEE4, 0x640 bytes) and the two
        # 0x640 blocks +0x1C6C / +0x22AC, then +0x28F0. List every SkillParam-like id (1000000..2199999, or with
        # type nibble 7) in pgd+0xED0..+0x2900 with its offset: the Powers of Blood tab's data [I which block].
        blob = w.rd(pgd + 0xED0, 0x2900 - 0xED0)
        found = []
        if blob:
            for k in range(0, len(blob) - 3, 4):
                v = struct.unpack_from('<I', blob, k)[0]
                if 1000000 <= (v & 0x0FFFFFFF) < 2200000 and (v >> 28) in (0, 7):
                    found.append('+%X=%x' % (0xED0 + k, v))
        L.append('  Power ids in pgd+ED0..+2900 [I]: block flag +EE0 %s | %s' % (
            w.b(pgd + 0xEE0), ' '.join(found[:24]) or '-'))
    # powers3_notes: the "Select what to receive" dialog (0x15A4DE0) and its OK callback 0x15B7EC4 [V].
    # LAN today: OK -> 0x15B7F18 (offline byte 0) -> 0x15B7F88 0x1E subtype 8 (built-in 0x15B7FA8: to the members)
    # -> each game 0x15979B0 -> 0x15B21A0 -> no entry in MapItemMan +0x330 -> return: nothing is given.
    pw = []
    try:
        sys.path.insert(0, 'diag/net')
        import powers_pick_live as PP
        pick_on = {a: n for grp in (PP.POWERS_PICK_CAVE, PP.POWERS_PICK) for a, o, n, c in grp}
        gf = w.b(w.base + PP.CAVES['GFLAG'])
        tr = (w.rd(w.base + PP.CAVES['TR_PICK'], 4) or b'').hex().upper()
        pw.append('PICK_CAVE trampolines %s, GFLAG %s' % (
            'ON' if tr == pick_on.get(PP.CAVES['TR_PICK']) else 'off', gf))
    except Exception:
        pick_on = {}
    for a, stock, name in ((0x15B7F18, '88030034', 'PICK hook 0x15B7F18'), (0x15B5560, 'E81400B4', 'GIVE hook 0x15B5560'),
                           (0x15B7FA8, '082140F9', 'subtype-8 send (built in: members)')):
        cur = (w.rd(w.base + a, 4) or b'').hex().upper()
        if a == 0x15B7FA8:
            state = 'ON' if cur == stock else 'off (%s)' % (cur or '?')
        else:
            state = 'stock' if cur == stock else ('ON' if cur == pick_on.get(a) else
                                                  ('CHANGED %s' % cur if cur else '?'))
        pw.append('%s %s' % (name, state))
    L.append('  pick words: ' + ', '.join(pw))
    pend = vec(w, mi + 0x330, 0x10, 16) if mi else []
    L.append('  take pending list MapItemMan +0x330: %d%s (0x15B21A0 gives only for a listed {member, handle})' % (
        len(pend), ''.join(' %s' % handle_txt(w.d(e + 8)) for e in pend)))
    ui = w.g(0x5B76648)
    sel = vec(w, ui + 0x20, 0x28, 16) if ui else []
    L.append('  select dialog list *(main+0x5B76648) +0x20: %d entries%s' % (
        len(sel), ''.join(' %08x x%s' % (w.d(e) or 0, w.d(e + 4)) for e in sel)))
    w.report_missing()
    return L


args = sys.argv[1:]
games = args[0] if args and args[0].isalpha() and args[0] not in ('noroses', 'watch') else 'AB'
do_roses = 'noroses' not in args
watch = 0.0
if 'watch' in args:
    k = args.index('watch')
    watch = float(args[k + 1]) if k + 1 < len(args) else 60.0
last = {}
for g in games:
    last[g] = block(g, do_roses)
    print('\n'.join(last[g]))
end = time.time() + watch
while time.time() < end:
    time.sleep(2.0)
    for g in games:
        b = block(g, False)
        if b != last[g]:
            print(time.strftime('%H:%M:%S'))
            print('\n'.join(b))
            last[g] = b
