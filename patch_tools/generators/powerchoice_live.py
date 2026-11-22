"""powerchoice_gen.py: in a LAN match, do not open the "Select what to receive" dialog for Powers of Blood, because
its OK can give nothing there; the player keeps the Power of his own per-player drop (auto-take + PICKUP_ADD) and sees
only its pick-up popup (static generator, SAFE PARTIAL of powerchoice_notes.md). Reads nso/*.bin, patch_manager.cpp
and every *_live.py (through cave_lib). Writes powerchoice_live.py and claims its far range in cave_registry.md
(owner `powerchoice_gen`).
python powerchoice_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: powerchoice_notes.md.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

POWERCHOICE_CAVE = [  # FAR cave records
    (0xC502410, "00000000", "E8010054", True),
    (0xC502414, "00000000", "A9B2FCB0", True),
    (0xC502418, "00000000", "294947F9", True),
    (0xC50241C, "00000000", "E90100B4", True),
    (0xC502420, "00000000", "09B3FCF0", True),
    (0xC502424, "00000000", "291146F9", True),
    (0xC502428, "00000000", "890100B4", True),
    (0xC50242C, "00000000", "29696F39", True),
    (0xC502430, "00000000", "49010035", True),
    (0xC502434, "00000000", "D8000035", True),
    (0xC502438, "00000000", "08010034", True),
    (0xC50243C, "00000000", "E93E40B9", True),
    (0xC502440, "00000000", "297D1C53", True),
    (0xC502444, "00000000", "3F1D0071", True),
    (0xC502448, "00000000", "81000054", True),
    (0xC50244C, "00000000", "1085FAD0", True),
    (0xC502450, "00000000", "10123F91", True),
    (0xC502454, "00000000", "00021FD6", True),
    (0xC502458, "00000000", "1085FAD0", True),
    (0xC50245C, "00000000", "10A23991", True),
    (0xC502460, "00000000", "00021FD6", True),
    (0x15A4DD0, "00000000", "F07A05D0", True),
    (0x15A4DD4, "00000000", "10421091", True),
    (0x15A4DD8, "00000000", "00021FD6", True),
]
POWERCHOICE = [
    (0x15A4E64, "080B0054", "DBFFFF17", True),
]

ORDER = [POWERCHOICE_CAVE, POWERCHOICE]
CAVES = {'HIDE': 0xC502410, 'TRAMP': 0x15A4DD0}
