"""TEST ONLY (LOADREL proof, 2026-11-20): give every finalist its own start area in a two-game rig final.
python diag/twin/force_slots.py A [SECONDS=240]

What FINALSLOTS2 (alpha) does on the host, done from outside for builds without it (v3.9.20): on host A, once
the final's start list is decided with fewer entries than pick slots, every slot of another player that has no
entry is rewritten as a copy of A's own slot with its number, pick kind 4, id -1, and MED_DECIDED (+0xB9) is
cleared so the game builds and sends the list again (then B gets its own area, as with 3 players).
Writes only those slot bytes and the one +0xB9 byte, once, on A. Starts acting only when the watch log shows
round 4 (start it during round 3)."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

MEDIATOR, MED_DECIDED, MED_LIST, MED_LIST_COUNT, MED_LIST_ENTRY = 0x5B44EA0, 0xB9, 0x290, 0x5D8, 0x68
MED_SLOTS, MED_SLOT_SIZE, MED_SLOT_COUNT, KIND, PICK = 0xC0, 0x30, 0x248, 0x10, 0x14
LOCAL_NO = 1  # rig host A is player 1


def main():
    who = sys.argv[1]
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 240
    m = Mem(who)
    end = time.time() + secs
    seen_decided = False
    while time.time() < end:
        time.sleep(0.2)
        med = m.u64(m.base + MEDIATOR)
        if not med:
            continue
        decided = m.read(med + MED_DECIDED, 1)[0]
        if not decided:
            seen_decided = True  # the final's own decision is still to come
            continue
        if not seen_decided:
            continue  # a list from before this tool started (round 3): wait for a fresh one
        slots = m.u64(med + MED_SLOT_COUNT)
        count = m.u64(med + MED_LIST_COUNT)
        if not 0 < slots <= 8 or count > 8:
            continue
        listed = [m.u32(med + MED_LIST + i * MED_LIST_ENTRY) for i in range(count)]
        raw = [m.read(med + MED_SLOTS + i * MED_SLOT_SIZE, MED_SLOT_SIZE) for i in range(slots)]
        mine = next((r for r in raw if struct.unpack_from('<I', r)[0] == LOCAL_NO), None)
        print('%s decided list %s, slots %s' % (time.strftime('%T'), listed,
                                               [struct.unpack_from('<I', r)[0] for r in raw]), flush=True)
        if mine is None:
            print('no own slot: nothing written', flush=True)
            return 1
        done = []
        for i, r in enumerate(raw):
            no = struct.unpack_from('<I', r)[0]
            if no in (0, LOCAL_NO) or no >= 100 or no in listed:
                continue
            s = bytearray(mine)
            struct.pack_into('<I', s, 0, no)
            s[KIND] = 4
            struct.pack_into('<i', s, PICK, -1)
            m.write(med + MED_SLOTS + i * MED_SLOT_SIZE, bytes(s))
            done.append(no)
        if done:
            m.write(med + MED_DECIDED, b'\0')
            print('%s slots of player(s) %s rewritten (kind 4, id -1), list to be built again' % (
                time.strftime('%T'), done), flush=True)
            return 0
        print('%s list complete: nothing written; waiting for the next list' % time.strftime('%T'), flush=True)
        seen_decided = False
        while time.time() < end and m.read(med + MED_DECIDED, 1)[0]:
            time.sleep(0.5)
    print('timed out: nothing written', flush=True)
    return 1


if __name__ == '__main__':
    sys.exit(main())
