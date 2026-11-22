"""Notice-queue lock watch (starcrash3_notes.md). READ-ONLY: only Mem.read, never writes, never sets breakpoints.
python diag/twin/qlock.py [GAMES=AB] [SECONDS=60] [-v]

Per game, polled as fast as the debug server answers (each poll is one read of 0x70 bytes per game):
  Q        = [[main+0x5B3CDF8] + 0x33A0]   the gain-notice queue that 0xF94A14 pushes into
  owner    u64 Q+0x60  CSDebugPanicLock owner (the pushing thread's object, tpidr_el0+0x88 slot); 0 = free
  depth    u32 Q+0x68  recursion depth (same thread may re-enter; a DIFFERENT thread aborts at 0xF94C44)
  abort    u8  Q+0x6C  abort flag
  records  (Q+0x18 - Q+0x10) / 12   queued 12-byte records {player, id, flag}
  REQ/DONE u32 main+SC_CNT, +4      only with STARCRASH_DEFER applied (starcrash2_live.py CAVES['SC_CNT']):
                                    REQ = TextEffect pushes the UI thread handed over, DONE = run by the game thread
Prints at the end: samples, samples with the lock held, every distinct owner value with its count (one value =
only the game thread was ever seen inside; two or more = a second thread was seen holding it = the race window),
max depth, abort ever set, max records, REQ / DONE (REQ - DONE = still pending; it must return to 0).
A poll takes ~1 ms or more and the lock is held for microseconds, so a held sample is luck: no second owner seen
proves nothing; one seen is proof the window opens."""
import os
import re
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

PAR = 0x5B3CDF8


def sc_cnt():
    p = os.path.join('diag', 'net', 'starcrash2_live.py')
    if os.path.exists(p):
        m = re.search(r"'SC_CNT':\s*0x([0-9A-Fa-f]+)", open(p, encoding='utf-8').read())
        if m:
            return int(m.group(1), 16)
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    games = args[0] if args else 'AB'
    secs = float(args[1]) if len(args) > 1 else 60.0
    verbose = '-v' in sys.argv
    cnt = sc_cnt()
    st = {}
    for w in games:
        m = Mem(w)
        par = m.u64(m.base + PAR)
        q = m.u64(par + 0x33A0) if par else 0
        st[w] = dict(m=m, q=q, n=0, held=0, owners={}, depth=0, abort=0, recs=0, req=None, done=None)
        print(w, 'base 0x%X par 0x%X Q 0x%X' % (m.base, par, q))
    t_end = time.time() + secs
    while time.time() < t_end:
        for w, s in st.items():
            if not s['q']:
                continue
            b = s['m'].read(s['q'], 0x70)
            v0, v1 = struct.unpack_from('<QQ', b, 0x10)
            owner, = struct.unpack_from('<Q', b, 0x60)
            depth, = struct.unpack_from('<I', b, 0x68)
            s['n'] += 1
            if owner:
                s['held'] += 1
                s['owners'][owner] = s['owners'].get(owner, 0) + 1
                if verbose:
                    print(w, '%.3f held owner 0x%X depth %d' % (time.time(), owner, depth))
            s['depth'] = max(s['depth'], depth)
            s['abort'] |= b[0x6C]
            if v0 and v1 >= v0:
                s['recs'] = max(s['recs'], (v1 - v0) // 12)
            if cnt is not None and s['n'] % 50 == 1:
                s['req'] = s['m'].u32(s['m'].base + cnt)
                s['done'] = s['m'].u32(s['m'].base + cnt + 4)
    for w, s in st.items():
        print('%s samples %d held %d owners %s max_depth %d abort %d max_records %d' % (
            w, s['n'], s['held'], ', '.join('0x%X x%d' % kv for kv in s['owners'].items()) or '-',
            s['depth'], s['abort'], s['recs']))
        if cnt is not None:
            s['req'] = s['m'].u32(s['m'].base + cnt)
            s['done'] = s['m'].u32(s['m'].base + cnt + 4)
            print('%s REQ %d DONE %d pending %d' % (w, s['req'], s['done'], (s['req'] - s['done']) & 0xFFFFFFFF))
        if len(s['owners']) > 1:
            print('%s SECOND OWNER SEEN: the race window opened on this game' % w)


if __name__ == '__main__':
    main()
