"""levelshare_gen.py: LEVELSHARE - every game gets the host's enemy strength levels (boss_scale study, 2026-11-21).
Static generator in the style of diag/net/*_gen.py. Gen(dry=True): cave_registry.md is NOT written (the lead adds
the printed rows). Writes bossscale_live.py NEXT TO THIS FILE (diag/net/zt_faults/boss_scale/).
    python diag/net/zt_faults/boss_scale/levelshare_gen.py      (from the workspace root, or anywhere)

Root cause [V code + data, L live lists]:
  The Trespasser chr's NpcParam row is chosen at creation by 0xEB8CA0 (only caller 0x1773E04 in the chr creator
  0x1773A20): key = chr handle (set << 12 | index); if the key is in the strength-level map of the module
  M = [*(main+0x5B3CDF8) + 0x3378] (unordered map at M+0x38, nodes {next, hash, u16 key +0x10, u16 key +0x12,
  s16 level +0x14}, first node M+0x50, size M+0x60), the NpcParam id, the think id and the JointStruggleParam id
  get + 1000 * level (0xEB8EEC..0xEB8F0C), e.g. NpcParam 21400000 -> 21401000, JointStruggleParam 214000000 ->
  214001000. Row 21401000 holds SpEffect 2210100 in its slot +0x68 and the base 2799300 at +0x498; the chr's
  SpEffect slot provider (vtable 0x56E22F8, slot +0x48 = 0xEB0540) adds the round (stage+0xB8) to the base when
  row +0x128 bit 2 is set: 2799300 + 2 = 2799302 (max HP rate 1.25, attack rates 1.35). Row 21400000 has neither.
  Writers of M+0x38: the trend step 0x1120B80 -> 0xEB7B40 at 0x1121304 (inside the MapSystem body 0x11123A0,
  host only since MAPSIM_HOST 0x11123E0); the lottery 0xEB5060 (returns at 0xEB509C in mode 6); the 0x75 reader
  0xEB7DA0 (PrepareSecond 0x114F324; reads only the server member mgr3+0x658, 0xEB7E38). In LAN no 0x75 comes,
  so a guest's map stays empty and its copy is built from the base row.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

LEVELSHARE_CAVE = [  # FAR cave records
    (0xC504704, "00000000", "FF8301D1", True),
    (0xC504708, "00000000", "E00700A9", True),
    (0xC50470C, "00000000", "E20F01A9", True),
    (0xC504710, "00000000", "E41702A9", True),
    (0xC504714, "00000000", "FD7B03A9", True),
    (0xC504718, "00000000", "F35304A9", True),
    (0xC50471C, "00000000", "F55B05A9", True),
    (0xC504720, "00000000", "530000F0", True),
    (0xC504724, "00000000", "73A23E91", True),
    (0xC504728, "00000000", "690240B9", True),
    (0xC50472C, "00000000", "29040034", True),
    (0xC504730, "00000000", "CAB1FC90", True),
    (0xC504734, "00000000", "4AFD46F9", True),
    (0xC504738, "00000000", "CA0300B4", True),
    (0xC50473C, "00000000", "4BB940B9", True),
    (0xC504740, "00000000", "6B050011", True),
    (0xC504744, "00000000", "3F010B6B", True),
    (0xC504748, "00000000", "41030054", True),
    (0xC50474C, "00000000", "6C0640B9", True),
    (0xC504750, "00000000", "9F010B6B", True),
    (0xC504754, "00000000", "E0020054", True),
    (0xC504758, "00000000", "740A40B9", True),
    (0xC50475C, "00000000", "B4020034", True),
    (0xC504760, "00000000", "9F4A0071", True),
    (0xC504764, "00000000", "68020054", True),
    (0xC504768, "00000000", "55BD59F9", True),
    (0xC50476C, "00000000", "350200B4", True),
    (0xC504770, "00000000", "B5E20091", True),
    (0xC504774, "00000000", "6B0600B9", True),
    (0xC504778, "00000000", "6C0E40B9", True),
    (0xC50477C, "00000000", "8C050011", True),
    (0xC504780, "00000000", "6C0E00B9", True),
    (0xC504784, "00000000", "76420091", True),
    (0xC504788, "00000000", "E00315AA", True),
    (0xC50478C, "00000000", "E10316AA", True),
    (0xC504790, "00000000", "E20316AA", True),
    (0xC504794, "00000000", "E30316AA", True),
    (0xC504798, "00000000", "D04DFAB0", True),
    (0xC50479C, "00000000", "10821A91", True),
    (0xC5047A0, "00000000", "00023FD6", True),
    (0xC5047A4, "00000000", "D6120091", True),
    (0xC5047A8, "00000000", "94060051", True),
    (0xC5047AC, "00000000", "F4FEFF35", True),
    (0xC5047B0, "00000000", "E00740A9", True),
    (0xC5047B4, "00000000", "E20F41A9", True),
    (0xC5047B8, "00000000", "E41742A9", True),
    (0xC5047BC, "00000000", "FD7B43A9", True),
    (0xC5047C0, "00000000", "F35344A9", True),
    (0xC5047C4, "00000000", "F55B45A9", True),
    (0xC5047C8, "00000000", "FF830191", True),
    (0xC5047CC, "00000000", "B04DFA90", True),
    (0xC5047D0, "00000000", "10823291", True),
    (0xC5047D4, "00000000", "00021FD6", True),
    (0x16F5470, "00000000", "707005F0", True),
    (0x16F5474, "00000000", "10121C91", True),
    (0x16F5478, "00000000", "00021FD6", True),
]
LEVELSHARE = [
    (0x1773E04, "A713DD97", "9B05FE97", True),
]

ORDER = [LEVELSHARE_CAVE, LEVELSHARE]
CAVES = {'LEVELSHARE': 0xC504704, 'LVBOX': 0xC50FFA8, 'TRAMP': 0x16F5470, 'HOOK_SITE': 0x1773E04, 'HOOK_WORD': 0x97FE059B}
