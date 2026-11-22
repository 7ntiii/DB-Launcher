"""Power of Blood choice: what the "Select what to receive" dialog offers vs what the per-player Power drop will
give. READ ONLY (no writes, no input). Notes: diag/net/sigil15_notes.md section 3.
python diag/twin/powerchoice.py [GAMES=AB] [watch SECONDS]

Per game:
  members   session manager *(main+0x5B3CE08) +0x1248..+0x1250, 0xF8 per member (stride used by 0x1598110 /
            0x15A4634) [V]. 0x15AE920 (item-lot award, the only dialog opener left for a handle -0x20 dialog in a
            match) runs only when this count is 0 [V 0x15AE954..0x15AE974].
  drops     MapItemMan *(main+0x5B3CDC0) +0x1B8 per-player world items: id +0x30 (low nibble 9 = per-player), owner
            mask +0x290; the record is node+0x30 [I, as 0x159D824 uses item+0x30]: entry count +0x68, entries
            12 bytes from +0x6C {u32 id, u32 count, u32 extra} [V layout 0x15A5140..0x15A5158]. The award of a
            kind-9 item gives EVERY entry (0x15981B8 -> 0x15A5020 with w4 = -1) [V].
  dialog    *(main+0x5B76648) +0x20.. entries of 0x28 bytes (+0 id, +4 count) = what the dialog shows [I layout,
            powers.py].
  owned     Power-like ids in pgd+0xED0..+0x2900 (as powers.py) -> compare before / after OK.
Read it once with the dialog open (before OK) and once after."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from world_lib import W  # noqa: E402

MGR3, MAPITEM, UI, GDM = 0x5B3CE08, 0x5B3CDC0, 0x5B76648, 0x5B57EB8


def vec(w, a, stride, limit=16):
    b, e = w.q(a), w.q(a + 8)
    if not b or not e or e < b:
        return []
    return [b + stride * k for k in range(min((e - b) // stride, limit))]


def block(g):
    w = W(g)
    L = ['== %s' % g]
    m3 = w.g(MGR3)
    if m3:
        b, e = w.q(m3 + 0x1248), w.q(m3 + 0x1250)
        n = (e - b) // 0xF8 if b and e and e >= b else None
        L.append('  session members (+0x1248, 0xF8 each): %s -> 0x15AE920 lot award %s' % (
            n, 'RUNS (dialog with handle -0x20 possible)' if n == 0 else 'returns at once' if n else '?'))
    mi = w.g(MAPITEM)
    node, k = (w.q(mi + 0x1B8) if mi else None), 0
    while node and k < 32:
        iid, mask = w.d(node + 0x30), w.q(node + 0x290) or 0
        cnt = w.d(node + 0x68)
        ents = []
        for j in range(min(cnt or 0, 8)):
            e = w.rd(node + 0x6C + 12 * j, 12)
            if e:
                ents.append('%08x x%d (+8 %08x)' % struct.unpack('<3I', e))
        L.append('  per-player item %08x owner slots %s | record count %s: %s' % (
            iid or 0, [b for b in range(12) if mask >> b & 1], cnt, ' / '.join(ents) or '-'))
        node, k = w.q(node + 8), k + 1
    L.append('  per-player items: %d' % k)
    ui = w.g(UI)
    sel = vec(w, ui + 0x20, 0x28) if ui else []
    L.append('  dialog list: %d entries %s' % (len(sel), ' / '.join('%08x x%s' % (w.d(e) or 0, w.d(e + 4))
                                                                    for e in sel) or '-'))
    gdm = w.g(GDM)
    pgd = w.q(gdm + 0x20) if gdm else None
    blob = w.rd(pgd + 0xED0, 0x2900 - 0xED0) if pgd else None
    found = []
    if blob:
        for o in range(0, len(blob) - 3, 4):
            v = struct.unpack_from('<I', blob, o)[0]
            if 1000000 <= (v & 0x0FFFFFFF) < 2200000 and (v >> 28) in (0, 7):
                found.append('+%X=%x' % (0xED0 + o, v))
    L.append('  owned Power ids: %s' % (' '.join(found[:24]) or '-'))
    w.report_missing()
    return L


args = sys.argv[1:]
games = args[0] if args and args[0].isalpha() and args[0] != 'watch' else 'AB'
watch = float(args[args.index('watch') + 1]) if 'watch' in args and args.index('watch') + 1 < len(args) else 0.0
last = {}
for g in games:
    last[g] = block(g)
    print('\n'.join(last[g]))
end = time.time() + watch
while time.time() < end:
    time.sleep(1.0)
    for g in games:
        b = block(g)
        if b != last[g]:
            print(time.strftime('%H:%M:%S'))
            print('\n'.join(b))
            last[g] = b
