"""READ-ONLY (diag/net/spectate2_notes.md): the game's spectator manager on each game, one line per game.
python diag/twin/watch_read.py WHO            one line for game WHO (A, B, C, D)
python diag/twin/watch_read.py ABC watch 60   one line per game every 2 s for 60 s (only changed lines)
Nothing is written. Run it on the out player's game during a 3-player final (laptop check S1).

Fields ("-" = null or not readable):
  man     *(main+0x5B55D30), CSGameWatchingMan (spectator manager)        [V xref 51 readers]
  mode    man+0x50 u32 (power_offer_notes 2: "spectator mode", 1/4/5 or 2..5 with +0x17A)
  partner man+0x170 u32 (Bloodbound partner id, bloodbound_notes 1e)
  w174    man+0x174 f32 (0.5 written by the quit path 0x11DBF34)
  on17a   man+0x17A u8 (watching enabled: the start functor 0x11E2B78 asks for step 10 only when set)
  f17d    man+0x17D u8 (set by the stage at 0x1150974 and by the manager's own steps)
  tgt     man+0xB8 u32 and man+0x2B0 u32 (copied 0xB8 -> 0x2B0 by the stage at 0x1150930; -1 = none)
  imp     man+0x2A8 != 0 (CSGameWatchingManImp)
  asked   man+0x2B4 u8 (a start was asked: 0x11E2C58)
  p164    stage+0x164 u8 (the OFFLINE spectator mark; ends UpdatePhase for the own player)
  step    stage+0x50 (6 = UpdatePhase)   round stage+0xB8"""
import struct
import sys
import time
sys.path.insert(0, 'diag/twin')
from mem import Mem

STAGE, WATCH = 0x5B3CDF8, 0x5B55D30
ORDER = ('step', 'round', 'p164', 'man', 'mode', 'partner', 'w174', 'on17a', 'f17d', 'tgt', 'imp', 'asked')


def read_one(m):
    def rd(a, fmt):
        try:
            b = m.read(a, struct.calcsize(fmt))
        except Exception:
            return None
        return struct.unpack('<' + fmt, b)[0] if b else None

    def ptr(a):
        v = rd(a, 'Q')
        return v if v and v < (1 << 48) and v % 8 == 0 else 0

    f = dict.fromkeys(ORDER, '-')
    stage = ptr(m.base + STAGE)
    if stage:
        for key, off, fmt in (('step', 0x50, 'I'), ('round', 0xB8, 'I'), ('p164', 0x164, 'B')):
            v = rd(stage + off, fmt)
            f[key] = str(v) if v is not None else '-'
    man = ptr(m.base + WATCH)
    if man:
        f['man'] = 'yes'
        for key, off, fmt in (('mode', 0x50, 'I'), ('partner', 0x170, 'I'), ('on17a', 0x17A, 'B'),
                              ('f17d', 0x17D, 'B'), ('asked', 0x2B4, 'B')):
            v = rd(man + off, fmt)
            f[key] = str(v) if v is not None else '-'
        v = rd(man + 0x174, 'f')
        f['w174'] = f'{v:.2f}' if v is not None else '-'
        a, b = rd(man + 0xB8, 'i'), rd(man + 0x2B0, 'i')
        f['tgt'] = f'{a}/{b}'
        f['imp'] = '1' if ptr(man + 0x2A8) else '0'
    return f


def line(who, f):
    return who + ' ' + ' '.join(f'{k}={f[k]}' for k in ORDER)


def main():
    args = sys.argv[1:]
    if not args or any(c not in 'ABCD' for c in args[0]):
        print(__doc__)
        return 2
    mems = {w: Mem(w) for w in args[0]}
    if len(args) >= 2 and args[1] == 'watch':
        seconds = float(args[2]) if len(args) >= 3 else 60.0
        last = {}
        end = time.time() + seconds
        while time.time() < end:
            for w, m in mems.items():
                text = line(w, read_one(m))
                if last.get(w) != text:
                    last[w] = text
                    print(time.strftime('%H:%M:%S'), text, flush=True)
            time.sleep(2)
        return 0
    for w, m in mems.items():
        print(line(w, read_one(m)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
