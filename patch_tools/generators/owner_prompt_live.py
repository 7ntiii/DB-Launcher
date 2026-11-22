"""owner_prompt_gen.py: no "Pick up" prompt for a per-player world item the local player may not take (static
generator). Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes owner_prompt_live.py.
python owner_prompt_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: batch39_notes.md section 3.

REGISTRY: the cave range is allocated with Gen(dry=True), so cave_registry.md is NOT written (task rule: new files
only). The range is printed and listed in batch39_notes.md; the lead adds the row when baking:
  owner_prompt_gen | PROMPT | <printed range> | prompt filter for per-player items (batch39 3)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

OWNER_PROMPT_CAVE = [  # FAR cave records
    (0xC501D98, "00000000", "FD7BBEA9", True),
    (0xC501D9C, "00000000", "FD030091", True),
    (0xC501DA0, "00000000", "E00B00F9", True),
    (0xC501DA4, "00000000", "1085FA90", True),
    (0xC501DA8, "00000000", "10823491", True),
    (0xC501DAC, "00000000", "00023FD6", True),
    (0xC501DB0, "00000000", "20050036", True),
    (0xC501DB4, "00000000", "E90B40F9", True),
    (0xC501DB8, "00000000", "AAB2FCD0", True),
    (0xC501DBC, "00000000", "4A4947F9", True),
    (0xC501DC0, "00000000", "8A0400B4", True),
    (0xC501DC4, "00000000", "2AB3FC90", True),
    (0xC501DC8, "00000000", "4A1146F9", True),
    (0xC501DCC, "00000000", "2A0400B4", True),
    (0xC501DD0, "00000000", "4A696F39", True),
    (0xC501DD4, "00000000", "EA030035", True),
    (0xC501DD8, "00000000", "2A014039", True),
    (0xC501DDC, "00000000", "AA032036", True),
    (0xC501DE0, "00000000", "2AB14439", True),
    (0xC501DE4, "00000000", "5F150071", True),
    (0xC501DE8, "00000000", "48030054", True),
    (0xC501DEC, "00000000", "2B008052", True),
    (0xC501DF0, "00000000", "6B21CA1A", True),
    (0xC501DF4, "00000000", "CC068052", True),
    (0xC501DF8, "00000000", "7F010C6A", True),
    (0xC501DFC, "00000000", "A0020054", True),
    (0xC501E00, "00000000", "CAB1FCF0", True),
    (0xC501E04, "00000000", "4AC546F9", True),
    (0xC501E08, "00000000", "4A0200B4", True),
    (0xC501E0C, "00000000", "4AD540F9", True),
    (0xC501E10, "00000000", "0A0200B4", True),
    (0xC501E14, "00000000", "4A1140F9", True),
    (0xC501E18, "00000000", "CA0100B4", True),
    (0xC501E1C, "00000000", "4AE940F9", True),
    (0xC501E20, "00000000", "8A0100B4", True),
    (0xC501E24, "00000000", "4A114439", True),
    (0xC501E28, "00000000", "5F2D0071", True),
    (0xC501E2C, "00000000", "28010054", True),
    (0xC501E30, "00000000", "2B0080D2", True),
    (0xC501E34, "00000000", "7121CA9A", True),
    (0xC501E38, "00000000", "2C2D41F9", True),
    (0xC501E3C, "00000000", "3F020CEA", True),
    (0xC501E40, "00000000", "E1000054", True),
    (0xC501E44, "00000000", "2C3141F9", True),
    (0xC501E48, "00000000", "3F020CEA", True),
    (0xC501E4C, "00000000", "80000054", True),
    (0xC501E50, "00000000", "20008052", True),
    (0xC501E54, "00000000", "FD7BC2A8", True),
    (0xC501E58, "00000000", "C0035FD6", True),
    (0xC501E5C, "00000000", "00008052", True),
    (0xC501E60, "00000000", "FDFFFF17", True),
    (0x15A18F0, "00000000", "107B0590", True),
    (0x15A18F4, "00000000", "10623691", True),
    (0x15A18F8, "00000000", "00021FD6", True),
]
OWNER_PROMPT = [
    (0x15A5CF0, "0CF0FF97", "00EFFF97", True),
    (0x15A5E6C, "ADEFFF97", "A1EEFF97", True),
]

ORDER = [OWNER_PROMPT_CAVE, OWNER_PROMPT]
CAVES = {'PROMPT': 0xC501D98, 'TRAMP': 0x15A18F0}
