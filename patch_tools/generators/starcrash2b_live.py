"""starcrash2_gen.py: move the TextEffect commendation notice push off the UI script thread (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes starcrash2_live.py.
python starcrash2_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: starcrash3_notes.md. Alternative to TE_COMMEND_UI (starcrash_live.py; same word 0x12A8C08: never both).

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

STARCRASH_DEFER_CAVE_V2 = [  # FAR cave records
    (0xC502368, "00000000", "09B3FCF0", True),
    (0xC50236C, "00000000", "291146F9", True),
    (0xC502370, "00000000", "490100B4", True),
    (0xC502374, "00000000", "29696F39", True),
    (0xC502378, "00000000", "09010035", True),
    (0xC50237C, "00000000", "690000B0", True),
    (0xC502380, "00000000", "2A0D43B9", True),
    (0xC502384, "00000000", "4A050011", True),
    (0xC502388, "00000000", "2A0D03B9", True),
    (0xC50238C, "00000000", "306DFAD0", True),
    (0xC502390, "00000000", "10323091", True),
    (0xC502394, "00000000", "00021FD6", True),
    (0xC502398, "00000000", "5060FAD0", True),
    (0xC50239C, "00000000", "10E20691", True),
    (0xC5023A0, "00000000", "00023FD6", True),
    (0xC5023A4, "00000000", "306DFAD0", True),
    (0xC5023A8, "00000000", "10323091", True),
    (0xC5023AC, "00000000", "00021FD6", True),
    (0xC5023B8, "00000000", "690000B0", True),
    (0xC5023BC, "00000000", "2A0D43B9", True),
    (0xC5023C0, "00000000", "2B1143B9", True),
    (0xC5023C4, "00000000", "5F010B6B", True),
    (0xC5023C8, "00000000", "C0010054", True),
    (0xC5023CC, "00000000", "C8B1FCD0", True),
    (0xC5023D0, "00000000", "08FD46F9", True),
    (0xC5023D4, "00000000", "680100B4", True),
    (0xC5023D8, "00000000", "0C5140B9", True),
    (0xC5023DC, "00000000", "9F190071", True),
    (0xC5023E0, "00000000", "01010054", True),
    (0xC5023E4, "00000000", "0CD159F9", True),
    (0xC5023E8, "00000000", "CC0000B4", True),
    (0xC5023EC, "00000000", "6B050011", True),
    (0xC5023F0, "00000000", "2B1103B9", True),
    (0xC5023F4, "00000000", "5060FAD0", True),
    (0xC5023F8, "00000000", "10E20691", True),
    (0xC5023FC, "00000000", "00023FD6", True),
    (0xC502400, "00000000", "E00313AA", True),
    (0xC502404, "00000000", "5060FAB0", True),
    (0xC502408, "00000000", "10320F91", True),
    (0xC50240C, "00000000", "00021FD6", True),
    (0x12A0894, "00000000", "109305D0", True),
    (0x12A0898, "00000000", "10A20D91", True),
    (0x12A089C, "00000000", "00021FD6", True),
    (0x1100090, "00000000", "10A005D0", True),
    (0x1100094, "00000000", "10E20E91", True),
    (0x1100098, "00000000", "00021FD6", True),
]
STARCRASH_DEFER_V2 = [
    (0x12A8C08, "6C8DF997", "23DFFF17", True),
    (0x110B3C8, "E00313AA", "32D3FF17", True),
]

ORDER = [STARCRASH_DEFER_CAVE_V2, STARCRASH_DEFER_V2]
CAVES = {'SC_UI': 0xC502368, 'SC_GAME': 0xC5023B8, 'SC_CNT': 0xC50F30C, 'PAD_UI': 0x12A0894, 'PAD_GM': 0x1100090}
EXCLUSIVE_WITH = {'STARCRASH_DEFER_V2': ['TE_COMMEND_UI', 'STARCRASH_DEFER']}
