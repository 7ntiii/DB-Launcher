"""loveaccept_gen.py: Love Ephemeral "Accept flowers" prompt for the bearer's REMOTE chr (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes loveaccept_live.py.
python loveaccept_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: sigil15_notes.md section 4.

REGISTRY: the cave range is allocated with Gen(dry=True), so cave_registry.md is NOT written (task rule: new files
only). The range is printed and listed in sigil15_notes.md section 4; the lead adds the rows when baking:
  loveaccept_gen | LOVEACCEPT | <printed range> | Love: accept-prompt key fallback on the bearer's offering bit
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

LOVEACCEPT_CAVE = [  # FAR cave records
    (0xC5029CC, "00000000", "28010035", True),
    (0xC5029D0, "00000000", "690640F9", True),
    (0xC5029D4, "00000000", "490100B4", True),
    (0xC5029D8, "00000000", "293952F9", True),
    (0xC5029DC, "00000000", "090100B4", True),
    (0xC5029E0, "00000000", "290140F9", True),
    (0xC5029E4, "00000000", "C90000B4", True),
    (0xC5029E8, "00000000", "29114539", True),
    (0xC5029EC, "00000000", "89001036", True),
    (0xC5029F0, "00000000", "30A6FAF0", True),
    (0xC5029F4, "00000000", "10623691", True),
    (0xC5029F8, "00000000", "00021FD6", True),
    (0xC5029FC, "00000000", "30A6FAF0", True),
    (0xC502A00, "00000000", "10922D91", True),
    (0xC502A04, "00000000", "00021FD6", True),
    (0x19C080C, "00000000", "105A05D0", True),
    (0x19C0810, "00000000", "10322791", True),
    (0x19C0814, "00000000", "00021FD6", True),
]
LOVEACCEPT = [
    (0x19C9D94, "88EEFF34", "9EDAFF17", True),
]

ORDER = [LOVEACCEPT_CAVE, LOVEACCEPT]
CAVES = {'LOVEACCEPT': 0xC5029CC, 'TRAMP': 0x19C080C}
