"""warpreplay_gen.py: WARPREPLAY (v4.51, on alpha 11 WARPDEFER). Static generator, Gen(dry=True): rows printed,
cave_registry.md not written. Writes warpreplay_live.py. python warpreplay_gen.py [--dry]   (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

WARPREPLAY_CAVE = [  # FAR cave records
    (0xC50448C, "00000000", "7FA21A39", True),
    (0xC504490, "00000000", "0AC80510", True),
    (0xC504494, "00000000", "4B054039", True),
    (0xC504498, "00000000", "AB010034", True),
    (0xC50449C, "00000000", "5F050039", True),
    (0xC5044A0, "00000000", "4B0D40B9", True),
    (0xC5044A4, "00000000", "6B050011", True),
    (0xC5044A8, "00000000", "4B0D00B9", True),
    (0xC5044AC, "00000000", "E00313AA", True),
    (0xC5044B0, "00000000", "9E000010", True),
    (0xC5044B4, "00000000", "705FFAF0", True),
    (0xC5044B8, "00000000", "10023C91", True),
    (0xC5044BC, "00000000", "00021FD6", True),
    (0xC5044C0, "00000000", "505FFAF0", True),
    (0xC5044C4, "00000000", "10F22391", True),
    (0xC5044C8, "00000000", "00021FD6", True),
    (0xC5044CC, "00000000", "505FFAF0", True),
    (0xC5044D0, "00000000", "10C22191", True),
    (0xC5044D4, "00000000", "00021FD6", True),
    (0x1077DEC, "00000000", "70A405B0", True),
    (0x1077DF0, "00000000", "10321291", True),
    (0x1077DF4, "00000000", "00021FD6", True),
]
WARPREPLAY = [
    (0x10EF86C, "7FA21A39", "6021FE17", True),
]

ORDER = [WARPREPLAY_CAVE, WARPREPLAY]
