"""Optional mitigation for the guest abort at the airship crash (starcrash_notes.md). Hand-written, static only,
NOT live-tested. Record format: (offset_from_main, orig_hex, new_hex, is_code), bytes in memory order.

TE_COMMEND_UI: 0x12A8C08 `bl 0x110C1B8` -> nop. The UI (script) thread's TextEffect completion callback
0x12A8B8C no longer pushes the two Commendation records (30000 / 40000, value 0) for the local player into the
Virtue record queue par+0x33A0 (writer 0xF94A14, guarded by a CSDebugPanicLock). The game thread's own
Commendation ranking pushes (0x110C850 / 0x110C9DC) are unchanged. Apply on every game, in the hub."""

TE_COMMEND_UI = [
    (0x12A8C08, "6C8DF997", "1F2003D5", True),   # bl 0x110c1b8 -> nop
]
ORDER = [TE_COMMEND_UI]
