"""Goldblood Stake count of each game's LOCAL player (read only): python diag/twin/stakes.py [GAMES=AB] [WATCH_SECONDS=0]
WATCH_SECONDS > 0: poll every 0.5 s and print a line only when something changed (use both stakes, die, revive).

pgd  = *(*(main+0x5B57EB8)+0x20) (local PlayerGameData): +0xD0 player no, +0x78 level, +0x7C blood,
       +0x110 u8 base stake count (refill target), +0x40D0 u8 type (1 local, 2 remote copy),
       +0x4648 u8 max, +0x4649 u8 count (what the HUD shows).
item mgr [[main+0x59E1B28]]: slots of 0x290 from +8 (slot+0 = player no); records deque at slot+0x50
       (start +0x70, count +0x78, 102 per block, 0x28 each): +0x10 item id, +0x14 asked, +0x18 state
       (0 wait, 1 accepted, 2 rejected), +0x1C f32 time, +0x20 remaining count.  [I] f32 [[slot+8]+0x40] = time of
       the last count write (stale check in 0xCFC988).
chr  = *(*(main+0x5B3CD88)+0x1A8) (local player): inplace = u8 chr+0x2618 (1 = revive in place, no top-up),
       dead = [[chr+0x68]+0x38]+0x28 bit 1; offline = u8 *(main+0x5B65C20)+0xBDA (0 in LAN).
Expected with the built-in STAKE_REFILL + stake2_live.py STAKE_TOPUP (stake2_notes.md): count 2 -> 1 -> 0 on uses;
after a death + revive (statue, inplace 0) count = max(count, base) ONCE, level/blood UNCHANGED (0x17BD69C top-up,
not 0xD1D5F4); the other game's line for its own player unchanged. Without STAKE_TOPUP the count stays 0."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
watch = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
mems = {w: Mem(w) for w in games}


def f32(m, a):
    return struct.unpack('<f', m.read(a, 4))[0]


def records(m, slot):
    mp = m.u64(slot + 0x50)
    start, count = m.u64(slot + 0x70), m.u64(slot + 0x78)
    out = []
    if not mp or count > 64:
        return out
    for i in range(max(0, count - 3), count):
        idx = start + i
        blk = m.u64(mp + idx // 102 * 8)
        if not blk:
            break
        r = m.read(blk + idx % 102 * 0x28, 0x28)
        item, asked, state, t, left = struct.unpack_from('<IBxxxifB', r, 0x10)
        out.append('item %08X asked %d state %d t %.2f left %d' % (item, asked, state, t, left))
    return out


def line(w):
    m = mems[w]
    gdm = m.u64(m.base + 0x5B57EB8)
    pgd = m.u64(gdm + 0x20) if gdm else 0
    if not pgd:
        return '%s no local PlayerGameData' % w
    no = struct.unpack('<i', m.read(pgd + 0xD0, 4))[0]
    lvl, blood = m.u32(pgd + 0x78), m.u32(pgd + 0x7C)
    base = m.read(pgd + 0x110, 1)[0]
    typ = m.read(pgd + 0x40D0, 1)[0]
    mx, cnt = m.read(pgd + 0x4648, 2)
    s = '%s player %d type %d stakes %d / max %d base %d level %d blood %d' % (w, no, typ, cnt, mx, base, lvl, blood)
    # stake2_notes.md: revive top-up 0x17BD69C needs the local chr dead (bit 1) and inplace (chr+0x2618) == 0;
    # it is gated by offline +0xBDA at 0x17BE63C unless stake2_live.py STAKE_TOPUP is applied
    wcm = m.u64(m.base + 0x5B3CD88)
    chr_ = m.u64(wcm + 0x1A8) if wcm else 0
    if chr_:
        st = m.u64(m.u64(chr_ + 0x68) + 0x38) if m.u64(chr_ + 0x68) else 0
        s += ' | inplace %d dead %s' % (m.read(chr_ + 0x2618, 1)[0], (m.read(st + 0x28, 1)[0] >> 1 & 1) if st else '-')
    off = m.u64(m.base + 0x5B65C20)
    s += ' offline %s' % (m.read(off + 0xBDA, 1)[0] if off else '-')
    mgr = m.u64(m.u64(m.base + 0x59E1B28))
    if mgr:
        for k in range(13):
            slot = mgr + 8 + 0x290 * k
            if struct.unpack('<i', m.read(slot, 4))[0] != no:
                continue
            sub = m.u64(slot + 8)
            s += ' | slot %d last-write-t %s | rec %s' % (k, ('%.2f' % f32(m, sub + 0x40)) if sub else '-',
                                                         records(m, slot) or '-')
            break
    return s


last = {}
t0 = time.time()
while True:
    for w in games:
        try:
            s = line(w)
        except Exception as e:  # game closed or debug server busy
            s = '%s read failed: %s' % (w, e)
        if s != last.get(w):
            print('%6.1f %s' % (time.time() - t0, s), flush=True)
            last[w] = s
    if time.time() - t0 >= watch:
        break
    time.sleep(0.5)
