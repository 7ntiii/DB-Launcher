"""READ-ONLY (diag/net/timer_notes.md 7.1 / 7.4): the real HUD window H of the match timer, found WITHOUT a breakpoint.
python diag/twin/timer_probe2.py AB          (or A, B, ...)   two reads per game, 1.5 s apart, then a diff
Only Mem.read and the debug server's read-only search_memory are used; nothing is written.

H = heap object with vtable main+0x57068B8 (0x5830 B, ctor 0x12DBD00) whose +0x9D0 == D = [main+0x5B76C30]+0x49BB0.
Printed per game:
  inputs  round / step / coord (stage+0x3388) / auth (main+0x492AFD8) / fade ([main+0x5B99BB0]+0x7DB9, 3 hides) /
          hud88 ([main+0x5B76C38]+0x88, 0 hides) -> w21 (0 = the state machine wants the panel SHOWN)
  D       +0x1D4 round, +0x1D8 clock copy, +0x183 skip, +0x9D4 area-changed, +0x9D0 id, +0x8FC/+0x8B4/+0x1E0/+0x1E2
  H       on +0x7CA (0 = layout released, case a), layout [+0x7C0] and its +0x1DC (visible), fo/fi +0x7C8/+0x7C9,
          P = H+0x2630: P+0 (state machine's last action: 1 hid, 0 showed), P+0x10 dirty, P+0x128, P+0x90, P+0x91,
          H+0x2658 element bits (u32), H+0x3028 round / H+0x302C value last printed, H+0x3030 text
VERDICT per game, with the case of timer_notes 7.1:
  (a) on=0 or no layout          -> layout released / never loaded (TIMER_RESYNC cannot help)
  (b) on=1 P+0=0 vis=0 no fade   -> faded out behind the state machine (TIMER_RESYNC fixes it)
  (c) D+0x9D4=1 on both reads    -> the area-changed path runs every frame
  (d) vis=1                      -> window visible: the gap is an element bit (compare H+0x2658 / P+0x90 / P+0x91)
  wait: w21=1 (fade / hud88)     -> the panel is hidden on purpose right now"""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

STAGE, AUTH = 0x5B3CDF8, 0x492AFD8
FE, HUD_DATA = 0x5B76C30, 0x49BB0
FADE_OBJ, FADE_OFF, HUD_OBJ, HUD_OFF = 0x5B99BB0, 0x7DB9, 0x5B76C38, 0x88
H_VT = 0x57068B8


def ok(p):
    return bool(p) and p < (1 << 48) and p % 8 == 0


class R:
    def __init__(self, who):
        self.m = Mem(who)
        self.who = who
        self.base = self.m.base

    def rd(self, a, n):
        if not a:
            return None
        try:
            return self.m.read(a, n)
        except Exception:
            return None

    def num(self, a, fmt):
        b = self.rd(a, struct.calcsize(fmt))
        return struct.unpack('<' + fmt, b)[0] if b else None

    def ptr(self, a):
        v = self.num(a, 'Q')
        return v if ok(v) else 0


def _h_cache(r):
    import os
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '.h_cache_%s' % getattr(r, 'who', getattr(r, 'g', 'x')))


def find_h(r, d):
    # cache first (no heap search at all when the HUD window is still the same one)
    try:
        h = int(open(_h_cache(r)).read().strip(), 16)
        if r.ptr(h) == r.base + H_VT and r.ptr(h + 0x9D0) == d:
            return [h], [h]
    except Exception:
        pass
    hits, match = _find_h_search(r, d)
    if match:
        try:
            open(_h_cache(r), 'w').write('%#x' % match[0])
        except Exception:
            pass
    return hits, match


def _find_h_search(r, d):
    pat = struct.pack('<Q', r.base + H_VT).hex()
    hits, start = [], None
    for _ in range(4000):
        p = {'pattern': pat, 'max_hits': 64, 'budget_ms': 100}
        if start:
            p['start'] = start
        try:
            time.sleep(0.4)  # stall guard: at most ~0.1 s of game-thread search, then let the game run
            res = r.m.call('search_memory', p)
        except Exception as e:
            print('  search_memory failed: %s' % e)
            break
        hits += [int(h, 16) if isinstance(h, str) else int(h['address'], 16) for h in res.get('hits', [])]
        start = res.get('next')
        if not start or (res.get('complete') and not start):
            break
    hits = sorted(set(h for h in hits if h % 8 == 0))
    match = [h for h in hits if r.ptr(h + 0x9D0) == d]
    return hits, match


def snap(r, h, d):
    f = {}
    stage = r.ptr(r.base + STAGE)
    f['round'] = r.num(stage + 0xB8, 'I') if stage else None
    f['step'] = r.num(stage + 0x50, 'I') if stage else None
    f['coord'] = int(bool(r.ptr(stage + 0x3388))) if stage else None
    clk = r.ptr(stage + 0x120) if stage else 0
    f['clock'] = r.num(clk + 8, 'f') if clk else None
    f['auth'] = r.num(r.base + AUTH, 'I')
    fo = r.ptr(r.base + FADE_OBJ)
    f['fade'] = r.num(fo + FADE_OFF, 'B') if fo else None
    ho = r.ptr(r.base + HUD_OBJ)
    f['hud88'] = r.num(ho + HUD_OFF, 'I') if ho else None
    f['w21'] = None if f['fade'] is None or f['hud88'] is None else int(f['fade'] == 3 or f['hud88'] == 0)
    for k, off, fmt in (('D1d4', 0x1D4, 'I'), ('D1d8', 0x1D8, 'f'), ('D183', 0x183, 'B'), ('D9d4', 0x9D4, 'B'),
                        ('D9d0', 0x9D0, 'I'), ('D8fc', 0x8FC, 'B'), ('D8b4', 0x8B4, 'B'), ('D1e0', 0x1E0, 'B'),
                        ('D1e2', 0x1E2, 'B')):
        f[k] = r.num(d + off, fmt)
    if h:
        f['on'] = r.num(h + 0x7CA, 'B')
        lay = r.ptr(h + 0x7C0)
        f['layout'] = '%#x' % lay if lay else 0
        f['vis'] = r.num(lay + 0x1DC, 'B') if lay else None
        f['fo'] = r.num(h + 0x7C8, 'B')
        f['fi'] = r.num(h + 0x7C9, 'B')
        p = h + 0x2630
        for k, off in (('P0', 0), ('P10', 0x10), ('P128', 0x128), ('P90', 0x90), ('P91', 0x91)):
            f[k] = r.num(p + off, 'B')
        v = r.num(h + 0x2658, 'I')
        f['H2658'] = '%#x' % v if v is not None else None
        f['H3028'] = r.num(h + 0x3028, 'I')
        f['H302c'] = r.num(h + 0x302C, 'f')
        t = r.rd(h + 0x3030, 16)
        f['text'] = t.split(b'\0')[0].decode('latin-1', 'replace') if t else None
    return f


def fmt(f):
    out = []
    for k, v in f.items():
        out.append('%s=%s' % (k, ('%.1f' % v) if isinstance(v, float) else v))
    return ' '.join(out)


def verdict(a, b):
    if a.get('on') is None:
        return 'NO H (window object not found)'
    if a['w21'] == 1:
        return 'WAIT: w21=1 (fade %s / hud88 %s) -> panel hidden on purpose now' % (a['fade'], a['hud88'])
    if not a['on'] or not a.get('layout'):
        return '(a) layout released / not loaded (on=%s layout=%s): TIMER_RESYNC cannot help' % (a['on'], a['layout'])
    if a.get('D9d4') == 1 and b.get('D9d4') == 1:
        return '(c) area-changed path every frame (D+0x9D4=1 on both reads, id D+0x9D0=%s)' % a.get('D9d0')
    if a.get('vis') == 0 and a.get('P0') == 0 and not a.get('fo') and not a.get('fi') and \
            b.get('vis') == 0 and b.get('P0') == 0:
        return '(b) faded out behind the state machine (P+0=0, vis=0, no fade): TIMER_RESYNC fits'
    if a.get('vis') == 1:
        return '(d) window visible: compare H2658 / P90 / P91 / P128 with the other game'
    return 'other: vis=%s P0=%s fo=%s fi=%s (compare with the other game)' % (a.get('vis'), a.get('P0'), a.get('fo'),
                                                                            a.get('fi'))


def main():
    args = sys.argv[1:]
    if not args or any(c not in 'ABCD' for c in args[0]):
        print(__doc__)
        return 2
    res = {}
    for who in args[0]:
        r = R(who)
        fe = r.ptr(r.base + FE)
        d = fe + HUD_DATA if fe else 0
        hits, match = find_h(r, d) if d else ([], [])
        h = match[0] if match else 0
        print('%s: D %s | H objects (vt main+%#x): %d %s | with +0x9D0 == D: %s' % (
            who, '%#x' % d if d else '-', H_VT, len(hits), ' '.join('%#x' % x for x in hits[:6]),
            ' '.join('%#x' % x for x in match) or 'none'))
        a = snap(r, h, d)
        time.sleep(1.5)
        b = snap(r, h, d)
        print('%s read1 %s' % (who, fmt(a)))
        print('%s read2 %s' % (who, fmt(b)))
        print('%s VERDICT %s' % (who, verdict(a, b)))
        res[who] = b
    if len(res) >= 2:
        keys = list(next(iter(res.values())).keys())
        for k in keys:
            vals = {w: res[w].get(k) for w in res}
            if len(set(map(str, vals.values()))) > 1:
                print('diff %s: %s' % (k, ' '.join('%s=%s' % (w, ('%.1f' % v) if isinstance(v, float) else v)
                                                    for w, v in vals.items())))
    return 0


if __name__ == '__main__':
    sys.exit(main())
