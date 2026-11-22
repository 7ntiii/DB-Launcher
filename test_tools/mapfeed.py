"""Prototype of the assist's map sharing (needs MAPSIM_HOST + MAP_INBOX + MAP_APPEND + MAP_WAIT applied on all games):
python diag/twin/mapfeed.py [HOST=A] [GUESTS=B] [MAX_SECONDS=1200]
Watches the host; when its MapSystem lists are filled for a new round it snapshots all 30 kinds and feeds them to
each guest through the inbox at main+0x563EE00 {u32 valid, u32 kind|flags, u32 nbytes, u32 pad, data[<=0x1F0]}:
first the kin-circle swap (current -> previous lists, as the simulation does), then every kind (bit 8 = append for
the following chunks), then kind 0xFF (ready)."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

host = sys.argv[1] if len(sys.argv) > 1 else 'A'
guests = sys.argv[2] if len(sys.argv) > 2 else 'B'
limit = float(sys.argv[3]) if len(sys.argv) > 3 else 1200
INBOX, CHUNK = 0xC50F000, 0x1E0


def ms_of(m):
    par = m.u64(m.base + 0x5B3CDF8)
    if not par:
        return 0, 0, 0, 0
    return par, m.u64(par + 0x2D8), m.u32(par + 0x50), m.u32(par + 0xB8)


def snapshot(m, ms):
    out = []
    for k in range(30):
        b, e = m.u64(ms + 0x28 + k * 0x20), m.u64(ms + 0x30 + k * 0x20)
        out.append(m.read(b, e - b) if e > b else b'')
    return out


def put(m, kind, data, timeout=5.0):
    m.write(m.base + INBOX + 4, struct.pack('<III', kind, len(data), 0) + data)
    m.write(m.base + INBOX, struct.pack('<I', 1))
    t = time.time()
    while time.time() - t < timeout:
        if m.u32(m.base + INBOX) == 0:
            return True
        time.sleep(0.01)
    return False


def feed(w, lists):
    m = Mem(w)
    par, ms, step, rnd = ms_of(m)
    for i in range(3):  # the simulation's start: previous <- current, current empty
        cur, prev = ms + 0x388 + i * 0x20, ms + 0x3E8 + i * 0x20
        c, p = m.read(cur, 0x18), m.read(prev, 0x18)
        pb = struct.unpack_from('<Q', p)[0]
        p = struct.pack('<QQ', pb, pb) + p[16:]
        m.write(cur, p)
        m.write(prev, c)
    n = 0
    for k, data in enumerate(lists):
        chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [b'']
        for j, ch in enumerate(chunks):
            if not put(m, k | (0x100 if j else 0), ch):
                print(w, 'inbox not consumed at kind %X chunk %d' % (k, j), flush=True)
                return False
            n += 1
    ok = put(m, 0xFF, b'')
    print(time.strftime('%H:%M:%S'), w, 'fed', n, 'records, ready', ok, 'guest step', ms_of(m)[2], flush=True)
    return ok


mh = Mem(host)
done = -1
t0 = time.time()
while time.time() - t0 < limit:
    try:
        par, ms, step, rnd = ms_of(mh)
        if ms and rnd != done:
            lists = snapshot(mh, ms)
            if any(lists) and mh.read(ms + 0x20, 1)[0] == 1:
                lists2 = snapshot(mh, ms)
                if lists2 == lists:
                    print(time.strftime('%H:%M:%S'), host, 'round', rnd, 'step', step, 'lists',
                          ' '.join('%X:%d' % (k, len(d)) for k, d in enumerate(lists) if d), flush=True)
                    for w in guests:
                        feed(w, lists)
                    done = rnd
    except Exception as ex:
        print('err', str(ex)[:80], flush=True)
    time.sleep(0.1)
