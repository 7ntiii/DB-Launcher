"""starfrag_pick_gen.py: a picked-up Star Fragment is added to the LOCAL picker's inventory in a LAN match (static
generator). Reads nso/*.bin, patch_manager.cpp and every *_live.py (through cave_lib). Writes starfrag_pick_live.py
and claims its far range in cave_registry.md (owner `starfrag_pick_gen`).
python starfrag_pick_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: starfrag3_notes.md.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

STARFRAG_PICK_CAVE = [  # FAR cave records
    (0xC501C08, "00000000", "080140F9", True),
    (0xC501C0C, "00000000", "C80400B4", True),
    (0xC501C10, "00000000", "09889352", True),
    (0xC501C14, "00000000", "0900A472", True),
    (0xC501C18, "00000000", "7F03096B", True),
    (0xC501C1C, "00000000", "41040054", True),
    (0xC501C20, "00000000", "29B3FC90", True),
    (0xC501C24, "00000000", "291146F9", True),
    (0xC501C28, "00000000", "E90300B4", True),
    (0xC501C2C, "00000000", "29696F39", True),
    (0xC501C30, "00000000", "A9030035", True),
    (0xC501C34, "00000000", "C9B1FCF0", True),
    (0xC501C38, "00000000", "29C546F9", True),
    (0xC501C3C, "00000000", "490300B4", True),
    (0xC501C40, "00000000", "29D540F9", True),
    (0xC501C44, "00000000", "3F0113EB", True),
    (0xC501C48, "00000000", "E1020054", True),
    (0xC501C4C, "00000000", "A90740F9", True),
    (0xC501C50, "00000000", "EAD7F9F0", True),
    (0xC501C54, "00000000", "29010A4B", True),
    (0xC501C58, "00000000", "8A308A52", True),
    (0xC501C5C, "00000000", "4A2BA072", True),
    (0xC501C60, "00000000", "3F010A6B", True),
    (0xC501C64, "00000000", "A0000054", True),
    (0xC501C68, "00000000", "8A3B8A52", True),
    (0xC501C6C, "00000000", "4A2BA072", True),
    (0xC501C70, "00000000", "3F010A6B", True),
    (0xC501C74, "00000000", "81010054", True),
    (0xC501C78, "00000000", "A90340F9", True),
    (0xC501C7C, "00000000", "490100B4", True),
    (0xC501C80, "00000000", "EA0309AA", True),
    (0xC501C84, "00000000", "490540F9", True),
    (0xC501C88, "00000000", "EAD7F9F0", True),
    (0xC501C8C, "00000000", "29010A4B", True),
    (0xC501C90, "00000000", "8A379052", True),
    (0xC501C94, "00000000", "2A2BA072", True),
    (0xC501C98, "00000000", "3F010A6B", True),
    (0xC501C9C, "00000000", "41000054", True),
    (0xC501CA0, "00000000", "E8031FAA", True),
    (0xC501CA4, "00000000", "B085FA90", True),
    (0xC501CA8, "00000000", "10821591", True),
    (0xC501CAC, "00000000", "00021FD6", True),
    (0x1597264, "00000000", "507B05D0", True),
    (0x1597268, "00000000", "10223091", True),
    (0x159726C, "00000000", "00021FD6", True),
]
STARFRAG_PICK = [
    (0x15B555C, "080140F9", "4287FF17", True),
]

ORDER = [STARFRAG_PICK_CAVE, STARFRAG_PICK]
CAVES = {'FRAG': 0xC501C08, 'TRAMP': 0x1597264}
FRAG_ID = 0x20009C40
