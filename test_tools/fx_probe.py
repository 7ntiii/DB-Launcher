"""READ-ONLY effect probe for two live faults (diag/net/vanish_death_notes.md). Writes nothing anywhere.

  python diag/twin/fx_probe.py AB [SECONDS=20] [all]

Every 0.1 s, on each game, for each player chr in the player set (WCM+0x30):
  - chr pointer (a change = the copy was made again), player no, HP, stage pgd+0x46B0, stock, rsp chrdata+0x2D0,
    flags chr+0x26E4 (bit16 respawn chosen, bit10 out), position;
  - the active SpEffect ids of the chr: list [[chr+0x20]+0x90], buckets from +8 chained by +0x18, nodes chained
    by +0x88, id node+0x78, row node+0x80, inactive when node+0x20 & 0x800C0003 (mirror of 0xE8C8C0 / 0x118F9C0) [V].
    By default only the skill families 14010xx (Blink), 14070xx (Neb-ra Vanishing), 14440xx (Darkmoon) and ids
    that appear more than once are printed; `all` prints every add / remove;
  - the effect-request manager [[main+0x59E1B28]] slot counts per player (requests +0xB8, records +0x78) [V effwatch]
    and the number of chrs in the world chr sets (WCM+0x18, +0x78 each).
Only changes are printed, with the time. At the end: per game and player the number of chr re-creations, deaths
(HP > 0 -> <= 0), SpEffect adds per id, and the largest node count seen (stacking shows as a growing count).

Use (1) Blink: start it, then cast Blink / Neb-ra Vanishing / Darkmoon on A next to B. Compare A's own row with
B's copy of A. (2) Death effects: start it on A and B just before the host's last-life death in a 3-player final.
"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W

EFFECT_MGR = 0x59E1B28
INACTIVE = 0x800C0003
FAMILIES = ((1401000, 1401099, 'Blink'), (1407000, 1407099, 'Neb-ra'), (1444000, 1444099, 'Darkmoon'))


def family(i):
    for lo, hi, name in FAMILIES:
        if lo <= i <= hi:
            return name
    return None


def effects(w, chr_):
    """list of active SpEffect ids (duplicates kept) or None"""
    data = w.q(chr_ + 0x20)
    mgr = w.q(data + 0x90) if data else None
    if not mgr:
        return None
    out = []
    outer = mgr + 8
    node = w.q(outer)
    for _ in range(64):
        guard = 0
        while node and guard < 256:
            fl = w.d(node + 0x20) or 0
            row = w.q(node + 0x80)
            if row and not fl & INACTIVE:
                out.append(w.i(node + 0x78))
            node = w.q(node + 0x88)
            guard += 1
        outer = w.q(outer + 0x18) if outer else None
        if not outer:
            break
        node = w.q(outer)
    return out


def requests(w):
    p = w.g(EFFECT_MGR)
    mgr = w.q(p) if p else None
    out = {}
    if not mgr:
        return out
    for k in range(13):
        slot = mgr + 8 + 0x290 * k
        no = w.i(slot)
        if no is None or no == -1:
            continue
        out[no] = (w.q(slot + 0xB8), w.q(slot + 0x78))
    return out


KNOWN = {}  # (game, player no) -> last chr seen in the player set


def snap(w):
    s = {}
    chrs = []
    for k in range(8):  # match 2: an emptied entry (FINALOUT on a guest) must not hide the entries after it
        e = w.player_entry(k)
        if e and e[0]:
            chrs.append((e[0], False))
    seen = set()
    for c, _ in chrs:
        data = w.q(c + 0x20)
        pgd = w.q(data + 0x1D0) if data else None
        seen.add(w.i(pgd + 0xD0) if pgd else None)
    # a player whose entry is gone: keep reading its old chr while it still names that player (the copy may live on)
    for (who, no), c in list(KNOWN.items()):
        if who == w.who and no not in seen:
            data = w.q(c + 0x20)
            pgd = w.q(data + 0x1D0) if data else None
            if pgd and w.i(pgd + 0xD0) == no:
                chrs.append((c, True))
    for c, gone in chrs:
        data = w.q(c + 0x20)
        pgd = w.q(data + 0x1D0) if data else None
        no = w.i(pgd + 0xD0) if pgd else None
        if not gone:
            KNOWN[(w.who, no)] = c
        st = w.rd(pgd + 0x46B0, 4) if pgd else None
        pos = w.chr_pos(c)
        s[no] = {
            'chr': c, 'hp': w.chr_hp(c), 'stage': st.hex() if st else None,
            'stock': w.b(pgd + 0x42A4) if pgd else None,
            'rsp': (w.b(data + 0x2D0) or 0) & 1 if data else None,
            'flags': w.d(c + 0x26E4),
            'pos': tuple(round(v, 1) for v in pos) if pos else None,
            'fx': effects(w, c),
            'entry': 'GONE (old chr still read)' if gone else 'in set',
        }
    rq = requests(w)
    # 'chrs in world' (a walk of every world chr set each tick) dropped in match 3: keep the probe cheap
    return s, rq


def main():
    games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    show_all = 'all' in sys.argv[3:]
    ws = [W(g) for g in games]
    last = {w.who: (None, None) for w in ws}
    stats = {}
    t0 = time.time()
    while time.time() - t0 < secs:
        now = time.time() - t0
        for w in ws:
            s, rq = snap(w)
            prev, prq = last[w.who]
            for no, p in s.items():
                key = (w.who, no)
                st = stats.setdefault(key, {'remade': 0, 'deaths': 0, 'adds': {}, 'maxfx': 0})
                q = prev.get(no) if prev else None
                fx = p['fx'] or []
                st['maxfx'] = max(st['maxfx'], len(fx))
                if q is None:
                    print('%6.1f %s p%s: chr %#x hp %s stage %s stock %s rsp %s flags %#x pos %s, %d SpEffects' % (
                        now, w.who, no, p['chr'], p['hp'], p['stage'], p['stock'], p['rsp'], p['flags'] or 0,
                        p['pos'], len(fx)), flush=True)
                    continue
                notes = []
                if q['chr'] != p['chr']:
                    st['remade'] += 1
                    notes.append('CHR MADE AGAIN %#x -> %#x' % (q['chr'], p['chr']))
                if q['hp'] is not None and p['hp'] is not None and q['hp'] > 0 >= p['hp']:
                    st['deaths'] += 1
                    notes.append('DIES (HP %s -> %s)' % (q['hp'], p['hp']))
                for k in ('entry', 'hp', 'stage', 'stock', 'rsp', 'flags'):
                    if q[k] != p[k] and not (k == 'hp' and notes and notes[-1].startswith('DIES')):
                        notes.append('%s %s -> %s' % (k, q[k] if k != 'flags' else '%#x' % (q[k] or 0),
                                                      p[k] if k != 'flags' else '%#x' % (p[k] or 0)))
                old = list(q['fx'] or [])
                added, removed = list(fx), []
                for i in old:
                    if i in added:
                        added.remove(i)
                    else:
                        removed.append(i)
                for i in added:
                    st['adds'][i] = st['adds'].get(i, 0) + 1
                dup = {i for i in fx if fx.count(i) > 1}
                sel = lambda ids: [i for i in ids if show_all or family(i) or i in dup]
                if sel(added):
                    notes.append('+fx %s' % ', '.join('%d%s' % (i, '(%s)' % family(i) if family(i) else '')
                                                      for i in sel(added)))
                if sel(removed):
                    notes.append('-fx %s' % ', '.join(str(i) for i in sel(removed)))
                if dup:
                    notes.append('STACKED %s' % ', '.join('%dx%d' % (i, fx.count(i)) for i in sorted(dup)))
                if notes:
                    print('%6.1f %s p%s: %s (pos %s, %d SpEffects)' % (now, w.who, no, '; '.join(notes), p['pos'],
                                                                       len(fx)), flush=True)
            for no in (prev or {}):
                if no not in s:
                    print('%6.1f %s p%s: GONE (no entry, old chr no longer names it)' % (now, w.who, no), flush=True)
            if prq is not None and rq != prq:
                print('%6.1f %s effect requests (player: requests, records) %s' % (now, w.who, rq), flush=True)
            last[w.who] = (s, rq)
        time.sleep(0.2)  # stall guard (match 3): small reads only, about 5 passes a second
    print('--- summary')
    for (who, no), st in sorted(stats.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        top = sorted(st['adds'].items(), key=lambda kv: -kv[1])[:8]
        print('%s p%s: chr made again %d, deaths %d, most SpEffects at once %d, adds %s' % (
            who, no, st['remade'], st['deaths'], st['maxfx'],
            ', '.join('%d x%d%s' % (i, n, ' (%s)' % family(i) if family(i) else '') for i, n in top) or 'none'))
    for w in ws:
        w.report_missing()


if __name__ == '__main__':
    main()
