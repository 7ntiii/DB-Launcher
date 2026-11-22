"""treasure_gen2.py: TREASURE_HOST v2, map treasures made by the LAN host, with two guards (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes treasure2_live.py.
python treasure_gen2.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: batch39b_notes.md section 1 (v1: treasure_gen.py / treasure_notes.md).

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed row:
  treasure_gen2 | THOST2 | <printed range> | TREASURE_HOST v2 gate (batch39b 1)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

TREASURE_HOST2_CAVE = [  # FAR cave records
    (0xC501E78, "00000000", "30B3FC90", True),
    (0xC501E7C, "00000000", "101246F9", True),
    (0xC501E80, "00000000", "B00200B4", True),
    (0xC501E84, "00000000", "086A6F39", True),
    (0xC501E88, "00000000", "E8010035", True),
    (0xC501E8C, "00000000", "5021FCB0", True),
    (0xC501E90, "00000000", "08627F39", True),
    (0xC501E94, "00000000", "08020035", True),
    (0xC501E98, "00000000", "B0B2FCD0", True),
    (0xC501E9C, "00000000", "105E47F9", True),
    (0xC501EA0, "00000000", "B00100B4", True),
    (0xC501EA4, "00000000", "111640F9", True),
    (0xC501EA8, "00000000", "710000B5", True),
    (0xC501EAC, "00000000", "111240F9", True),
    (0xC501EB0, "00000000", "310100B4", True),
    (0xC501EB4, "00000000", "28D240B9", True),
    (0xC501EB8, "00000000", "E8000034", True),
    (0xC501EBC, "00000000", "1F050031", True),
    (0xC501EC0, "00000000", "A0000054", True),
    (0xC501EC4, "00000000", "28008052", True),
    (0xC501EC8, "00000000", "7039FA90", True),
    (0xC501ECC, "00000000", "10620191", True),
    (0xC501ED0, "00000000", "00021FD6", True),
    (0xC501ED4, "00000000", "08008052", True),
    (0xC501ED8, "00000000", "7039FA90", True),
    (0xC501EDC, "00000000", "10620191", True),
    (0xC501EE0, "00000000", "00021FD6", True),
    (0xC07F64, "00000000", "D0C705D0", True),
    (0xC07F68, "00000000", "10E23991", True),
    (0xC07F6C, "00000000", "00021FD6", True),
]
TREASURE_HOST2 = [
    (0xC2D04C, "C8790290", "C66BFF17", True),
]

ORDER = [TREASURE_HOST2_CAVE, TREASURE_HOST2]
CAVES = {'THOST2': 0xC501E78, 'TRAMP': 0xC07F64}
EXCLUSIVE_WITH = {'TREASURE_HOST2': ['TREASURE_HOST']}
