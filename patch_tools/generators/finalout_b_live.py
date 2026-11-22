"""finalout_b_gen.py (helper 4 review of finalout_gen.py, audit_new_groups_notes.md): a player eliminated from a 3+ player final is processed by the game at once (static generator,
spectate_notes.md section "3-player final elimination"). Reads nso/*.bin, patch_manager.cpp and every *_live.py
through cave_lib. Writes finalout_b_live.py (replaces finalout_live.py; same FOUT / FOUTBOX rows, same trampoline
and FINALOUT_HOOK / FINALOUT_SPECTATE words; only the FOUT cave words differ).
python finalout_b_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Why (run3 2026-11-16, spectate FAIL with real hits) [V code below]:
- The host's death list sends a player who is out for good to coordinator vt+0x98 0x116FD20. Without a living
  alliance partner (always in the final: alliances are disbanded) it only queues {no, 1} into the elimination
  deque par+0x38A0 (0x1143580, opened online by the shipped 0x11435B0). Live: A's deque (1, [(3, 1)]).
- The ONLY consumer of that deque is the stage update block 0x1140DD0..0x11412F0, behind the offline gate
  0x1140DCC (`cbz w8 (+0xBDA), #0x114197c`). Offline it builds a list of the eliminated players, ranks it
  (0x1144A60 -> final kill decision: event 7 = 04 05 01 01 for a player who is not a survivor), applies the words
  to the pgds (0x11454A0), makes the Outcome items (0x11459C0) and, for the LOCAL player, sets par+0x164 = 1
  (spectating; offline gate 0x1141220). Online the server did this; in LAN nothing does, so in a 3-player final
  the eliminated player stays dead at stage 01 01 00 00 with no spectator state until the final ends.
- With 2 players this never showed: the second player's death ends the final itself (kill decision), and the
  EndPhase that follows lists the eliminated player normally (v3.2 proof).
- Guests never run the death list, so their deques stay empty: the assist (assist_v399.diff) writes each player
  that is out for good (its own game said so, type 10 kind 1) into the mailbox FOUTBOX on every game; the cave
  queues it through the game's own 0x1143580 (which merges a player already queued).
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

FINALOUT_CAVE = [  # FAR cave records
    (0xC502B20, "00000000", "E8020035", True),
    (0xC502B24, "00000000", "700000B0", True),
    (0xC502B28, "00000000", "111643B9", True),
    (0xC502B2C, "00000000", "F1020034", True),
    (0xC502B30, "00000000", "90BB40B9", True),
    (0xC502B34, "00000000", "1F120071", True),
    (0xC502B38, "00000000", "81020054", True),
    (0xC502B3C, "00000000", "904B5CF9", True),
    (0xC502B40, "00000000", "500200B5", True),
    (0xC502B44, "00000000", "E007BDA9", True),
    (0xC502B48, "00000000", "FE7F01A9", True),
    (0xC502B4C, "00000000", "F12300B9", True),
    (0xC502B50, "00000000", "30008052", True),
    (0xC502B54, "00000000", "F0930039", True),
    (0xC502B58, "00000000", "E0031CAA", True),
    (0xC502B5C, "00000000", "E1830091", True),
    (0xC502B60, "00000000", "1062FAB0", True),
    (0xC502B64, "00000000", "10021691", True),
    (0xC502B68, "00000000", "00023FD6", True),
    (0xC502B6C, "00000000", "FE7F41A9", True),
    (0xC502B70, "00000000", "E007C3A8", True),
    (0xC502B74, "00000000", "700000B0", True),
    (0xC502B78, "00000000", "1F1603B9", True),
    (0xC502B7C, "00000000", "F061FAD0", True),
    (0xC502B80, "00000000", "10423791", True),
    (0xC502B84, "00000000", "00021FD6", True),
    (0xC502B88, "00000000", "F061FAF0", True),
    (0xC502B8C, "00000000", "10F22591", True),
    (0xC502B90, "00000000", "00021FD6", True),
    (0x10C2CA4, "00000000", "10A20590", True),
    (0x10C2CA8, "00000000", "10822C91", True),
    (0x10C2CAC, "00000000", "00021FD6", True),
]
FINALOUT_HOOK = [
    (0x1140DCC, "885D0034", "B607FE17", True),
]

ORDER = [FINALOUT_CAVE, FINALOUT_HOOK]
FINALOUT_SPECTATE = [  # optional, NOT in ORDER: apply after FINALOUT_HOOK if no spectator camera
    (0x1141220, "88060034", "1F2003D5", True),  # nop
]
CAVES = {'FOUT': 0xC502B20}
BOX = 0xC50F314
SITE = 0x1140DCC
HOOK_WORD = 0x17FE07B6
OPTIONAL = ['FINALOUT_SPECTATE']
