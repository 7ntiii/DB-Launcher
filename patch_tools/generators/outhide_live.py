"""outhide_gen.py: OUTHIDE, the game-thread half of v4.39 (fire_alpha_notes.md). Static generator, Gen(dry=True):
cave_registry.md is NOT written (the lead adds the printed rows). Writes outhide_live.py.
python outhide_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

OUTHIDE_CAVE = [  # FAR cave records
    (0xC504078, "00000000", "4A0000F0", True),
    (0xC50407C, "00000000", "4A412391", True),
    (0xC504080, "00000000", "400140F9", True),
    (0xC504084, "00000000", "A00100B4", True),
    (0xC504088, "00000000", "5F0100F9", True),
    (0xC50408C, "00000000", "88578252", True),
    (0xC504090, "00000000", "0800088B", True),
    (0xC504094, "00000000", "090140F9", True),
    (0xC504098, "00000000", "290172B2", True),
    (0xC50409C, "00000000", "090100F9", True),
    (0xC5040A0, "00000000", "099D40B8", True),
    (0xC5040A4, "00000000", "29011832", True),
    (0xC5040A8, "00000000", "090100B9", True),
    (0xC5040AC, "00000000", "D091FAB0", True),
    (0xC5040B0, "00000000", "10822D91", True),
    (0xC5040B4, "00000000", "00023FD6", True),
    (0xC5040B8, "00000000", "880340F9", True),
    (0xC5040BC, "00000000", "D07EFAD0", True),
    (0xC5040C0, "00000000", "10322591", True),
    (0xC5040C4, "00000000", "00021FD6", True),
    (0x145F9D4, "00000000", "308505B0", True),
    (0x145F9D8, "00000000", "10E20191", True),
    (0x145F9DC, "00000000", "00021FD6", True),
]
OUTHIDE = [
    (0x14DE948, "880340F9", "2304FE17", True),
]

ORDER = [OUTHIDE_CAVE, OUTHIDE]
CAVES = {'OUTHIDE': 0xC504078, 'OHBOX': 0xC50F8D0, 'TRAMP': 0x145F9D4}
