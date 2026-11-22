"""READ-ONLY (diag/net/lineup_notes.md): the PlayerGameData copies the loading-screen line-up reads.
python diag/twin/lineup_read.py WHO              one snapshot of game WHO (A, B, C, D)
python diag/twin/lineup_read.py WHO watch SECS   poll every 0.25 s for SECS seconds; print a line only when a
                                                 copy changes (plus the first snapshot)
The line-up functor 0x1315840 adds a figure only when pgd+0xD0 != -1 and take-part byte +0x46A0 == 1, once, when
the loading screen is built. So the next match shows whether the other guest's copy lacks its number or take-part
byte at that moment. Nothing is written; each pointer is checked ("-" = not readable).

Per copy: slot (pool index 0..11, or L20 / L28 = the local pgds net+0x20 / +0x28), address, no (+0xD0), rno
(+0xD4), part (+0x46A0), state (+0x46B0 bytes). Pool slots with no = 0 and part = 0 are counted as empty, not
printed. Each line starts with the time (hh:mm:ss.mmm) and the phase (stage+0x50, '-' before the stage exists)."""
import struct
import sys
import time
sys.path.insert(0, 'diag/twin')
from mem import Mem

NET, STAGE = 0x5B57EB8, 0x5B3CDF8
PGD_LOCAL, PGD_LOCAL_ALT, PGD_POOL, PGD_SIZE, PGD_MAX = 0x20, 0x28, 0x30, 0x47F0, 12


def ok(p):
    return p and p < (1 << 48) and p % 8 == 0


def rd(m, a, n):
    try:
        return m.read(a, n)
    except Exception:
        return None


def ptr(m, a):
    b = rd(m, a, 8)
    p = struct.unpack('<Q', b)[0] if b else 0
    return p if ok(p) else 0


def copy(m, pgd):
    head = rd(m, pgd + 0xD0, 8)
    tail = rd(m, pgd + 0x46A0, 0x14)
    if head is None or tail is None:
        return None
    no, rno = struct.unpack('<ii', head)
    return no, rno, tail[0], tail[0x10:0x14].hex()


def snapshot(m):
    stage = ptr(m, m.base + STAGE)
    phase = '-'
    if stage:
        b = rd(m, stage + 0x50, 4)
        phase = str(struct.unpack('<I', b)[0]) if b else '-'
    net = ptr(m, m.base + NET)
    rows = []
    if not net:
        return phase, ['net table null']
    for name, off in (('L20', PGD_LOCAL), ('L28', PGD_LOCAL_ALT)):
        p = ptr(m, net + off)
        if p:
            c = copy(m, p)
            rows.append(f'{name} {p:#x} ' + (f'no {c[0]} rno {c[1]} part {c[2]} state {c[3]}' if c else 'unreadable'))
        else:
            rows.append(f'{name} null')
    pool = ptr(m, net + PGD_POOL)
    empty = 0
    if not pool:
        rows.append('pool null')
    for k in range(PGD_MAX if pool else 0):
        p = pool + k * PGD_SIZE
        c = copy(m, p)
        if c is None:
            rows.append(f'{k} {p:#x} unreadable')
        elif c[0] == 0 and c[2] == 0:
            empty += 1
        else:
            rows.append(f'{k} {p:#x} no {c[0]} rno {c[1]} part {c[2]} state {c[3]}')
    rows.append(f'empty pool slots {empty}')
    return phase, rows


def stamp():
    t = time.time()
    return time.strftime('%H:%M:%S', time.localtime(t)) + f'.{int(t * 1000) % 1000:03d}'


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ('A', 'B', 'C', 'D'):
        print(__doc__)
        return 2
    m = Mem(args[0])
    secs = 0.0
    if len(args) >= 3 and args[1] == 'watch':
        secs = float(args[2])
    end = time.time() + secs
    last = None
    while True:
        phase, rows = snapshot(m)
        if rows != last:
            print(f'{stamp()} {args[0]} phase {phase} | ' + ' | '.join(rows), flush=True)
            last = rows
        if time.time() >= end:
            break
        time.sleep(0.25)
    return 0


if __name__ == '__main__':
    sys.exit(main())
