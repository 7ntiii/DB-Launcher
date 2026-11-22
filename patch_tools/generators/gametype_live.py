"""Paste-ready patch records: (offset_from_main, orig_hex, new_hex, is_code). Bytes are little-endian as in memory.
Source: gametype_census_notes.md (census of every read of the game-type byte [*(main+0x5B65C20)+0xD80]).
Every orig word read from nso/main_text.bin; every new word disassembled with capstone at its address.

Result of the census: only ONE site blocks a receive or a feature at game type 0x16, and it is the
0x1E item reader that drops_live.py D1 already fixes. GT_B repeats that record so this file is complete;
apply it from ONE file only (drops_live.DROPS or GT_B), not both (same address, same words, so a second
apply is a no-op but it is pointless).
"""

GT_B = [  # (b) world items / enemy drops / pickups: 0x1E reader 0x1597280
    # 0x15973E4  b.ne 0x1598a8c  ->  nop
    # cmp w8(gametype),#0x16 ; ccmp w9(subtype),#1,#4,eq ; b.ne exit
    # = "game type 0x16 and subtype != 1 -> stop reading 0x1E". Other game types (offline, invasion types) pass.
    # Risk: low, live-verified (drops/pickups on two games). Both games must apply it (each game reads 0x1E).
    (0x15973E4, "41B50054", "1F2003D5", True),  # = drops_live D1
]

GT_C_OPT = [  # (c) NOT recommended unless spawn placement is wrong at match load. See notes site 10.
    # 0x1830328  b.ne 0x1830368  ->  b 0x1830368
    # Online spawn (fn 0x182feb0): game type 0x16 copies the server-given transform from gamedata+0xAE0..+0xB08
    # (written by the accept handler 0x14D5FF4..0x14D6030 from the 0x33 ticket, which the LAN stub never fills,
    # so it holds the bss default main+0x6B23850). The patch sends 0x16 down the "other game type" path:
    # local spawn lookup 0xF35000 (the offline / invasion path). Risk: medium; both games should apply it.
    (0x1830328, "01020054", "10000014", True),
]

ORDER = [GT_B]  # GT_C_OPT only after a live look at the spawn position
