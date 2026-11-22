"""loadrel_gen.py: LOADREL, the final-load crash root fix. Static generator,
Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes loadrel_live.py.
python loadrel_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

LOADREL_CAVE = [  # FAR cave records
    (0xC5041A8, "00000000", "69024239", True),
    (0xC5041AC, "00000000", "3F050071", True),
    (0xC5041B0, "00000000", "E0000054", True),
    (0xC5041B4, "00000000", "3F090071", True),
    (0xC5041B8, "00000000", "A0000054", True),
    (0xC5041BC, "00000000", "68024239", True),
    (0xC5041C0, "00000000", "B0D7FBF0", True),
    (0xC5041C4, "00000000", "10A22191", True),
    (0xC5041C8, "00000000", "00021FD6", True),
    (0xC5041CC, "00000000", "490000F0", True),
    (0xC5041D0, "00000000", "29C12391", True),
    (0xC5041D4, "00000000", "2A0140B9", True),
    (0xC5041D8, "00000000", "4A050011", True),
    (0xC5041DC, "00000000", "2A0100B9", True),
    (0xC5041E0, "00000000", "681248B8", True),
    (0xC5041E4, "00000000", "B0D7FBF0", True),
    (0xC5041E8, "00000000", "10A22291", True),
    (0xC5041EC, "00000000", "00021FD6", True),
    (0x3F7BB74, "00000000", "502C04B0", True),
    (0x3F7BB78, "00000000", "10A20691", True),
    (0x3F7BB7C, "00000000", "00021FD6", True),
]
LOADREL = [
    (0x3FFB864, "68024239", "C400FE17", True),
]

ORDER = [LOADREL_CAVE, LOADREL]
CAVES = {'LOADREL': 0xC5041A8, 'LRBOX': 0xC50F8F0, 'TRAMP': 0x3F7BB74, 'HOOK_WORD': 0x17FE00C4}
