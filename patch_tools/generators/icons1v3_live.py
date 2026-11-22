"""icons1v3_gen.py: ICONS1 v3 REPICK, alpha RECONSTRUCTION (alpha_reconstructions.md a). Static generator,
Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes icons1v3_live.py.
python icons1v3_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

I1REPICK_CAVE = [  # FAR cave records
    (0xC504118, "00000000", "FF0301D1", True),
    (0xC50411C, "00000000", "E00700A9", True),
    (0xC504120, "00000000", "E20F01A9", True),
    (0xC504124, "00000000", "E41702A9", True),
    (0xC504128, "00000000", "E61F03A9", True),
    (0xC50412C, "00000000", "490000F0", True),
    (0xC504130, "00000000", "29812391", True),
    (0xC504134, "00000000", "200140F9", True),
    (0xC504138, "00000000", "000100B4", True),
    (0xC50413C, "00000000", "3F0100F9", True),
    (0xC504140, "00000000", "2A0940B9", True),
    (0xC504144, "00000000", "4A050011", True),
    (0xC504148, "00000000", "2A0900B9", True),
    (0xC50414C, "00000000", "F060FA90", True),
    (0xC504150, "00000000", "10022E91", True),
    (0xC504154, "00000000", "00023FD6", True),
    (0xC504158, "00000000", "E00740A9", True),
    (0xC50415C, "00000000", "E20F41A9", True),
    (0xC504160, "00000000", "E41742A9", True),
    (0xC504164, "00000000", "E61F43A9", True),
    (0xC504168, "00000000", "FF030191", True),
    (0xC50416C, "00000000", "48B2FCB0", True),
    (0xC504170, "00000000", "3062FAF0", True),
    (0xC504174, "00000000", "10B22791", True),
    (0xC504178, "00000000", "00021FD6", True),
    (0x10CF724, "00000000", "B0A105B0", True),
    (0x10CF728, "00000000", "10620491", True),
    (0x10CF72C, "00000000", "00021FD6", True),
]
I1REPICK = [
    (0x114B9E8, "085002D0", "4F0FFE17", True),
]

ORDER = [I1REPICK_CAVE, I1REPICK]
CAVES = {'I1REPICK': 0xC504118, 'I1RBOX': 0xC50F8E0, 'TRAMP': 0x10CF724, 'HOOK_WORD': 0x17FE0F4F}
