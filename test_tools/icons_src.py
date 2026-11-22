"""READ-ONLY: compare the host-only area-trend sources on two games (diag/net/icons3_notes.md). Writes nothing.

  python diag/twin/icons_src.py AB          (A = host, B = guest; same round, Phase II or III)

Sources compared [V code]:
  1. MS+0x448 group table (MS = [[main+0x5B3CDF8]+0x2D8]): ids and +4/+6 (what v423 copies; logs say equal).
  2. P = [par+0x3378]: the lottery 0x1120B80 hands it the u16 list of the picked trend groups' items
     (0x11212F0 -> 0xEB7B40 -> 0xEBD6A0), host only; nothing else fills it. Its hash map at P+0x38
     (buckets +0x38, count +0x40, first node +0x48, size +0x50; node: next +0, hash +8, u16 key +0x10, value +0x14..).
     P's class code is 0xEB5060..0xEBD6A0 (PrepareFirst calls 0xEB5060, the bot-data broadcast), so it is more
     likely the bots' "go to trend areas" table than the icon; it is compared because it is host-only.
  3. MS+0x558 arrangement slots: count only (v423b).
  4. Generic: every 8-byte field of MapSystem 0..0x800 (scalars as is, heap (begin, end) pairs by length).
The widget's own source was NOT found statically (icons3_notes.md); this read names whatever differs.
"""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W

PAR = 0x5B3CDF8


def src(w):
    s = {}
    par = w.g(PAR)
    if not par:
        return {'err': 'no par'}
    s['round'] = w.d(par + 0xB8)
    s['phase'] = w.d(par + 0x50)
    s['role'] = w.b(w.base + 0x492AFD8)
    ms = w.q(par + 0x2D8)
    tab = {}
    if ms:
        b, e = w.q(ms + 0x448), w.q(ms + 0x450)
        if b and e and 0 <= e - b <= 0x70 * 256:
            raw = w.big(b, e - b) or b''
            for k in range(len(raw) // 0x70):
                gid, x4, x6 = struct.unpack_from('<Ihh', raw, 0x70 * k)
                tab[gid] = (x4, x6)
        b, e = w.q(ms + 0x558), w.q(ms + 0x560)
        s['slots558'] = (e - b) // 0x158 if b and e and e >= b else None
    s['tab'] = tab
    p = w.q(par + 0x3378)
    s['P'] = p
    keys = {}
    if p:
        s['Pvt'] = w.rel(w.q(p))
        s['P8'] = w.d(p + 8)
        s['Pa8'] = w.b(p + 0xA8)
        s['size'] = w.q(p + 0x50)
        node, guard = w.q(p + 0x48), 0
        while node and guard < 512:
            k = w.h(node + 0x10)
            v = w.rd(node + 0x10, 0x30)
            if k is not None:
                keys[k] = v.hex() if v else None
            else:
                s['bad_nodes'] = s.get('bad_nodes', 0) + 1
            node, guard = w.q(node), guard + 1
    s['keys'] = keys
    # 4. generic: every 8-byte field of MS 0..0x800 and of [par+0x2D8]'s neighbours is either a scalar (compared as
    #    is) or a (begin, end) heap pair (compared by length) - whatever differs host vs guest is printed.
    raw = w.big(ms, 0x800) if ms else None
    fields = {}
    if raw:
        q = [struct.unpack_from('<Q', raw, o)[0] for o in range(0, 0x800, 8)]
        heap = lambda v: 0x10000000 <= v <= 0xFFFFFFFFFF and not (w.base <= v < w.base + 0x7000000)
        k = 0
        while k < len(q):
            v = q[k]
            if heap(v) and k + 1 < len(q) and heap(q[k + 1]) and 0 <= q[k + 1] - v <= 0x100000:
                fields[k * 8] = ('len', q[k + 1] - v)
                k += 2
                continue
            if heap(v) or (w.base <= v < w.base + 0x7000000):
                fields[k * 8] = ('ptr', None)
            else:
                fields[k * 8] = ('val', v)
            k += 1
    s['fields'] = fields
    # the 30 lists MS+0x28 + kind*0x20 (begin, end): kind 0xB is the trend kind (0x1118A00(ms, 0xB, ...))
    s['lists'] = {kd: fields.get(0x28 + kd * 0x20) for kd in range(30)}
    return s


def show(w, s):
    if 'err' in s:
        print('%s: %s' % (w.who, s['err']))
        return
    setn = sum(1 for v in s['tab'].values() if v[0] >= 0 or v[1] >= 0)
    print('%s: role %s round %s phase %s | MS+0x448 %d groups, %d set | MS+0x558 slots %s | P %s vt %s +8 %s '
          '+0xA8 %s map size %s keys %s' % (
              w.who, s['role'], s['round'], s['phase'], len(s['tab']), setn, s.get('slots558'), w.rel(s['P']),
              s.get('Pvt'), s.get('P8'), s.get('Pa8'), s.get('size'), sorted(s['keys'])))
    for k in sorted(s['keys']):
        print('     key %5d (0x%04x): %s' % (k, k, s['keys'][k]))


def main():
    ws = [W(g) for g in (sys.argv[1] if len(sys.argv) > 1 else 'AB')]
    ss = [src(w) for w in ws]
    for w, s in zip(ws, ss):
        try:
            show(w, s)
            if s.get('bad_nodes'):
                print('     (%d map nodes unreadable)' % s['bad_nodes'])
        except Exception as e:  # never let the print stop the comparison below
            print('%s: print failed: %r' % (w.who, e))
    if len(ws) == 2 and 'err' not in ss[0] and 'err' not in ss[1]:
        a, b = ss
        tdiff = sorted(k for k in set(a['tab']) | set(b['tab']) if a['tab'].get(k) != b['tab'].get(k))
        kd_a = sorted(set(a['keys']) - set(b['keys']))
        kd_b = sorted(set(b['keys']) - set(a['keys']))
        vdiff = sorted(k for k in set(a['keys']) & set(b['keys']) if a['keys'][k] != b['keys'][k])
        print('RESULT: MS+0x448 %s; map P+0x38 %s (only on %s: %s; only on %s: %s; value differs: %s); rounds %s/%s' % (
            'EQUAL' if not tdiff else 'DIFFERS on %d ids %s' % (len(tdiff), tdiff[:10]),
            'EQUAL' if not (kd_a or kd_b or vdiff) else 'DIFFERS',
            ws[0].who, kd_a, ws[1].who, kd_b, vdiff, a['round'], b['round']))
        fd = []
        for off in sorted(set(a['fields']) | set(b['fields'])):
            fa, fb = a['fields'].get(off), b['fields'].get(off)
            if fa != fb and not (fa and fb and fa[0] == fb[0] == 'ptr'):
                fd.append('MS+0x%X %s/%s' % (off, fa, fb))
        print('MapSystem fields that differ (%s/%s; lengths in bytes): %d' % (ws[0].who, ws[1].who, len(fd)))
        for line in fd:
            print('     ' + line)
        print('list kind 0xB (trend kind) length %s/%s' % (a['lists'].get(0xB), b['lists'].get(0xB)))
    for w in ws:
        w.report_missing()


if __name__ == '__main__':
    main()
