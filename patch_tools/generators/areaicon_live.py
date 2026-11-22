"""areaicon_gen.py: guests get the host's area-icon list MS+0x538 (icons4_notes.md). Static generator: reads
nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes areaicon_live.py.
python areaicon_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows (proposal).

Why [V]:
- The HUD's area-name icon lookup 0x1481160 (callers 0x12E95D4 / 0x12E9A90 in the HUD build 0x12E32E0, and
  0x13CEE84) reads [[par+0x2D8]+0x538 .. +0x540]: 8-byte entries {u32 area id, u32 kind}, kind 0..9 -> icon
  0xBB95..0xBBBD. Match 3 round 2: host 72 bytes (9 entries), guest none.
- Its only writers: the constructor (zero), the teardown 0x11103E0 (frees begin through [MS+0x550] vt+0x70), the
  host-only simulation body, and 0x1111260, the 0x6A reader's section (0x1110820 -> 0x11109DC): end = begin,
  reserve 0x1122FC0(&MS+0x538, n), then one entry per record. Guests never get 0x6A, so their list stays empty.
- The list must be the game's own allocation (the teardown frees it): a buffer of ours would be freed by the
  game's allocator. So the cave refills it with the game's own reserve, as 0x1111260 does.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

AREA_ICON_CAVE = [  # FAR cave records
    (0xC5035D8, "00000000", "E07BBEA9", True),
    (0xC5035DC, "00000000", "F55B01A9", True),
    (0xC5035E0, "00000000", "75000090", True),
    (0xC5035E4, "00000000", "B5C20C91", True),
    (0xC5035E8, "00000000", "A80240B9", True),
    (0xC5035EC, "00000000", "48030034", True),
    (0xC5035F0, "00000000", "68AA42F9", True),
    (0xC5035F4, "00000000", "E80200B4", True),
    (0xC5035F8, "00000000", "B60640B9", True),
    (0xC5035FC, "00000000", "DFE20071", True),
    (0xC503600, "00000000", "88020054", True),
    (0xC503604, "00000000", "689E42F9", True),
    (0xC503608, "00000000", "68A202F9", True),
    (0xC50360C, "00000000", "36020034", True),
    (0xC503610, "00000000", "60E21491", True),
    (0xC503614, "00000000", "E103162A", True),
    (0xC503618, "00000000", "F060FAF0", True),
    (0xC50361C, "00000000", "10023F91", True),
    (0xC503620, "00000000", "00023FD6", True),
    (0xC503624, "00000000", "6A9E42F9", True),
    (0xC503628, "00000000", "4A0100B4", True),
    (0xC50362C, "00000000", "A9220091", True),
    (0xC503630, "00000000", "EB03162A", True),
    (0xC503634, "00000000", "2C0140F9", True),
    (0xC503638, "00000000", "4C0100F9", True),
    (0xC50363C, "00000000", "29210091", True),
    (0xC503640, "00000000", "4A210091", True),
    (0xC503644, "00000000", "6B050051", True),
    (0xC503648, "00000000", "6BFFFF35", True),
    (0xC50364C, "00000000", "6AA202F9", True),
    (0xC503650, "00000000", "BF0200B9", True),
    (0xC503654, "00000000", "F55B41A9", True),
    (0xC503658, "00000000", "E07BC2A8", True),
    (0xC50365C, "00000000", "086852B9", True),
    (0xC503660, "00000000", "7060FAB0", True),
    (0xC503664, "00000000", "10722191", True),
    (0xC503668, "00000000", "00021FD6", True),
    (0x1090AC8, "00000000", "90A305F0", True),
    (0x1090ACC, "00000000", "10621791", True),
    (0x1090AD0, "00000000", "00021FD6", True),
]
AREA_ICON_HOOK = [
    (0x1110858, "086852B9", "9C00FE17", True),
]

ORDER = [AREA_ICON_CAVE, AREA_ICON_HOOK]
CAVES = {'ICON': 0xC5035D8}
BOX = 0xC50F330
SITE = 0x1110858
PAD = 0x1090AC8
HOOK_WORD = 0x17FE009C
