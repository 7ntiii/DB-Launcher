"""TIMER_RESYNC (timer_fix_gen.py, timer_notes.md section 7): re-show the HUD window whose fade-out the
panel state machine did not do. Variant A (the final only). NOT built, NOT applied. Apply the CAVE group before the HOOK group.
Undo = the HOOK group's original word (0x12E339C ldrb w8, [x24]).
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

TIMER_RESYNC_CAVE = [  # FAR cave records
    (0xC503390, "00000000", "08034039", True),
    (0xC503394, "00000000", "48020035", True),
    (0xC503398, "00000000", "69E343F9", True),
    (0xC50339C, "00000000", "090200B4", True),
    (0xC5033A0, "00000000", "29714739", True),
    (0xC5033A4, "00000000", "C9010035", True),
    (0xC5033A8, "00000000", "69235F39", True),
    (0xC5033AC, "00000000", "89010035", True),
    (0xC5033B0, "00000000", "69275F39", True),
    (0xC5033B4, "00000000", "49010035", True),
    (0xC5033B8, "00000000", "C9B1FCB0", True),
    (0xC5033BC, "00000000", "29FD46F9", True),
    (0xC5033C0, "00000000", "E90000B4", True),
    (0xC5033C4, "00000000", "30B940B9", True),
    (0xC5033C8, "00000000", "1F120071", True),
    (0xC5033CC, "00000000", "81000054", True),
    (0xC5033D0, "00000000", "30C559F9", True),
    (0xC5033D4, "00000000", "500000B4", True),
    (0xC5033D8, "00000000", "28008052", True),
    (0xC5033DC, "00000000", "106FFA90", True),
    (0xC5033E0, "00000000", "10820E91", True),
    (0xC5033E4, "00000000", "00021FD6", True),
    (0x12E2424, "00000000", "109105B0", True),
    (0x12E2428, "00000000", "10420E91", True),
    (0x12E242C, "00000000", "00021FD6", True),
]
TIMER_RESYNC_HOOK = [
    (0x12E339C, "08034039", "22FCFF17", True),
]

ORDER = [TIMER_RESYNC_CAVE, TIMER_RESYNC_HOOK]
