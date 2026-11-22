"""icons1_gen.py: ICONS1, alpha reconstruction (alpha_reconstructions.md a). Static generator, Gen(dry=True):
cave_registry.md is NOT written (the lead adds the printed rows). Writes icons1_live.py.
python icons1_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

ICONS1_CAVE = [  # FAR cave records
    (0xC5040C8, "00000000", "01E540B9", True),
    (0xC5040CC, "00000000", "E101F836", True),
    (0xC5040D0, "00000000", "410000F0", True),
    (0xC5040D4, "00000000", "21606339", True),
    (0xC5040D8, "00000000", "61010034", True),
    (0xC5040DC, "00000000", "480000F0", True),
    (0xC5040E0, "00000000", "08612391", True),
    (0xC5040E4, "00000000", "010540B9", True),
    (0xC5040E8, "00000000", "21040011", True),
    (0xC5040EC, "00000000", "010500B9", True),
    (0xC5040F0, "00000000", "41D49052", True),
    (0xC5040F4, "00000000", "2100A072", True),
    (0xC5040F8, "00000000", "9059FAB0", True),
    (0xC5040FC, "00000000", "10E20D91", True),
    (0xC504100, "00000000", "00021FD6", True),
    (0xC504104, "00000000", "01E540B9", True),
    (0xC504108, "00000000", "9059FAB0", True),
    (0xC50410C, "00000000", "10E20D91", True),
    (0xC504110, "00000000", "00021FD6", True),
    (0xFB5E54, "00000000", "70AA05F0", True),
    (0xFB5E58, "00000000", "10220391", True),
    (0xFB5E5C, "00000000", "00021FD6", True),
]
ICONS1 = [
    (0x1035374, "01E540B9", "B802FE17", True),
]

ORDER = [ICONS1_CAVE, ICONS1]
CAVES = {'ICONS1': 0xC5040C8, 'I1BOX': 0xC50F8D8, 'TRAMP': 0xFB5E54, 'HOOK_WORD': 0x17FE02B8}
