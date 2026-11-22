"""treasure_gen.py: map treasures made by the LAN host, and blood crystals awarded on the killer's own game (static
generator). Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. No cave, no registry claim.
python treasure_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: treasure_notes.md.

Groups: TREASURE_HOST (3 words), CRYSTAL_LOCAL (1 word). Notes treasure_notes.md.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

TREASURE_HOST = [
    (0xC2D04C, "C8790290", "E8E701B0", True),
    (0xC2D050, "081146F9", "08617F39", True),
    (0xC2D054, "08696F39", "08010052", True),
]
CRYSTAL_LOCAL = [
    (0x15B0528, "28010034", "1F2003D5", True),
]

ORDER = [TREASURE_HOST, CRYSTAL_LOCAL]
EXCLUSIVE_WITH = {'TREASURE_HOST': ['STARFRAG_V2']}

# 2026-11-15: CRYSTAL_LOCAL is WITHDRAWN (pickup2_notes.md 3): do not apply it. TREASURE_HOST is unaffected.
# 2026-11-15 batch39_notes.md 2: EXCLUSIVE_WITH STARFRAG_V2 is WITHDRAWN - 0xC2CEE0 returns early (0x15A57E0, LAN) when a networked item is already linked to the asset, so both together cannot duplicate; keep both.
