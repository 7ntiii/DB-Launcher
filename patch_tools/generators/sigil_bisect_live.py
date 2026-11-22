"""Bisect helpers (test only): put built-in hook words back to stock / older words on a running game.
(offset_from_main, current_hex, wanted_hex, is_code)"""

STATE_OFF = [  # SIGIL3_STATE hooks back to stock
    (0x1178DDC, "57181315", "1F090071", True),
    (0x117AA1C, "03000014", "68000035", True),
]
STEP_OLD = [  # SIGIL3_STEP_T hook back to the old SIGIL3_STEP cave
    (0x117B770, "EF0D1395", "E00D1395", True),
]
ORDER = [STATE_OFF, STEP_OLD]
