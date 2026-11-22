"""drop3_gen.py: a fully taken per-player world item (owner-only enemy drop) is removed on EVERY game (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes drop3_live.py.
python drop3_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: drop3_notes.md.

REGISTRY: the cave range is allocated with Gen(dry=True), so cave_registry.md is NOT written (task rule: new files
only). The range is printed and listed in drop3_notes.md; the lead adds the row when baking:
  drop3_gen | DROP3 | <printed range> | removal 0x15A55C0: fully taken per-player item -> subtype 2 to every member
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

DROP3_CAVE = [  # FAR cave records
    (0xC503050, "00000000", "C9B1FCB0", True),
    (0xC503054, "00000000", "290547F9", True),
    (0xC503058, "00000000", "A90100B4", True),
    (0xC50305C, "00000000", "2A2549F9", True),
    (0xC503060, "00000000", "2B2949F9", True),
    (0xC503064, "00000000", "4AA10B91", True),
    (0xC503068, "00000000", "7F010AEB", True),
    (0xC50306C, "00000000", "03010054", True),
    (0xC503070, "00000000", "20410091", True),
    (0xC503074, "00000000", "080040F9", True),
    (0xC503078, "00000000", "082140F9", True),
    (0xC50307C, "00000000", "C1038052", True),
    (0xC503080, "00000000", "E2230091", True),
    (0xC503084, "00000000", "03018052", True),
    (0xC503088, "00000000", "00013FD6", True),
    (0xC50308C, "00000000", "1085FAD0", True),
    (0xC503090, "00000000", "10021E91", True),
    (0xC503094, "00000000", "00021FD6", True),
    (0x15A57CC, "00000000", "F07A05D0", True),
    (0x15A57D0, "00000000", "10420191", True),
    (0x15A57D4, "00000000", "00021FD6", True),
]
DROP3 = [
    (0x15A5754, "68015836", "C8035836", True),
    (0x15A575C, "28011837", "88031837", True),
]

ORDER = [DROP3_CAVE, DROP3]
CAVES = {'DROP3': 0xC503050, 'TRAMP': 0x15A57CC}
MIN_MEMBERS = 3
