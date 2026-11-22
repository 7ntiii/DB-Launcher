r"""mapdiff.py: objective "did a new marker appear" check for map screenshots (READ ONLY: reads PNG files only).

Row 54 (map pins / player markers) has no memory field known (regress_small.py pin_place / markers say MANUAL).
This tool replaces the by-eye judgment with a pixel comparison of two shots of the SAME map view.

    python diag/twin/mapdiff.py BEFORE.png AFTER.png [BEFORE2.png AFTER2.png ...] [options]

Per pair it lists the changed blobs (connected areas where the colour changed by more than thr), with their centre
in fractions of the image (0..1, so shots of different games at the same size compare directly), their size in
pixels, and the mean colour after. With two or more pairs it then looks for a blob that appears in EVERY pair at
the same place (within near= of each other): that is the new pin (pin_place) or the moved player marker (markers,
the other player moved, the viewer stood still).

Options (defaults in brackets):
  thr=40       per-pixel change (max of |dR|, |dG|, |dB|) that counts
  scale=2      work on a 1/scale image (speed; 480-line shots stay fine at 2)
  min=4        smallest blob kept, in working pixels
  max=2500     largest blob kept (bigger = the view itself moved or a menu opened: the pair is reported as UNUSABLE)
  near=0.04    distance (fraction of the image width) for "the same place" across pairs
  ignore=x0,y0,x1,y1[;...]   areas to leave out, in fractions (e.g. the clock: ignore=0.85,0,1,0.1)
  expect=1     at least this many common blobs for PASS

Exit / last line:
  MAPDIFF PASS  common blob(s) at ...         every pair shows a new blob at the same place
  MAPDIFF FAIL  ...                           a usable pair shows no blob, or no blob is common to every pair
  MAPDIFF UNUSABLE ...                        a pair changed too much (different view / a menu): take the shots again
"""
import sys

from PIL import Image


def opts(argv):
    o = {'thr': 40, 'scale': 2, 'min': 4, 'max': 2500, 'near': 0.04, 'ignore': '', 'expect': 1}
    files = []
    for a in argv:
        if '=' in a and not a.lower().endswith('.png'):
            k, v = a.split('=', 1)
            o[k] = v if k == 'ignore' else float(v)
        else:
            files.append(a)
    zones = []
    for part in filter(None, str(o['ignore']).split(';')):
        zones.append(tuple(float(x) for x in part.split(',')))
    o['zones'] = zones
    return o, files


def blobs(before, after, o):
    a = Image.open(before).convert('RGB')
    b = Image.open(after).convert('RGB')
    if a.size != b.size:
        raise SystemExit(f'MAPDIFF UNUSABLE {before} {after}: sizes differ {a.size} {b.size}')
    s = max(1, int(o['scale']))
    w, h = a.size[0] // s, a.size[1] // s
    a = a.resize((w, h))
    b = b.resize((w, h))
    pa, pb = a.load(), b.load()
    thr = o['thr']
    mask = bytearray(w * h)
    changed = 0
    for y in range(h):
        fy = y / h
        for x in range(w):
            fx = x / w
            if any(z[0] <= fx <= z[2] and z[1] <= fy <= z[3] for z in o['zones']):
                continue
            c1, c2 = pa[x, y], pb[x, y]
            if max(abs(c1[0] - c2[0]), abs(c1[1] - c2[1]), abs(c1[2] - c2[2])) > thr:
                mask[y * w + x] = 1
                changed += 1
    found, big = [], 0
    seen = bytearray(w * h)
    for start in range(w * h):
        if not mask[start] or seen[start]:
            continue
        stack, pts = [start], []
        seen[start] = 1
        while stack:
            p = stack.pop()
            pts.append(p)
            x, y = p % w, p // w
            for q in ((p - 1) if x > 0 else -1, (p + 1) if x < w - 1 else -1, p - w, p + w):
                if 0 <= q < w * h and mask[q] and not seen[q]:
                    seen[q] = 1
                    stack.append(q)
        n = len(pts)
        if n > o['max']:
            big += 1
            continue
        if n < o['min']:
            continue
        cx = sum(p % w for p in pts) / n / w
        cy = sum(p // w for p in pts) / n / h
        col = [0, 0, 0]
        for p in pts:
            c = pb[p % w, p // w]
            col = [col[i] + c[i] for i in range(3)]
        found.append({'x': cx, 'y': cy, 'n': n, 'rgb': tuple(int(v / n) for v in col)})
    return found, big, changed / (w * h)


def main(argv):
    o, files = opts(argv)
    if len(files) < 2 or len(files) % 2:
        print(__doc__)
        return 2
    pairs = []
    unusable = False
    for i in range(0, len(files), 2):
        found, big, frac = blobs(files[i], files[i + 1], o)
        state = 'UNUSABLE (a blob over max: the view moved or a menu opened)' if big else 'ok'
        unusable |= bool(big)
        print(f'pair {i // 2 + 1}: {files[i]} -> {files[i + 1]}: {len(found)} blob(s), {frac * 100:.2f} % of the '
              f'image changed, {state}')
        for f in sorted(found, key=lambda f: -f['n'])[:12]:
            print(f'    blob at x {f["x"]:.3f} y {f["y"]:.3f}  size {f["n"]}  colour after {f["rgb"]}')
        pairs.append(found)
    if unusable:
        print('MAPDIFF UNUSABLE: take that pair again with the same map view')
        return 3
    if any(not p for p in pairs):
        print('MAPDIFF FAIL  a pair shows no new blob')
        return 1
    common = []
    for f in pairs[0]:
        if all(any(((g['x'] - f['x']) ** 2 + (g['y'] - f['y']) ** 2) ** 0.5 <= o['near'] for g in p)
               for p in pairs[1:]):
            common.append(f)
    if len(common) >= o['expect']:
        print('MAPDIFF PASS  common blob(s) at ' +
              ', '.join(f'({f["x"]:.3f}, {f["y"]:.3f})' for f in common))
        return 0
    print('MAPDIFF FAIL  no blob is at the same place in every pair')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
