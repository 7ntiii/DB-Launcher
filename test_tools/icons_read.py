"""READ-ONLY (diag/net/icons_notes.md): the MapSystem group-arrangement table that the area icons are thought to come
from (HUD / map binding ArrangementTendencyIcon). Settles whether a guest lacks the host's values.
python diag/twin/icons_read.py WHO          one dump of game WHO (A, B, C, D)
python diag/twin/icons_read.py AB diff      dump A and B, then one line per area id where they differ

MapSystem = [[main+0x5B3CDF8]+0x2D8]; table = vector MS+0x448 (begin) / +0x450 (end), 0x70-byte entries:
u32 id +0, s16 +4, s16 +6 (the simulation body 0x11123A0 resets both to -1 each round and its lottery fills them; the
readers 0x1122D6C / 0x1124F00.. test them), inner vectors at +0x08, +0x28, +0x48 (begin, end). Also printed: round
(stage+0xB8), phase (stage+0x50), the 30 MapSystem list sizes (MS+0x28 + kind*0x20) for reference.
Expected if the notes are right: same ids on both games; host values >= 0 on the trend areas, guest -1 / -1.
The HUD field (+0x1C98 of the HUD model) is not printed: the path from a global to that model was not found.
Nothing is written. Every pointer is checked ('-' = unreadable)."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

STAGE, P_ROUND, P_STATE, MAP_SYSTEM = 0x5B3CDF8, 0xB8, 0x50, 0x2D8
TABLE, STRIDE, MAX_ENTRIES = 0x448, 0x70, 256
LISTS = 0x28


def ok(p):
    return bool(p) and p < (1 << 48) and p % 8 == 0


def rd(m, a, n):
    try:
        return m.read(a, n)
    except Exception:  # noqa: BLE001
        return None


def q(m, a):
    b = rd(m, a, 8)
    v = struct.unpack('<Q', b)[0] if b else 0
    return v


def dump(who):
    m = Mem(who)
    out = {'who': who, 'rows': {}, 'text': []}
    t = out['text']
    stage = q(m, m.base + STAGE)
    if not ok(stage):
        t.append('%s: stage null (not in a match)' % who)
        return out
    hdr = rd(m, stage + P_STATE, 4)
    rnd = rd(m, stage + P_ROUND, 4)
    ms = q(m, stage + MAP_SYSTEM)
    t.append('%s %s: round %s phase %s MapSystem %s' % (
        time.strftime('%H:%M:%S'), who, struct.unpack('<I', rnd)[0] if rnd else '-',
        struct.unpack('<I', hdr)[0] if hdr else '-', '%#x' % ms if ok(ms) else 'null'))
    if not ok(ms):
        return out
    sizes = []
    for k in range(30):
        b = rd(m, ms + LISTS + k * 0x20, 16)
        if not b:
            sizes.append('-')
            continue
        lo, hi = struct.unpack('<QQ', b)
        sizes.append(str((hi - lo) // 16) if ok(lo) and hi >= lo and (hi - lo) % 16 == 0 else ('0' if lo == hi
                                                                                               else '?'))
    t.append('  lists (kind:elements) ' + ' '.join('%d:%s' % (k, s) for k, s in enumerate(sizes) if s != '0'))
    b = rd(m, ms + TABLE, 16)
    if not b:
        t.append('  table MS+0x448 unreadable')
        return out
    lo, hi = struct.unpack('<QQ', b)
    if lo == 0 and hi == 0:
        t.append('  table MS+0x448 empty (begin = end = 0)')
        return out
    if not ok(lo) or hi < lo or (hi - lo) % STRIDE or (hi - lo) // STRIDE > MAX_ENTRIES:
        t.append('  table MS+0x448 not plausible: begin %#x end %#x' % (lo, hi))
        return out
    n = (hi - lo) // STRIDE
    raw = rd(m, lo, n * STRIDE) if n else b''
    if raw is None:
        t.append('  table %#x..%#x (%d entries) unreadable' % (lo, hi, n))
        return out
    set_n = 0
    t.append('  table %#x..%#x: %d entries (id, +4, +6, inner vector sizes, raw +0..+0x10)' % (lo, hi, n))
    for i in range(n):
        e = raw[i * STRIDE:(i + 1) * STRIDE]
        eid, a, c = struct.unpack_from('<Ihh', e, 0)
        vs = []
        for off in (0x08, 0x28, 0x48):
            vb, ve = struct.unpack_from('<QQ', e, off)
            vs.append(str((ve - vb) // 8) if ok(vb) and ve >= vb else ('0' if vb == ve else '?'))
        set_n += a >= 0 or c >= 0
        out['rows'][eid] = (a, c)
        t.append('    id %-8d +4 %4d  +6 %4d  vec %s  raw %s' % (eid, a, c, '/'.join(vs), e[:0x10].hex()))
    t.append('  %d of %d entries have +4 or +6 >= 0' % (set_n, n))
    slots(m, ms, out)
    return out


def slots(m, ms, out):
    """second host-only table: MS+0x558 / +0x560, 0x158-byte slots (u16 +0, s32 +4 = -1 when free; built and filled
    in the simulation body 0x1113D18.., read with MS+0x448 by 0x1122CE0). Compared as 'slot:<index>' rows."""
    t = out['text']
    b = rd(m, ms + 0x558, 16)
    if not b:
        t.append('  slots MS+0x558 unreadable')
        return
    lo, hi = struct.unpack('<QQ', b)
    if lo == hi:
        t.append('  slots MS+0x558 empty')
        return
    if not ok(lo) or hi < lo or (hi - lo) % 0x158 or (hi - lo) // 0x158 > 512:
        t.append('  slots MS+0x558 not plausible: begin %#x end %#x' % (lo, hi))
        return
    n = (hi - lo) // 0x158
    raw = rd(m, lo, n * 0x158)
    if raw is None:
        t.append('  slots %#x (%d) unreadable' % (lo, n))
        return
    used = 0
    for i in range(n):
        e = raw[i * 0x158:(i + 1) * 0x158]
        h0, = struct.unpack_from('<H', e, 0)
        v4, = struct.unpack_from('<i', e, 4)
        used += v4 >= 0
        out['rows']['slot:%d' % i] = (h0, v4)
    t.append('  slots MS+0x558 %#x: %d slots, %d with +4 >= 0 (compared in diff as slot:N = (u16 +0, s32 +4))' % (
        lo, n, used))


def main():
    args = sys.argv[1:]
    if not args or any(g not in 'ABCD' for g in args[0]):
        print(__doc__)
        return 2
    res = [dump(g) for g in args[0]]
    for r in res:
        print('\n'.join(r['text']), flush=True)
    if len(args) > 1 and args[1] == 'diff' and len(res) == 2:
        a, b = res
        ids = sorted(set(a['rows']) | set(b['rows']), key=str)
        diff = [i for i in ids if a['rows'].get(i) != b['rows'].get(i)]
        print('diff %s vs %s: %d of %d ids differ' % (a['who'], b['who'], len(diff), len(ids)))
        for i in diff:
            print('  id %-8s %s %s   %s %s' % (i, a['who'], a['rows'].get(i, 'missing'), b['who'],
                                              b['rows'].get(i, 'missing')))
        d448 = [i for i in diff if not str(i).startswith('slot:')]
        dslot = [i for i in diff if str(i).startswith('slot:')]
        if ids and not diff:
            print('RESULT icons_read: tables EQUAL on both games -> neither table is the cause (notes section 3)')
        else:
            print('RESULT icons_read: MS+0x448 %s (%d ids), MS+0x558 slots %s (%d) -> %s' % (
                'DIFFER' if d448 else 'equal', len(d448), 'DIFFER' if dslot else 'equal', len(dslot),
                'assist_v423 covers MS+0x448 only; slots need a v423 extension' if dslot else
                'assist_v423 is the fix candidate'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
