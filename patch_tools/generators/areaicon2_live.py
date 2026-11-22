"""areaicon2_gen.py: v3.9.16 candidate fix for the match 5 guest final crash (b_final_crash_notes.md).
Static generator: reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes areaicon2_live.py,
which supersedes areaicon_live.py (new cave ICON2, the same hook, the trampoline re-pointed, plus one new guard).
python areaicon2_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: Gen(dry=True); cave_registry.md is NOT written. ICON / ICONBOX are the existing areaicon_gen rows; the
new rows (LISTBUF, ICONFREE) are printed as a proposal for the lead.

What changes against v3.9.15 (areaicon_live.py):
- v3.9.15 filled the guest's MS+0x538 list with the GAME's allocator (reserve 0x1122FC0, [MS+0x550] vt+0x58).
  On a stock guest that list is never allocated (begin = 0): only the host-only body and the 0x6A reader own it.
  Both v3.9.15 guests crashed 3 s into the final in the stock load-process scheduler with a freed
  CSLoadProcessData_Geomhkxbnd still queued (b_final_crash_notes.md). The game-heap block we created is the one
  guest-side heap change that v3.9.14 did not make.
- v3.9.16: the guest's list never touches the game heap. A new cave ICON2 (the trampoline 0x1090AC8 is
  re-pointed; the baked v3.9.15 ICON body stays in place, unreachable) points MS+0x538 begin / end / capacity at a
  mod buffer LISTBUF (FAR_DATA, 56 entries) and copies the entries there; a list that is the game's own
  (begin != 0 and != LISTBUF) is never touched.
- AREA_ICON_FREE: the MapSystem teardown 0x11103E0 frees begin at 0x1110668..0x1110680. When begin == LISTBUF the
  guard zeroes begin / end / capacity and the teardown skips the free (cbz x1), so the game never frees our buffer.
  The other frees of MS+0x538 (reserve 0x1122FC0 when it grows, the body's 0x112317C / 0x1123368) run only in the
  host-only body and the 0x6A reader, which guests never run; the host's begin is never LISTBUF.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

AREA_ICON_CAVE = [  # FAR cave records
    (0xC503698, "00000000", "F55BBFA9", True),
    (0xC50369C, "00000000", "75000090", True),
    (0xC5036A0, "00000000", "B5C20C91", True),
    (0xC5036A4, "00000000", "A80240B9", True),
    (0xC5036A8, "00000000", "48040034", True),
    (0xC5036AC, "00000000", "6A000090", True),
    (0xC5036B0, "00000000", "4AE11391", True),
    (0xC5036B4, "00000000", "1F090071", True),
    (0xC5036B8, "00000000", "E0020054", True),
    (0xC5036BC, "00000000", "B60640B9", True),
    (0xC5036C0, "00000000", "DFE20071", True),
    (0xC5036C4, "00000000", "48030054", True),
    (0xC5036C8, "00000000", "689E42F9", True),
    (0xC5036CC, "00000000", "680000B4", True),
    (0xC5036D0, "00000000", "1F010AEB", True),
    (0xC5036D4, "00000000", "C1020054", True),
    (0xC5036D8, "00000000", "6DE21491", True),
    (0xC5036DC, "00000000", "AA2900A9", True),
    (0xC5036E0, "00000000", "4B010791", True),
    (0xC5036E4, "00000000", "6BA602F9", True),
    (0xC5036E8, "00000000", "36020034", True),
    (0xC5036EC, "00000000", "A9220091", True),
    (0xC5036F0, "00000000", "EB03162A", True),
    (0xC5036F4, "00000000", "2C0140F9", True),
    (0xC5036F8, "00000000", "4C0100F9", True),
    (0xC5036FC, "00000000", "29210091", True),
    (0xC503700, "00000000", "4A210091", True),
    (0xC503704, "00000000", "6B050051", True),
    (0xC503708, "00000000", "6BFFFF35", True),
    (0xC50370C, "00000000", "6AA202F9", True),
    (0xC503710, "00000000", "07000014", True),
    (0xC503714, "00000000", "689E42F9", True),
    (0xC503718, "00000000", "1F010AEB", True),
    (0xC50371C, "00000000", "81000054", True),
    (0xC503720, "00000000", "6DE21491", True),
    (0xC503724, "00000000", "BF7D00A9", True),
    (0xC503728, "00000000", "7FA602F9", True),
    (0xC50372C, "00000000", "BF0200B9", True),
    (0xC503730, "00000000", "F55BC1A8", True),
    (0xC503734, "00000000", "086852B9", True),
    (0xC503738, "00000000", "7060FAB0", True),
    (0xC50373C, "00000000", "10722191", True),
    (0xC503740, "00000000", "00021FD6", True),
    (0x1090AC8, "00000000", "90A305F0", True),
    (0x1090ACC, "00000000", "10621A91", True),
    (0x1090AD0, "00000000", "00021FD6", True),
]
AREA_ICON_HOOK = [
    (0x1110858, "086852B9", "9C00FE17", True),
]
AREA_ICON_FREE = [  # FAR cave records
    (0xC503758, "00000000", "619E42F9", True),
    (0xC50375C, "00000000", "70000090", True),
    (0xC503760, "00000000", "10E21391", True),
    (0xC503764, "00000000", "3F0010EB", True),
    (0xC503768, "00000000", "A1000054", True),
    (0xC50376C, "00000000", "71E21491", True),
    (0xC503770, "00000000", "3F7E00A9", True),
    (0xC503774, "00000000", "7FA602F9", True),
    (0xC503778, "00000000", "E1031FAA", True),
    (0xC50377C, "00000000", "7060FAB0", True),
    (0xC503780, "00000000", "10B21991", True),
    (0xC503784, "00000000", "00021FD6", True),
    (0x1090704, "00000000", "90A305F0", True),
    (0x1090708, "00000000", "10621D91", True),
    (0x109070C, "00000000", "00021FD6", True),
    (0x1110668, "619E42F9", "2700FE17", True),
]

ORDER = [AREA_ICON_CAVE, AREA_ICON_HOOK, AREA_ICON_FREE]
CAVES = {'ICON': 0xC503698, 'ICONFREE': 0xC503758}
BOX = 0xC50F330
LISTBUF = 0xC50F4F8
SITE = 0x1110858
PAD = 0x1090AC8
FSITE = 0x1110668
PAD2 = 0x1090704
