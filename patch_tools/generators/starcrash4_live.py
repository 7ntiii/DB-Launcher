"""starcrash4_gen.py: STARCRASH_DEFER game side that DROPS pending notices outside UpdatePhase (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes starcrash4_live.py.
python starcrash4_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: cosmetic_notes.md section 2. Needs the BUILT-IN STARCRASH_DEFER (v1, starcrash2_live.py): SC_UI and
SC_CNT {u32 REQ, u32 DONE} at 0xC50F30C stay as they are; only the game side changes.

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed row.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

STARCRASH4_CAVE = [  # FAR cave records
    (0xC502970, "00000000", "690000B0", True),
    (0xC502974, "00000000", "2A0D43B9", True),
    (0xC502978, "00000000", "2B1143B9", True),
    (0xC50297C, "00000000", "5F010B6B", True),
    (0xC502980, "00000000", "E0010054", True),
    (0xC502984, "00000000", "C8B1FCD0", True),
    (0xC502988, "00000000", "08FD46F9", True),
    (0xC50298C, "00000000", "E80000B4", True),
    (0xC502990, "00000000", "0CD159F9", True),
    (0xC502994, "00000000", "AC0000B4", True),
    (0xC502998, "00000000", "0C5140B9", True),
    (0xC50299C, "00000000", "9F190071", True),
    (0xC5029A0, "00000000", "41000054", True),
    (0xC5029A4, "00000000", "6A050011", True),
    (0xC5029A8, "00000000", "2A1103B9", True),
    (0xC5029AC, "00000000", "81000054", True),
    (0xC5029B0, "00000000", "5060FAD0", True),
    (0xC5029B4, "00000000", "10E20691", True),
    (0xC5029B8, "00000000", "00023FD6", True),
    (0xC5029BC, "00000000", "E00313AA", True),
    (0xC5029C0, "00000000", "5060FAB0", True),
    (0xC5029C4, "00000000", "10320F91", True),
    (0xC5029C8, "00000000", "00021FD6", True),
]
STARCRASH4_HOOK = [
    (0x1100090, "00000000", "10A005D0", True),
    (0x1100094, "00000000", "10C22591", True),
    (0x1100098, "00000000", "00021FD6", True),
]

ORDER = [STARCRASH4_CAVE, STARCRASH4_HOOK]
CAVES = {'SC_GAME4': 0xC502970, 'SC_CNT': 0xC50F30C, 'PAD_GM': 0x1100090}
REQUIRES = ['STARCRASH_DEFER (built in)']
EXCLUSIVE_WITH = {'STARCRASH4_HOOK': ['TE_COMMEND_UI', 'STARCRASH_DEFER_V2']}
