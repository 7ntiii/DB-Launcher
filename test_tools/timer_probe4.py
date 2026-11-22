"""READ-ONLY (diag/net/timer4_notes.md): the HUD's own phase-clock data object on two games, side by side.
python diag/twin/timer_probe4.py AB        (in the final, A = host without timer, B = guest with it)

H = the timer HUD window (vt main+0x57068B8, +0x9D0 == D; found as timer_probe2 does). Its elements are bound by
name in 0x12E2208 [V]: g_phaseClock = object [H+0x54F0] (0x13A1AE0 builds it: refresh when par+0xC8 differs from
its +0x74; it keeps par+0xB8 at +0x70 and par+0xC8 at +0x74; +0xA = the low byte from 0x12C9160 (0 = the hidden
branch 0x13A1BE8); +8 dirty; +0x14 / +0x18 / +0x78 floats; +0x7C byte; +0x20..+0x30 a float vector).
Also printed: par+0xB8 / +0xC8 and the 0x100 raw bytes of the object, with a per-word diff A vs B.
Two reads 1.5 s apart per game. Nothing is written."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from timer_probe2 import R, find_h, FE, HUD_DATA, STAGE  # noqa: E402

PHASE_CLOCK = 0x54F0


def read(r, h):
    out = {}
    stage = r.ptr(r.base + STAGE)
    out['par.B8'] = r.num(stage + 0xB8, 'I') if stage else None
    out['par.C8'] = r.num(stage + 0xC8, 'I') if stage else None
    # 0x12C9160 (the dial's source) takes the phase object [par+0xD0 + (round-1)*8] (null -> default
    # main+0x5B6CBD8; round 0 -> par+0x118), calls its vt+0x10 / vt+0x18 and tests [obj+0x10]+0x8F bit 1 [V]
    rnd = out['par.B8']
    if stage and rnd:
        po = r.ptr(stage + 0xD0 + (rnd - 1) * 8) if rnd <= 9 else 0
        out['phaseobj'] = '%#x' % po if po else 'null (default main+0x5B6CBD8)'
        row = r.ptr(po + 0x10) if po else 0
        out['phaseobj.vt'] = 'main+%#x' % (r.ptr(po) - r.base) if po and r.ptr(po) else None
        out['row'] = '%#x' % row if row else None
        out['row+8F'] = r.num(row + 0x8F, 'B') if row else None
        out['row+14'] = r.num(row + 0x14, 'i') if row else None
    o = r.ptr(h + PHASE_CLOCK)
    out['obj'] = '%#x' % o if o else None
    raw = r.rd(o, 0x100) if o else None
    out['raw'] = raw
    if raw:
        u8 = lambda k: raw[k]
        f32 = lambda k: struct.unpack_from('<f', raw, k)[0]
        u32 = lambda k: struct.unpack_from('<I', raw, k)[0]
        out.update({'dirty+8': u8(8), '+9': u8(9), 'shown+A': u8(0xA), '+14': round(f32(0x14), 3),
                    '+18': round(f32(0x18), 3), 'round+70': u32(0x70), 'C8+74': u32(0x74),
                    '+78': round(f32(0x78), 4), '+7C': u8(0x7C),
                    'vec+20': (struct.unpack_from('<Q', raw, 0x28)[0] - struct.unpack_from('<Q', raw, 0x20)[0]) // 4})
    return out


def main():
    games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
    res = {}
    for g in games:
        r = R(g)
        fe = r.ptr(r.base + FE)
        d = fe + HUD_DATA if fe else 0
        _, match = find_h(r, d)
        if not match:
            print('%s: H not found (D %#x)' % (g, d))
            continue
        h = match[0]
        reads = []
        for k in range(2):
            x = read(r, h)
            reads.append(x)
            print('%s read%d H %#x %s' % (g, k + 1, h, ' '.join('%s=%s' % (a, b) for a, b in x.items() if a != 'raw')))
            if k == 0:
                time.sleep(1.5)
        res[g] = reads[-1]
    if len(res) == 2:
        a, b = (res[g] for g in games)
        if a.get('raw') and b.get('raw'):
            print('raw words that differ (%s / %s):' % tuple(games))
            for k in range(0, 0x100, 4):
                wa = struct.unpack_from('<I', a['raw'], k)[0]
                wb = struct.unpack_from('<I', b['raw'], k)[0]
                if wa != wb:
                    print('  +0x%02X %08x / %08x' % (k, wa, wb))


if __name__ == '__main__':
    main()
