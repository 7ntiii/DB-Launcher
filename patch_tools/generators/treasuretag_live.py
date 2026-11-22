"""treasuretag_gen.py: a CTAG-style player tag for map-treasure record ids made by a NEW host (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes treasuretag_live.py.
python treasuretag_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: players8b_notes.md P3, audit_v398_notes.md section 2.

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Why: a world-item record id is (counter << 5) | kind bits, from a per-game counter. Only the host creates map
treasures (TREASURE_HOST2 + ITEMS I3), so a guest's counters never move. After a host hand-over the new host
counts from its own (low) counters and can repeat ids of items the old host made that are still in the world.
Fix: when the id is formed in the three creators the treasure step 0x15AB6D0 uses (lot kind < 2: 0x15AB840,
kind 2: 0x15AC2A8 -> 0x15B0B40, kind 3: 0x15AC42C), put the own player number into bits 27..30 (as CTAG does for
Power drops) - only online, only on the host (role byte 0) and only when the own number is 2..15.
Player 1 (the first host) never tags: while it stays host nothing changes. CTAG's own Power-drop tag (same
bits, same value) is written after this one, so those ids are unchanged too.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

TREASURE_TAG_CAVE = [  # FAR cave records
    (0xC502A0C, "00000000", "AB150B2A", True),
    (0xC502A10, "00000000", "10B3FCF0", True),
    (0xC502A14, "00000000", "101246F9", True),
    (0xC502A18, "00000000", "300200B4", True),
    (0xC502A1C, "00000000", "116A6F39", True),
    (0xC502A20, "00000000", "F1010035", True),
    (0xC502A24, "00000000", "5021FC90", True),
    (0xC502A28, "00000000", "11627F39", True),
    (0xC502A2C, "00000000", "91010035", True),
    (0xC502A30, "00000000", "B0B2FCB0", True),
    (0xC502A34, "00000000", "105E47F9", True),
    (0xC502A38, "00000000", "300100B4", True),
    (0xC502A3C, "00000000", "101240F9", True),
    (0xC502A40, "00000000", "F00000B4", True),
    (0xC502A44, "00000000", "11D240B9", True),
    (0xC502A48, "00000000", "306E1C12", True),
    (0xC502A4C, "00000000", "90000035", True),
    (0xC502A50, "00000000", "307E0153", True),
    (0xC502A54, "00000000", "50000034", True),
    (0xC502A58, "00000000", "2B0E0533", True),
    (0xC502A5C, "00000000", "5085FAB0", True),
    (0xC502A60, "00000000", "10E23091", True),
    (0xC502A64, "00000000", "00021FD6", True),
    (0xC502A68, "00000000", "08150C2A", True),
    (0xC502A6C, "00000000", "10B3FCF0", True),
    (0xC502A70, "00000000", "101246F9", True),
    (0xC502A74, "00000000", "300200B4", True),
    (0xC502A78, "00000000", "116A6F39", True),
    (0xC502A7C, "00000000", "F1010035", True),
    (0xC502A80, "00000000", "5021FC90", True),
    (0xC502A84, "00000000", "11627F39", True),
    (0xC502A88, "00000000", "91010035", True),
    (0xC502A8C, "00000000", "B0B2FCB0", True),
    (0xC502A90, "00000000", "105E47F9", True),
    (0xC502A94, "00000000", "300100B4", True),
    (0xC502A98, "00000000", "101240F9", True),
    (0xC502A9C, "00000000", "F00000B4", True),
    (0xC502AA0, "00000000", "11D240B9", True),
    (0xC502AA4, "00000000", "306E1C12", True),
    (0xC502AA8, "00000000", "90000035", True),
    (0xC502AAC, "00000000", "307E0153", True),
    (0xC502AB0, "00000000", "50000034", True),
    (0xC502AB4, "00000000", "280E0533", True),
    (0xC502AB8, "00000000", "5085FAD0", True),
    (0xC502ABC, "00000000", "10F21591", True),
    (0xC502AC0, "00000000", "00021FD6", True),
    (0xC502AC4, "00000000", "08150B2A", True),
    (0xC502AC8, "00000000", "10B3FCF0", True),
    (0xC502ACC, "00000000", "101246F9", True),
    (0xC502AD0, "00000000", "300200B4", True),
    (0xC502AD4, "00000000", "116A6F39", True),
    (0xC502AD8, "00000000", "F1010035", True),
    (0xC502ADC, "00000000", "5021FC90", True),
    (0xC502AE0, "00000000", "11627F39", True),
    (0xC502AE4, "00000000", "91010035", True),
    (0xC502AE8, "00000000", "B0B2FCB0", True),
    (0xC502AEC, "00000000", "105E47F9", True),
    (0xC502AF0, "00000000", "300100B4", True),
    (0xC502AF4, "00000000", "101240F9", True),
    (0xC502AF8, "00000000", "F00000B4", True),
    (0xC502AFC, "00000000", "11D240B9", True),
    (0xC502B00, "00000000", "306E1C12", True),
    (0xC502B04, "00000000", "90000035", True),
    (0xC502B08, "00000000", "307E0153", True),
    (0xC502B0C, "00000000", "50000034", True),
    (0xC502B10, "00000000", "280E0533", True),
    (0xC502B14, "00000000", "7085FAD0", True),
    (0xC502B18, "00000000", "10223691", True),
    (0xC502B1C, "00000000", "00021FD6", True),
    (0x156C8C8, "00000000", "B07C05D0", True),
    (0x156C8CC, "00000000", "10322891", True),
    (0x156C8D0, "00000000", "00021FD6", True),
    (0x156CBAC, "00000000", "B07C05D0", True),
    (0x156CBB0, "00000000", "10A22991", True),
    (0x156CBB4, "00000000", "00021FD6", True),
    (0x15717CC, "00000000", "907C05B0", True),
    (0x15717D0, "00000000", "10122B91", True),
    (0x15717D4, "00000000", "00021FD6", True),
]
TREASURE_TAG = [
    (0x15ABC34, "AB150B2A", "2503FF17", True),
    (0x15AC578, "08150C2A", "8D01FF17", True),
    (0x15B0D84, "08150B2A", "9202FF17", True),
]

ORDER = [TREASURE_TAG_CAVE, TREASURE_TAG]
SITES = ['0x15abc34', '0x15ac578', '0x15b0d84']
PADS = ['0x156c8c8', '0x156cbac', '0x15717cc']
