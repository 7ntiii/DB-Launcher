"""firekeep_gen.py: plan B for the fire at an eliminated finalist's spot (fire_planb_notes.md). Static generator,
allocated with Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes firekeep_live.py.
python firekeep_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

FIREKEEP_CAVE = [  # FAR cave records
    (0xC503A78, "00000000", "09B3FCD0", True),
    (0xC503A7C, "00000000", "291146F9", True),
    (0xC503A80, "00000000", "C90200B4", True),
    (0xC503A84, "00000000", "29696F39", True),
    (0xC503A88, "00000000", "89020035", True),
    (0xC503A8C, "00000000", "09054139", True),
    (0xC503A90, "00000000", "3F150071", True),
    (0xC503A94, "00000000", "21020054", True),
    (0xC503A98, "00000000", "C9B1FCB0", True),
    (0xC503A9C, "00000000", "29C546F9", True),
    (0xC503AA0, "00000000", "C90100B4", True),
    (0xC503AA4, "00000000", "29D540F9", True),
    (0xC503AA8, "00000000", "3F0100EB", True),
    (0xC503AAC, "00000000", "60010054", True),
    (0xC503AB0, "00000000", "6A000090", True),
    (0xC503AB4, "00000000", "4A211C91", True),
    (0xC503AB8, "00000000", "490140B9", True),
    (0xC503ABC, "00000000", "29050011", True),
    (0xC503AC0, "00000000", "490100B9", True),
    (0xC503AC4, "00000000", "090140B9", True),
    (0xC503AC8, "00000000", "490500B9", True),
    (0xC503ACC, "00000000", "1062FAD0", True),
    (0xC503AD0, "00000000", "10322291", True),
    (0xC503AD4, "00000000", "00021FD6", True),
    (0xC503AD8, "00000000", "F095FA90", True),
    (0xC503ADC, "00000000", "10423791", True),
    (0xC503AE0, "00000000", "00023FD6", True),
    (0xC503AE4, "00000000", "1062FAD0", True),
    (0xC503AE8, "00000000", "10322291", True),
    (0xC503AEC, "00000000", "00021FD6", True),
    (0x10C5988, "00000000", "F0A105D0", True),
    (0x10C598C, "00000000", "10E22991", True),
    (0x10C5990, "00000000", "00021FD6", True),
]
FIREKEEP = [
    (0x1145888, "52E91994", "4000FE17", True),
]

ORDER = [FIREKEEP_CAVE, FIREKEEP]
CAVES = {'FKEEP': 0xC503A78, 'FKBOX': 0xC50F708, 'TRAMP': 0x10C5988}
