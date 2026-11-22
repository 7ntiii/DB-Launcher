"""cutauth_gen.py: a guest cuts after Phases II / III by the AUTHORITY's ranks when the assist has them (static
generator, cutauth_notes.md; realnet_notes R1, assist_v400_notes 1 "Real fix"). Reads nso/*.bin,
patch_manager.cpp and every *_live.py through cave_lib. Writes cutauth_live.py.
python cutauth_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Why [V code below]: every game cuts for every player in its own EndPhase (0x1144A60 -> 0xF6AF20 -> score manager
vt+0x50 rank 0xF871C0, then vt+0x60 cut 0xF879A0), from its own Virtue copies. After a network stall at a phase end
two games can rank differently and cut different players. The assist cannot write the ranks (rank and cut run back
to back in one game-thread call), and the authority's list (type 13) exists only after the authority's cut.

The cut 0xF879A0 [V]: threshold w21 (PhaseInfoParam +0x92, Phase III EnvEvent +0xAA override, Bloodbound (rule byte
main+0x5B65C70 == 2) halved and rounded up with the TEAM rank functor 0x56EA238 = entry +0x20 instead of 0x56EA280
= entry +0x10); then per phase entry (par+0x33D0, 0x60 each, count +0x488; x20 = entry + 0x38) not yet at stage
byte 4: w0 = functor rank, 0xF87BDC `cmp w0, w21; b.le keep` else event 1 (04 03 01 01) at 0xF87BF4.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

CUTAUTH_CAVE = [  # FAR cave records
    (0xC502C60, "00000000", "10B3FCF0", True),
    (0xC502C64, "00000000", "101246F9", True),
    (0xC502C68, "00000000", "D00200B4", True),
    (0xC502C6C, "00000000", "106A6F39", True),
    (0xC502C70, "00000000", "90020035", True),
    (0xC502C74, "00000000", "700000B0", True),
    (0xC502C78, "00000000", "111A43B9", True),
    (0xC502C7C, "00000000", "31020034", True),
    (0xC502C80, "00000000", "D0B1FCD0", True),
    (0xC502C84, "00000000", "10FE46F9", True),
    (0xC502C88, "00000000", "D00100B4", True),
    (0xC502C8C, "00000000", "10BA40B9", True),
    (0xC502C90, "00000000", "300EB872", True),
    (0xC502C94, "00000000", "1F02116B", True),
    (0xC502C98, "00000000", "41010054", True),
    (0xC502C9C, "00000000", "91825CB8", True),
    (0xC502CA0, "00000000", "3F420071", True),
    (0xC502CA4, "00000000", "E2000054", True),
    (0xC502CA8, "00000000", "700000B0", True),
    (0xC502CAC, "00000000", "10820C91", True),
    (0xC502CB0, "00000000", "1002118B", True),
    (0xC502CB4, "00000000", "11024039", True),
    (0xC502CB8, "00000000", "51000034", True),
    (0xC502CBC, "00000000", "E003112A", True),
    (0xC502CC0, "00000000", "1F00156B", True),
    (0xC502CC4, "00000000", "3054FAB0", True),
    (0xC502CC8, "00000000", "10822F91", True),
    (0xC502CCC, "00000000", "00021FD6", True),
    (0xF08230, "00000000", "D0AF05D0", True),
    (0xF08234, "00000000", "10823191", True),
    (0xF08238, "00000000", "00021FD6", True),
]
CUTAUTH = [
    (0xF87BDC, "1F00156B", "9501FE17", True),
]

ORDER = [CUTAUTH_CAVE, CUTAUTH]
CAVES = {'CAUTH': 0xC502C60}
BOX = 0xC50F318
KEY_MAGIC = 0xC0710000
SITE = 0xF87BDC
HOOK_WORD = 0x17FE0195
