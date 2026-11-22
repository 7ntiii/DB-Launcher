"""pickup_gen2.py: PICKUP_ADD v2 = PICKUP_ADD plus the host's local take of its own Power drop (HOST_TAKE,
host_take_gen.py): 0x15A5020 called from 0x15A4CCC (LR 0x15A4CD0) is also added, without the gift-marker test (that
frame is not the reader's). Static generator; allocated with Gen(dry=True), cave_registry.md NOT written (the lead adds
the printed row). Writes pickup2_live.py.
python pickup_gen2.py [--dry]      (from diag/net)
Notes: pickup4_notes.md section 3 (v1: pickup_notes.md section 4).
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

PICKUP_ADD2_CAVE = [  # FAR cave records
    (0xC502278, "00000000", "080140F9", True),
    (0xC50227C, "00000000", "A80500B4", True),
    (0xC502280, "00000000", "09B3FCF0", True),
    (0xC502284, "00000000", "291146F9", True),
    (0xC502288, "00000000", "490500B4", True),
    (0xC50228C, "00000000", "29696F39", True),
    (0xC502290, "00000000", "09050035", True),
    (0xC502294, "00000000", "C9B1FCD0", True),
    (0xC502298, "00000000", "29C546F9", True),
    (0xC50229C, "00000000", "A90400B4", True),
    (0xC5022A0, "00000000", "29D540F9", True),
    (0xC5022A4, "00000000", "3F0113EB", True),
    (0xC5022A8, "00000000", "41040054", True),
    (0xC5022AC, "00000000", "A90740F9", True),
    (0xC5022B0, "00000000", "EAD7F9D0", True),
    (0xC5022B4, "00000000", "29010A4B", True),
    (0xC5022B8, "00000000", "8A308A52", True),
    (0xC5022BC, "00000000", "4A2BA072", True),
    (0xC5022C0, "00000000", "3F010A6B", True),
    (0xC5022C4, "00000000", "A0000054", True),
    (0xC5022C8, "00000000", "8A3B8A52", True),
    (0xC5022CC, "00000000", "4A2BA072", True),
    (0xC5022D0, "00000000", "3F010A6B", True),
    (0xC5022D4, "00000000", "E1020054", True),
    (0xC5022D8, "00000000", "AB0340F9", True),
    (0xC5022DC, "00000000", "AB0200B4", True),
    (0xC5022E0, "00000000", "690540F9", True),
    (0xC5022E4, "00000000", "EAD7F9D0", True),
    (0xC5022E8, "00000000", "29010A4B", True),
    (0xC5022EC, "00000000", "0A9A8952", True),
    (0xC5022F0, "00000000", "4A2BA072", True),
    (0xC5022F4, "00000000", "3F010A6B", True),
    (0xC5022F8, "00000000", "A0010054", True),
    (0xC5022FC, "00000000", "8A379052", True),
    (0xC502300, "00000000", "2A2BA072", True),
    (0xC502304, "00000000", "3F010A6B", True),
    (0xC502308, "00000000", "41010054", True),
    (0xC50230C, "00000000", "6B0140F9", True),
    (0xC502310, "00000000", "0B0100B4", True),
    (0xC502314, "00000000", "6BA10AD1", True),
    (0xC502318, "00000000", "690140B9", True),
    (0xC50231C, "00000000", "2AE98852", True),
    (0xC502320, "00000000", "2AC9AA72", True),
    (0xC502324, "00000000", "3F010A6B", True),
    (0xC502328, "00000000", "40000054", True),
    (0xC50232C, "00000000", "E8031FAA", True),
    (0xC502330, "00000000", "9085FAF0", True),
    (0xC502334, "00000000", "10821591", True),
    (0xC502338, "00000000", "00021FD6", True),
    (0x15357A8, "00000000", "707E05B0", True),
    (0x15357AC, "00000000", "10E20991", True),
    (0x15357B0, "00000000", "00021FD6", True),
]
PICKUP_ADD2 = [
    (0x15B555C, "080140F9", "9300FE17", True),
]

ORDER = [PICKUP_ADD2_CAVE, PICKUP_ADD2]
CAVES = {'ADD2': 0xC502278, 'TRAMP': 0x15357A8}
EXCLUSIVE_WITH = {'PICKUP_ADD2': ['PICKUP_ADD', 'STARFRAG_PICK']}
