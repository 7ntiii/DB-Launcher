"""pickup_gen.py: every world-item pick-up award from the host is added to the LOCAL picker's inventory in a LAN
match, through the game's own (offline) add branch 0x15B57FC (static generator). Reads nso/*.bin, patch_manager.cpp
and every *_live.py (through cave_lib). Writes pickup_live.py and claims its far range in cave_registry.md (owner
`pickup_gen`).
python pickup_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: pickup_notes.md (section 4 = this group).

REPLACES STARFRAG_PICK (same site 0x15B555C): apply one of the two, never both.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

PICKUP_ADD_CAVE = [  # FAR cave records
    (0xC501CB8, "00000000", "080140F9", True),
    (0xC501CBC, "00000000", "280500B4", True),
    (0xC501CC0, "00000000", "29B3FC90", True),
    (0xC501CC4, "00000000", "291146F9", True),
    (0xC501CC8, "00000000", "C90400B4", True),
    (0xC501CCC, "00000000", "29696F39", True),
    (0xC501CD0, "00000000", "89040035", True),
    (0xC501CD4, "00000000", "C9B1FCF0", True),
    (0xC501CD8, "00000000", "29C546F9", True),
    (0xC501CDC, "00000000", "290400B4", True),
    (0xC501CE0, "00000000", "29D540F9", True),
    (0xC501CE4, "00000000", "3F0113EB", True),
    (0xC501CE8, "00000000", "C1030054", True),
    (0xC501CEC, "00000000", "A90740F9", True),
    (0xC501CF0, "00000000", "EAD7F9F0", True),
    (0xC501CF4, "00000000", "29010A4B", True),
    (0xC501CF8, "00000000", "8A308A52", True),
    (0xC501CFC, "00000000", "4A2BA072", True),
    (0xC501D00, "00000000", "3F010A6B", True),
    (0xC501D04, "00000000", "A0000054", True),
    (0xC501D08, "00000000", "8A3B8A52", True),
    (0xC501D0C, "00000000", "4A2BA072", True),
    (0xC501D10, "00000000", "3F010A6B", True),
    (0xC501D14, "00000000", "61020054", True),
    (0xC501D18, "00000000", "AB0340F9", True),
    (0xC501D1C, "00000000", "2B0200B4", True),
    (0xC501D20, "00000000", "690540F9", True),
    (0xC501D24, "00000000", "EAD7F9F0", True),
    (0xC501D28, "00000000", "29010A4B", True),
    (0xC501D2C, "00000000", "8A379052", True),
    (0xC501D30, "00000000", "2A2BA072", True),
    (0xC501D34, "00000000", "3F010A6B", True),
    (0xC501D38, "00000000", "41010054", True),
    (0xC501D3C, "00000000", "6B0140F9", True),
    (0xC501D40, "00000000", "0B0100B4", True),
    (0xC501D44, "00000000", "6BA10AD1", True),
    (0xC501D48, "00000000", "690140B9", True),
    (0xC501D4C, "00000000", "2AE98852", True),
    (0xC501D50, "00000000", "2AC9AA72", True),
    (0xC501D54, "00000000", "3F010A6B", True),
    (0xC501D58, "00000000", "40000054", True),
    (0xC501D5C, "00000000", "E8031FAA", True),
    (0xC501D60, "00000000", "B085FA90", True),
    (0xC501D64, "00000000", "10821591", True),
    (0xC501D68, "00000000", "00021FD6", True),
    (0x1597270, "00000000", "507B05D0", True),
    (0x1597274, "00000000", "10E23291", True),
    (0x1597278, "00000000", "00021FD6", True),
]
PICKUP_ADD = [
    (0x15B555C, "080140F9", "4587FF17", True),
]

ORDER = [PICKUP_ADD_CAVE, PICKUP_ADD]
CAVES = {'ADD': 0xC501CB8, 'TRAMP': 0x1597270}
EXCLUSIVE_WITH = ['STARFRAG_PICK']
