"""TEST ONLY (final-crash trigger proof, 2026-11-20): make player NO start round R in area AREA, on host A.
python diag/twin/pick_area.py A NO AREA [ROUND=3] [SECONDS=600]

On the host, while round R's intermission list is not decided yet (MED_DECIDED 0), the slot of player NO is held
at pick kind 3 (an area) id AREA every 0.1 s; the game then builds and sends its list with that area. Writes only
those 5 bytes of that one slot, only in round R, then stops at the first decided list and prints it."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

STAGE_PHASE, P_ROUND, P_STATE = 0x5B3CDF8, 0xB8, 0x50
MEDIATOR, MED_DECIDED, MED_LIST, MED_LIST_COUNT, MED_LIST_ENTRY = 0x5B44EA0, 0xB9, 0x290, 0x5D8, 0x68
MED_SLOTS, MED_SLOT_SIZE, MED_SLOT_COUNT, KIND, PICK = 0xC0, 0x30, 0x248, 0x10, 0x14


def main():
    who, no, area = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    rnd = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    end = time.time() + (float(sys.argv[5]) if len(sys.argv) > 5 else 600)
    m = Mem(who)
    writes = 0
    while time.time() < end:
        time.sleep(0.1)
        stage = m.u64(m.base + STAGE_PHASE)
        med = m.u64(m.base + MEDIATOR)
        if not stage or not med or m.u32(stage + P_ROUND) != rnd:
            continue
        if m.read(med + MED_DECIDED, 1)[0]:
            if writes:
                count = m.u64(med + MED_LIST_COUNT)
                lst = [(m.u32(med + MED_LIST + i * MED_LIST_ENTRY), m.u32(med + MED_LIST + i * MED_LIST_ENTRY + 0x24))
                       for i in range(min(count, 8))]
                print('%s round %d list decided (no, area): %s; %d pick writes' % (time.strftime('%T'), rnd, lst,
                                                                                   writes), flush=True)
                return 0
            continue
        slots = m.u64(med + MED_SLOT_COUNT)
        if 1 <= slots < 8 and all(m.u32(med + MED_SLOTS + i * MED_SLOT_SIZE) != no for i in range(slots)):
            # the guest's pick never reached the host: add its slot (a copy of slot 0 with its number), as
            # FinalSlots does in the final
            s = bytearray(m.read(med + MED_SLOTS, MED_SLOT_SIZE))
            struct.pack_into('<I', s, 0, no)
            m.write(med + MED_SLOTS + slots * MED_SLOT_SIZE, bytes(s))
            m.write(med + MED_SLOT_COUNT, struct.pack('<Q', slots + 1))
            print('%s round %d: player %d had no slot here: added (%d -> %d slots)' % (
                time.strftime('%T'), rnd, no, slots, slots + 1), flush=True)
            slots += 1
        for i in range(min(slots, 8)):
            at = med + MED_SLOTS + i * MED_SLOT_SIZE
            if m.u32(at) == no:
                if m.read(at + KIND, 1)[0] != 3 or struct.unpack('<i', m.read(at + PICK, 4))[0] != area:
                    m.write(at + KIND, b'\x03')
                    m.write(at + PICK, struct.pack('<i', area))
                    writes += 1
                    if writes == 1:
                        print('%s round %d: player %d slot set to area %d' % (time.strftime('%T'), rnd, no, area),
                              flush=True)
    print('timed out (%d pick writes)' % writes, flush=True)
    return 1


if __name__ == '__main__':
    sys.exit(main())
