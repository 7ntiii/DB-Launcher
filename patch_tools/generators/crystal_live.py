"""crystal_gen.py: a guest's Bloodsac kill makes the skill-enhancement offer on the guest's own game (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes crystal_live.py.
python crystal_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: batch39b_notes.md section 2. Replaces the withdrawn CRYSTAL_LOCAL (treasure_live.py; same word).

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed row:
  crystal_gen | CGUEST | <printed range> | guest Bloodsac offer (batch39b 2)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

CRYSTAL_GUEST_CAVE = [  # FAR cave records
    (0xC501EE4, "00000000", "88000034", True),
    (0xC501EE8, "00000000", "7085FAF0", True),
    (0xC501EEC, "00000000", "10B21491", True),
    (0xC501EF0, "00000000", "00021FD6", True),
    (0xC501EF4, "00000000", "5021FCB0", True),
    (0xC501EF8, "00000000", "10627F39", True),
    (0xC501EFC, "00000000", "70010034", True),
    (0xC501F00, "00000000", "E007442D", True),
    (0xC501F04, "00000000", "837E4092", True),
    (0xC501F08, "00000000", "E22B40BD", True),
    (0xC501F0C, "00000000", "E1630091", True),
    (0xC501F10, "00000000", "E00313AA", True),
    (0xC501F14, "00000000", "FF0F00F9", True),
    (0xC501F18, "00000000", "E23F40B9", True),
    (0xC501F1C, "00000000", "9085FAD0", True),
    (0xC501F20, "00000000", "10920E91", True),
    (0xC501F24, "00000000", "00023FD6", True),
    (0xC501F28, "00000000", "7085FAF0", True),
    (0xC501F2C, "00000000", "10321591", True),
    (0xC501F30, "00000000", "00021FD6", True),
    (0x15A1AEC, "00000000", "107B0590", True),
    (0x15A1AF0, "00000000", "10923B91", True),
    (0x15A1AF4, "00000000", "00021FD6", True),
]
CRYSTAL_GUEST = [
    (0x15B0528, "28010034", "71C5FF17", True),
]

ORDER = [CRYSTAL_GUEST_CAVE, CRYSTAL_GUEST]
CAVES = {'CGUEST': 0xC501EE4, 'TRAMP': 0x15A1AEC}
EXCLUSIVE_WITH = {'CRYSTAL_GUEST': ['CRYSTAL_LOCAL']}
