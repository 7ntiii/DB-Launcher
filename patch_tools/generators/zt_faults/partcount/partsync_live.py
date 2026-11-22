"""partsync_gen.py: PARTSYNC - every game holds the same Trespasser (joint struggle) participant list, so the count,
the MultiPlayCorrectionParam SpEffect and the boss's max HP are the same on every screen. Static generator in the
style of diag/net/*_gen.py, Gen(dry=True): cave_registry.md is NOT written (the lead adds the printed rows).
Writes partsync_live.py NEXT TO THIS FILE (diag/net/zt_faults/partcount/).
    python diag/net/zt_faults/partcount/partsync_gen.py          (from the workspace root, or anywhere)
    ... --box 0xADDR                                              (another 16-byte box; default 0x492AFA0)

Stock facts [V, re-checked by the asserts below] (study: partcount report, d_*.txt in this folder):
  - Per-frame update of an instance (vtable 0x56ECFE0 slot 27 = 0x101BB40): after the participant loop it runs
    `mov x0, x19; bl 0x101B6E0` at 0x101CAD8 / 0x101CADC on EVERY frame in mode 6 (0x101CAC8 cmp w8,#6; b.eq).
  - 0x101B6E0 (count): n = (+0x2B8 - +0x2B0) >> 7; when mode is 0/6, step <= 3, +0x361 set and n != +0x2F0 it
    calls 0x10293C0(ins, functor 0x56ED530, -1) = functor 0x102D900 on the boss chr (0x17E7828 by key): NpcParam
    +0x20C -> MultiPlayCorrectionParam row, case n: add the SpEffect of field 0x24 + 4 (n - 1) (n = 0: remove
    all), then 0x19BDA00(mod, 1). It stores n in +0x2F0 in EVERY case (0x101B7C4), also when it did not apply.
  - Kind-4 apply 0x1023E80(ins, payload) (message 0x59 kind 4, handler 0x1023500 -> 0x10236A8): payload
    {u32 player, u8 accepted +4, u8 activate +5, u8 b +6 (-> entry +0xD), u8 leader-if-none +7, u8 hide +8,
    u8 defeated +9}. Adds the player once (idempotent) only when the boss chr / JointStruggleParam row is found
    on this game AND +4 != 0; always drops the player's pending request (+0x2D0).
  - Kind-6 apply 0x1025260(ins, payload) (handler -> 0x102370C): payload {u32 player, +4, +5, u8 +6 = also put
    the player on the "left by death" list +0x340}. Removes the entry if present, with the game's own cleanup.
  - In LAN every join (kind 3) and leave (kind 5) request goes to the requester's OWN game (0x1046FA4 -> the
    own server link) and is decided there (0x1023BA0 / 0x1024F9C), which broadcasts kind 4 / kind 6 to the
    others; nothing ever repairs a game that missed or reordered one of those broadcasts.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

PARTSYNC_CAVE = [  # FAR cave records
    (0xC5048AC, "00000000", "FD7BBDA9", True),
    (0xC5048B0, "00000000", "F35301A9", True),
    (0xC5048B4, "00000000", "F30300AA", True),
    (0xC5048B8, "00000000", "3421FCD0", True),
    (0xC5048BC, "00000000", "94823E91", True),
    (0xC5048C0, "00000000", "880240B9", True),
    (0xC5048C4, "00000000", "890640B9", True),
    (0xC5048C8, "00000000", "1F01096B", True),
    (0xC5048CC, "00000000", "00050054", True),
    (0xC5048D0, "00000000", "69C240B9", True),
    (0xC5048D4, "00000000", "8A0A40B9", True),
    (0xC5048D8, "00000000", "3F010A6B", True),
    (0xC5048DC, "00000000", "81040054", True),
    (0xC5048E0, "00000000", "880600B9", True),
    (0xC5048E4, "00000000", "893E4039", True),
    (0xC5048E8, "00000000", "29050011", True),
    (0xC5048EC, "00000000", "893E0039", True),
    (0xC5048F0, "00000000", "FF7F02A9", True),
    (0xC5048F4, "00000000", "893A4039", True),
    (0xC5048F8, "00000000", "E92300B9", True),
    (0xC5048FC, "00000000", "8A324039", True),
    (0xC504900, "00000000", "5F050071", True),
    (0xC504904, "00000000", "20010054", True),
    (0xC504908, "00000000", "5F090071", True),
    (0xC50490C, "00000000", "20020054", True),
    (0xC504910, "00000000", "5F0D0071", True),
    (0xC504914, "00000000", "C1020054", True),
    (0xC504918, "00000000", "09008052", True),
    (0xC50491C, "00000000", "29050051", True),
    (0xC504920, "00000000", "69F202B9", True),
    (0xC504924, "00000000", "12000014", True),
    (0xC504928, "00000000", "29008052", True),
    (0xC50492C, "00000000", "E9930039", True),
    (0xC504930, "00000000", "89364039", True),
    (0xC504934, "00000000", "E99B0039", True),
    (0xC504938, "00000000", "E00313AA", True),
    (0xC50493C, "00000000", "E1830091", True),
    (0xC504940, "00000000", "F058FAF0", True),
    (0xC504944, "00000000", "10023A91", True),
    (0xC504948, "00000000", "00023FD6", True),
    (0xC50494C, "00000000", "08000014", True),
    (0xC504950, "00000000", "29008052", True),
    (0xC504954, "00000000", "E9970039", True),
    (0xC504958, "00000000", "E00313AA", True),
    (0xC50495C, "00000000", "E1830091", True),
    (0xC504960, "00000000", "1059FAB0", True),
    (0xC504964, "00000000", "10820991", True),
    (0xC504968, "00000000", "00023FD6", True),
    (0xC50496C, "00000000", "E00313AA", True),
    (0xC504970, "00000000", "F35341A9", True),
    (0xC504974, "00000000", "FD7BC3A8", True),
    (0xC504978, "00000000", "B058FAF0", True),
    (0xC50497C, "00000000", "10821B91", True),
    (0xC504980, "00000000", "00021FD6", True),
    (0xF9D088, "00000000", "30AB05F0", True),
    (0xF9D08C, "00000000", "10B22291", True),
    (0xF9D090, "00000000", "00021FD6", True),
]
PARTSYNC = [
    (0x101CADC, "01FBFF97", "6B01FE97", True),
]

ORDER = [PARTSYNC_CAVE, PARTSYNC]
CAVES = {'PARTSYNC': 0xC5048AC, 'PSBOX': 0x492AFA0, 'TRAMP': 0xF9D088, 'HOOK_SITE': 0x101CADC, 'HOOK_WORD': 0x97FE016B}
