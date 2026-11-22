"""needdata_gen.py: NEEDDATA, the game-thread half of v4.37 (b_loadhang_notes.md 5). Static generator,
allocated with Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows). Writes needdata_live.py.
python needdata_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

NEEDDATA_CAVE = [  # FAR cave records
    (0xC504018, "00000000", "73020034", True),
    (0xC50401C, "00000000", "490000F0", True),
    (0xC504020, "00000000", "29012391", True),
    (0xC504024, "00000000", "2A0140B9", True),
    (0xC504028, "00000000", "8A010034", True),
    (0xC50402C, "00000000", "2A0540F9", True),
    (0xC504030, "00000000", "EA7F03F9", True),
    (0xC504034, "00000000", "2A0540B9", True),
    (0xC504038, "00000000", "4A050011", True),
    (0xC50403C, "00000000", "2A0500B9", True),
    (0xC504040, "00000000", "3F0100B9", True),
    (0xC504044, "00000000", "E1E31B91", True),
    (0xC504048, "00000000", "E00318AA", True),
    (0xC50404C, "00000000", "B0BEFAB0", True),
    (0xC504050, "00000000", "10223691", True),
    (0xC504054, "00000000", "00023FD6", True),
    (0xC504058, "00000000", "D07EFAD0", True),
    (0xC50405C, "00000000", "10E22291", True),
    (0xC504060, "00000000", "00021FD6", True),
    (0xC504064, "00000000", "D07EFAD0", True),
    (0xC504068, "00000000", "10222591", True),
    (0xC50406C, "00000000", "00021FD6", True),
    (0x145F330, "00000000", "308505B0", True),
    (0x145F334, "00000000", "10620091", True),
    (0x145F338, "00000000", "00021FD6", True),
]
NEEDDATA = [
    (0x14DE8B4, "B3040034", "9F02FE17", True),
]

ORDER = [NEEDDATA_CAVE, NEEDDATA]
CAVES = {'NEEDDATA': 0xC504018, 'NDBOX': 0xC50F8C0, 'TRAMP': 0x145F330}
