"""Paste-ready patch records: (offset_from_main, orig_hex, new_hex, is_code). Bytes are little-endian as in memory.
Source: enemy_drop_trace_notes.md. Every orig word read from nso/main_text.bin; every new word disassembled with
capstone at its address. No cave is used (the ro padding 0x563ED00..0x563EDFF stays free).
Needs ITEMS_1 + ITEMS_2 applied first (cave_f, I1 broadcast, I3, I4a/I4b)."""

DROPS = [  # D1: the 0x1E reader serves every subtype in game type 0x16 (LAN forces +0xD80 = 0x16)
    # 0x15973E4  b.ne 0x1598a8c  ->  nop
    # Original: cmp w8(gametype),#0x16 ; ccmp w9(subtype),#1,#4,eq ; b.ne exit
    # = "if game type == 0x16 and subtype != 1: stop reading". Non-0x16 game types already pass.
    (0x15973E4, "41B50054", "1F2003D5", True),  # D1 reader: no game-type-0x16 subtype filter
]

DROPS_OPT = [  # D2: apply ONLY if the live read shows the rule-id table disables drops (see notes, gate C3)
    # 0x15AC938  cbz w19, 0x15acd88  ->  nop   (w19 = byte +6 of the 0x5A5AB30 entry for rule id *(*(main+0x5B57EB8)+0x20)+0x154)
    (0x15AC938, "93220034", "1F2003D5", True),  # D2 online lot create: ignore the per-rule "drops enabled" byte
]

ORDER = [DROPS]  # DROPS_OPT only after the live check
