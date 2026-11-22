"""loadgrave_gen.py: LOADGRAVE, third candidate for the final-load crash family. Static generator,
Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes loadgrave_live.py.
python loadgrave_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

LOADGRAVE_CAVE = [  # FAR cave records
    (0xC50439C, "00000000", "E9AA0510", True),
    (0xC5043A0, "00000000", "2A008052", True),
    (0xC5043A4, "00000000", "2B01EAB8", True),
    (0xC5043A8, "00000000", "6B190012", True),
    (0xC5043AC, "00000000", "A9AA0510", True),
    (0xC5043B0, "00000000", "290D0B8B", True),
    (0xC5043B4, "00000000", "2C81F3F8", True),
    (0xC5043B8, "00000000", "F3030CAA", True),
    (0xC5043BC, "00000000", "B30000B4", True),
    (0xC5043C0, "00000000", "E00313AA", True),
    (0xC5043C4, "00000000", "B0D7FBF0", True),
    (0xC5043C8, "00000000", "10422491", True),
    (0xC5043CC, "00000000", "00021FD6", True),
    (0xC5043D0, "00000000", "B0D7FBF0", True),
    (0xC5043D4, "00000000", "10F22491", True),
    (0xC5043D8, "00000000", "00021FD6", True),
    (0x3F7DC54, "00000000", "302C04F0", True),
    (0x3F7DC58, "00000000", "10720E91", True),
    (0x3F7DC5C, "00000000", "00021FD6", True),
]
LOADGRAVE = [
    (0x3FFB90C, "E00313AA", "D208FE17", True),
]

ORDER = [LOADGRAVE_CAVE, LOADGRAVE]
