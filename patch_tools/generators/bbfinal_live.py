"""bbfinal_gen.py: Bloodbound Alliances final with two pairs, game half of the F3 fix (static generator,
bbfinal_notes.md; players8_notes.md F3).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes bbfinal_live.py.
python bbfinal_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

What it fixes (bbfinal_notes 2c): the final's kill decision 0x116F240 (coordinator vt+0x88) gives every listed
finalist an event: survivor (in C+0x148) -> 5, partner of a survivor (alliance entry) -> 8, else -> 7. Event 8
turns a word at stage 2 (02 01 01 00, the host's death list) into 04 04 01 01 = the winner class (team rank 1 under
rule 2), but leaves a word at stage 1 unchanged [V 0x11383E8 tables 0x4C49AA4 / 0x4C49AB3]. In LAN only the host
runs the death list, so on a guest whose own player is out while its partner lives, the own word is still
01 01 00 00: no stage 4 -> no team rank from it, no MatchResultCreate item (0x11459C0 needs stage 4) -> no Outcome
for that player. BB_ALLY_OUT does what the online server's death list did: for rule 2 only, a stage-1 word that
is about to get event 8 is first set to 02 01 01 00, so event 8 gives 04 04 01 01 on every game.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

BB_FINAL_CAVE = [  # FAR cave records
    (0xC502920, "00000000", "10B3FCF0", True),
    (0xC502924, "00000000", "101246F9", True),
    (0xC502928, "00000000", "B00100B4", True),
    (0xC50292C, "00000000", "116A6F39", True),
    (0xC502930, "00000000", "71010035", True),
    (0xC502934, "00000000", "10B3FCF0", True),
    (0xC502938, "00000000", "11C27139", True),
    (0xC50293C, "00000000", "3F0A0071", True),
    (0xC502940, "00000000", "E1000054", True),
    (0xC502944, "00000000", "B1024139", True),
    (0xC502948, "00000000", "3F060071", True),
    (0xC50294C, "00000000", "81000054", True),
    (0xC502950, "00000000", "51208052", True),
    (0xC502954, "00000000", "3100A072", True),
    (0xC502958, "00000000", "B14200B9", True),
    (0xC50295C, "00000000", "01018052", True),
    (0xC502960, "00000000", "7063FAB0", True),
    (0xC502964, "00000000", "10821691", True),
    (0xC502968, "00000000", "00021FD6", True),
    (0x10EFAB0, "00000000", "90A005F0", True),
    (0x10EFAB4, "00000000", "10822491", True),
    (0x10EFAB8, "00000000", "00021FD6", True),
]
BB_ALLY_OUT = [
    (0x116F670, "01018052", "1001FE17", True),
]

ORDER = [BB_FINAL_CAVE, BB_ALLY_OUT]
CAVES = {'BBALLY': 0xC502920, 'TR': 0x10EFAB0}
SITE = 0x116F670
