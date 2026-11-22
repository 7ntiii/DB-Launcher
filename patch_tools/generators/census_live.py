"""Paste-ready patch records from the offline-gate census: (offset_from_main, orig_hex, new_hex, is_code).
Bytes are little-endian as in memory. Every original word was read from nso/main_text.bin, and every new word
was decoded with capstone at its own address (scratchpad census_live_gen.py). No cave words are used, so no
padding at main+0x563EE00..0x563EFFF is consumed.
One group per feature. Each group is independent and can be applied and removed on its own.
Details, live checks and risks: census_patchset.md."""

CHARM = [  # 0x3F act-point / charm record reaches the other games (send to server -> broadcast). Reader 0xED6AE0 already runs every frame in mode 6.
    (0x0DFD900, "082540F9", "082140F9", True),  # C1 0xDFC620: ldr x8,[x8,#0x48] -> [x8,#0x40] (0x3F send -> broadcast)
    (0x0DFE56C, "082540F9", "082140F9", True),  # C2 0xDFDD40: same
    (0x0E0008C, "082540F9", "082140F9", True),  # C3 0xDFFF18: same
    (0x0E02648, "082540F9", "082140F9", True),  # C4 0xE02550: same
]
WARP = [  # intermission warp point: pick and apply on the warping game, like offline. Nothing is sent.
    (0x10BE1E0, "01010054", "08000014", True),  # W1 b.ne #0x10be200 -> b #0x10be200
]
CUTSCENE = [  # cutscene skip: skip your own cutscene at once, like offline. No 0x25 vote is sent.
    (0x11B932C, "610C0054", "63000014", True),  # S1 b.ne #0x11b94b8 -> b #0x11b94b8
]
DEATHFLAG = [  # enemy death: run the generator-pool membership check in mode 6 (same result on every game).
    (0x1751C20, "A0070054", "1F2003D5", True),  # D1 b.eq #0x1751d14 -> nop
]
LEVEL = [  # OPTIONAL, check first (see census_patchset.md, LEVEL): blood / level award always takes the local-player path.
    (0x17BBD48, "A80600B4", "35000014", True),  # L1 cbz x8,#0x17bbe1c -> b #0x17bbe1c
]

ORDER = [CHARM, WARP, CUTSCENE, DEATHFLAG]  # LEVEL optional, only after its live check
