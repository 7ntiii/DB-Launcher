"""lineuphold_gen.py: LINEUPHOLD - the match loading screen waits (capped) until every member's player data is in,
so the game's own line-up shows every player. Static generator in the style of diag/net/*_gen.py, Gen(dry=True):
cave_registry.md is NOT written (the lead adds the printed rows). Writes lineuphold_live.py NEXT TO THIS FILE.
    python diag/net/loadscreen/lineuphold_gen.py        (from the workspace root, or anywhere)

Stock facts [V, re-checked by the asserts below]:
  - CSMatchLoadingOverwrapStep (step table built at 0x1131C60 into main+0x5B6BE60; names UTF-16 in ro):
    Init 0x112FFC4, MenuInit 0x112FFC8, WaitMatchPreProcess 0x112FFE8, BeginMatchStartPlayerRend 0x1130068,
    MatchStartPlayerRend 0x11300A0, IsLoadingOverwrap 0x1130188, Finish 0x113018C.
  - WaitMatchPreProcess: par = *(main+0x5B3CDF8); w0 = par vt+0x60 (the stage step = "match phase");
    0x1130018 `cmp w0, #2`; 0x113001C `b.lt 0x1130034` (return, polled again next frame) else 0x1130020 -> advance
    (tail call 0x112FED8). So the screen moves on in the first frame of stage step 2 (MatchLoading).
  - MatchStartPlayerRend 0x11300A0: when the figure map [[main+0x5B76C30]]+0x519E8 is empty or every node is
    loaded (+0x38), it calls 0x1AFAE80 at 0x11300E4. 0x1AFAE80 -> std::function 0x5750BF0 (op 0x1B01360) ->
    layout 0x1AA5F18 -> factory 0x574AA98 (op 0x1AAE490: new 0x14F0) -> view ctor 0x1313D20.
  - The ctor builds the line-up ONCE: 0x1314100 refreshes the figure map (0x149E040: one figure per pgd with
    +0xD0 != -1 and +0x104 <= 0xB, iterator 0xCE9F40 flags 0x27 = local pgd + pool copies), then 0x13144FC runs
    the functor 0x1315840 (vtable 0x5708888) over the same pgds: skip +0xD0 == -1 or a duplicate, skip
    +0x46A0 == 0, else add the figure (0x1315A80, map lookup by number). 0x1315840 / 0x1315A80 have no other
    caller, so a copy bound after this frame never appears on that screen.
  - A remote pool copy gets +0xD0 / +0x46A0 / +0x104 only from that member's type-5 record (0x14DD180; member
    +0xE8 = 1 at 0x14DE294 marks it), lineup_notes 2, remote_player_hang_notes 5b.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

LINEUPHOLD_CAVE = [  # FAR cave records
    (0xC5047E4, "00000000", "0B010054", True),
    (0xC5047E8, "00000000", "3021FCD0", True),
    (0xC5047EC, "00000000", "10C23E91", True),
    (0xC5047F0, "00000000", "110240B9", True),
    (0xC5047F4, "00000000", "F1000034", True),
    (0xC5047F8, "00000000", "110640B9", True),
    (0xC5047FC, "00000000", "31060011", True),
    (0xC504800, "00000000", "110600B9", True),
    (0xC504804, "00000000", "7061FA90", True),
    (0xC504808, "00000000", "10D20091", True),
    (0xC50480C, "00000000", "00021FD6", True),
    (0xC504810, "00000000", "7061FA90", True),
    (0xC504814, "00000000", "10820091", True),
    (0xC504818, "00000000", "00021FD6", True),
    (0x10B04E4, "00000000", "B0A20590", True),
    (0x10B04E8, "00000000", "10921F91", True),
    (0x10B04EC, "00000000", "00021FD6", True),
]
LINEUPHOLD = [
    (0x113001C, "CB000054", "3201FE17", True),
]

ORDER = [LINEUPHOLD_CAVE, LINEUPHOLD]
CAVES = {'LINEUPHOLD': 0xC5047E4, 'LHBOX': 0x492AFB0, 'TRAMP': 0x10B04E4, 'HOOK_SITE': 0x113001C, 'HOOK_WORD': 0x17FE0132}
