"""TEST RIG ONLY (diag/net/late_notes.md): reproduce the late-guest fault on purpose, to test v417.
On game WHO, write 00 00 00 00 into the state word (pgd+0x46B0) of its copy of REMOTE player NO.
python diag/twin/state_zero.py WHO NO [show]      ("show" = read and print only, write nothing)

The pgd is resolved as part_flag.py does: WCM [main+0x5B3CD88] -> chr set [WCM+0x30] (0x38 per entry, entry 0 =
local) -> chr -> [chr+0x20] -> +0x1D0. Every pointer is checked. It also finds the pool copy the assist uses
(VirtuePlayer: [main+0x5B57EB8]+0x30 pool, 12 x 0x47F0, pgd+0xD0 == NO, the local pgds +0x20 / +0x28 skipped).
Refused (nothing written):
  - NO is the game's own player (local pgd +0x20 / +0x28, entry 0, or pgd+0xD0 == own number);
  - no chr with that number, or the chr's pgd and the pool copy differ (the test would not mean what it says);
  - the current word is not 01 01 00 00.
Check sequence (round 1, UpdatePhase, B, player 1):
  1. python diag/twin/state_zero.py B 1          -> "after 00000000"
  2. wait 8 s; python diag/twin/part_flag.py AB  -> B shows "no 1 ... state 01010000" again (v417),
     and B's dusk_lan.txt has one "!!! state word: our copy of player 1 ... (v417 ...)" line
  3. the round-1 cut check on B lists "state words 1=01 01 00 00 2=01 01 00 00"; match4 ranks agree on A and B
  Baseline (a build without v417): after step 1 the word stays 00000000, B's cut check lists 1=00 00 00 00 and
  B's ranking has only player 2 (the fault of 2026-11-16 18:27)."""
import struct
import sys
sys.path.insert(0, 'diag/twin')
from mem import Mem

WCM, NET_PLAYERS = 0x5B3CD88, 0x5B57EB8
PGD_LOCAL, PGD_LOCAL_ALT, PGD_POOL, PGD_SIZE, PGD_MAX = 0x20, 0x28, 0x30, 0x47F0, 12
NO_OFF, STATE, FLAG = 0xD0, 0x46B0, 0x46A0
IN = bytes.fromhex('01010000')
PLAYER_VT = 0x572B108          # part_flag.py: entries with this vtable are skipped


def fail(text):
    print('REFUSED:', text)
    sys.exit(2)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ('A', 'B', 'C', 'D'):
        print(__doc__)
        return 2
    who, no, show = sys.argv[1], int(sys.argv[2]), 'show' in sys.argv[3:]
    if not 1 <= no <= 16:
        fail(f'player number {no} is not 1..16')
    m = Mem(who)
    wcm = m.u64(m.base + WCM)
    if not wcm:
        fail('WCM is null (no match loaded?)')
    table = m.u64(wcm + 0x30)
    if not table:
        fail('WCM+0x30 chr set is null')
    net = m.u64(m.base + NET_PLAYERS)
    if not net:
        fail('network player table is null')
    local = {m.u64(net + PGD_LOCAL), m.u64(net + PGD_LOCAL_ALT)} - {0}
    own_nos = {m.u32(p + NO_OFF) for p in local}
    if no in own_nos:
        fail(f'player {no} is this game\'s own player')
    arr = m.read(table, 0x38 * 8)
    chr_pgd = 0
    for i in range(8):
        c = struct.unpack_from('<Q', arr, 0x38 * i)[0]
        if not c or m.u64(c) == m.base + PLAYER_VT:
            continue
        data = m.u64(c + 0x20)
        pgd = m.u64(data + 0x1D0) if data else 0
        if not pgd or m.u32(pgd + NO_OFF) != no:
            continue
        if i == 0 or pgd in local:
            fail(f'player {no} is the local entry here')
        chr_pgd = pgd
        break
    if not chr_pgd:
        fail(f'no player chr with number {no} on game {who}')
    pool = m.u64(net + PGD_POOL)
    pool_pgd = 0
    for k in range(PGD_MAX if pool else 0):
        p = pool + k * PGD_SIZE
        if p in local:
            continue
        if m.u32(p + NO_OFF) == no:
            pool_pgd = p
            break
    word = m.read(chr_pgd + STATE, 4)
    print(f'{who} player {no}: chr pgd {chr_pgd:#x}, pool pgd {pool_pgd:#x}, flag {m.read(chr_pgd + FLAG, 1)[0]}, '
          f'before {word.hex()}')
    if pool_pgd != chr_pgd:
        fail('the chr\'s pgd is not the pool copy the assist reads; nothing written')
    if show:
        return 0
    if word != IN:
        fail(f'the word is {word.hex()}, not 01010000')
    m.write(chr_pgd + STATE, b'\x00\x00\x00\x00')
    print(f'{who} player {no}: after {m.read(chr_pgd + STATE, 4).hex()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
