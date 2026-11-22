"""Find where an isolated-bright-pixel pattern (dots) appears in a frame capture.
Usage: python tools/trace_dots.py CAPTURE_DIR [gpu_addr ...]
Without addresses: every pass/dispatch output with its dots score in the region.
Decodes B10G11R11_FLOAT, R16G16B16A16_FLOAT, R16G16_FLOAT, R16_FLOAT, A8B8G8R8_UNORM 2D images."""
import json
import sys
from compression import zstd
import numpy as np

REGION = (slice(150, 480), slice(250, 850))


def f11(v, mb):
    e = (v >> mb) & 31
    m = v & ((1 << mb) - 1)
    return np.where(e == 0, m / (1 << mb) * 2.0 ** -14, (1 + m / (1 << mb)) * 2.0 ** (e.astype(np.int32) - 15))


def load(path, fmt, w, h):
    b = zstd.decompress(open(path, 'rb').read())
    if fmt == 'B10G11R11_FLOAT':
        x = np.frombuffer(b, np.uint32)[:w * h].reshape(h, w).astype(np.int64)
        return [f11(x & 0x7ff, 6), f11((x >> 11) & 0x7ff, 6), f11((x >> 22) & 0x3ff, 5)]
    comps = {'R16G16B16A16_FLOAT': 4, 'R16G16_FLOAT': 2, 'R16_FLOAT': 1}.get(fmt)
    if comps:
        a = np.frombuffer(b, np.float16)[:w * h * comps].reshape(h, w, comps).astype(np.float32)
        return [a[..., c] for c in range(comps)]
    if fmt == 'A8B8G8R8_UNORM':
        a = np.frombuffer(b, np.uint8)[:w * h * 4].reshape(h, w, 4).astype(np.float32) / 255
        return [a[..., c] for c in range(4)]
    return None


def dots(y):
    nb = np.median(np.stack([np.roll(np.roll(y, a, 0), c, 1) for a in (-1, 0, 1) for c in (-1, 0, 1) if a or c]), 0)
    return float((y > np.abs(nb) * 1.8 + 1e-3).mean())


def main():
    d = sys.argv[1]
    addrs = set(sys.argv[2:])
    for line in open(d + '/manifest.jsonl'):
        x = json.loads(line)
        if x.get('kind') not in ('pass', 'dispatch') or not x.get('raw'):
            continue
        if addrs and x.get('gpu_addr') not in addrs:
            continue
        if (x.get('depth') or 1) != 1 or x.get('width', 0) < 900:
            continue
        chans = load(d + '/' + x['raw'], x['format'], x['width'], x['height'])
        if chans is None:
            continue
        scores = [dots(c[REGION]) for c in chans]
        print(f"{x['name'][:88]:88} shaders={','.join(x.get('shaders') or [])[:40]} dots={max(scores):.3f}")


if __name__ == '__main__':
    main()
