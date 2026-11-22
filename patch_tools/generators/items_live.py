"""Paste-ready patch records: (offset_from_main, orig_hex, new_hex, is_code). Bytes are little-endian as in memory.
Cave records have orig "00000000" (zero padding past the ro file end, main+0x563E45C..0x563F000).
Apply each group in list order; within a group the hook that makes it live comes last."""

ITEMS_1 = [  # ITEMS-1 caves (inert until hooked)
    (0x563E500, "00000000", "40000054", True),  # cave_f (0x1E role filter)
    (0x563E504, "00000000", "C363FD16", True),  # cave_f (0x1E role filter)
    (0x563E508, "00000000", "6C97FF90", True),  # cave_f (0x1E role filter)
    (0x563E50C, "00000000", "8C617F39", True),  # cave_f (0x1E role filter)
    (0x563E510, "00000000", "4C000035", True),  # cave_f (0x1E role filter)
    (0x563E514, "00000000", "BF63FD16", True),  # cave_f (0x1E role filter)
    (0x563E518, "00000000", "BB63FD16", True),  # cave_f (0x1E role filter)
    (0x563E520, "00000000", "080100B4", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E524, "00000000", "E82700D0", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E528, "00000000", "080547F9", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E52C, "00000000", "880000B4", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E530, "00000000", "086952B9", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E534, "00000000", "1F190071", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E538, "00000000", "40000054", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E53C, "00000000", "5E97FD16", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E540, "00000000", "F497FD16", True),  # cave_m6a (reply in mode 6, check 1)
    (0x563E544, "00000000", "080100B4", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E548, "00000000", "E82700D0", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E54C, "00000000", "080547F9", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E550, "00000000", "880000B4", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E554, "00000000", "086952B9", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E558, "00000000", "1F190071", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E55C, "00000000", "40000054", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E560, "00000000", "CA97FD16", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E564, "00000000", "EB97FD16", True),  # cave_m6b (reply in mode 6, check 2)
    (0x563E568, "00000000", "E92700D0", True),  # cave_push (new item to all)
    (0x563E56C, "00000000", "290547F9", True),  # cave_push (new item to all)
    (0x563E570, "00000000", "E90100B4", True),  # cave_push (new item to all)
    (0x563E574, "00000000", "2A6952B9", True),  # cave_push (new item to all)
    (0x563E578, "00000000", "5F190071", True),  # cave_push (new item to all)
    (0x563E57C, "00000000", "81010054", True),  # cave_push (new item to all)
    (0x563E580, "00000000", "FD7BBFA9", True),  # cave_push (new item to all)
    (0x563E584, "00000000", "20410091", True),  # cave_push (new item to all)
    (0x563E588, "00000000", "090040F9", True),  # cave_push (new item to all)
    (0x563E58C, "00000000", "292140F9", True),  # cave_push (new item to all)
    (0x563E590, "00000000", "E20301AA", True),  # cave_push (new item to all)
    (0x563E594, "00000000", "C1038052", True),  # cave_push (new item to all)
    (0x563E598, "00000000", "03328052", True),  # cave_push (new item to all)
    (0x563E59C, "00000000", "20013FD6", True),  # cave_push (new item to all)
    (0x563E5A0, "00000000", "FD7BC1A8", True),  # cave_push (new item to all)
    (0x563E5A4, "00000000", "E0031FAA", True),  # cave_push (new item to all)
    (0x563E5A8, "00000000", "C0035FD6", True),  # cave_push (new item to all)
    (0x563E5AC, "00000000", "7894FD16", True),  # cave_push (new item to all)
]
ITEMS_2 = [  # ITEMS-2 code + hooks (I2 filter last)
    (0x15A49A0, "082540F9", "082140F9", True),  # I1 sub 5 take: send to server -> broadcast
    (0x15AAF84, "082540F9", "082140F9", True),  # I1 sub 0x14 enemy drop: send to server -> broadcast
    (0x1826B40, "082540F9", "082140F9", True),  # I1 sub 0 join sync: send to server -> broadcast
    (0x15AE1E0, "082540F9", "082140F9", True),  # I1 sub 0xD: send to server -> broadcast
    (0x15AF87C, "082540F9", "082140F9", True),  # I1 sub 9: send to server -> broadcast
    (0x15B056C, "082540F9", "082140F9", True),  # I1 sub 0xE: send to server -> broadcast
    (0x15B1B00, "082540F9", "082140F9", True),  # I1 sub 0xA: send to server -> broadcast
    (0x15B7FA8, "082540F9", "082140F9", True),  # I1 sub 8: send to server -> broadcast
    (0x15A9540, "082540F9", "082140F9", True),  # I1 sub 0x16: send to server -> broadcast
    (0x15A9FDC, "082540F9", "082140F9", True),  # I1 sub 0x17: send to server -> broadcast
    (0x15AAC24, "082540F9", "082140F9", True),  # I1 sub 0x11: send to server -> broadcast
    (0x15AAD6C, "082540F9", "082140F9", True),  # I1 sub 0x13: send to server -> broadcast
    (0x159B17C, "082540F9", "082140F9", True),  # I1 sub 0xF (reader): send to server -> broadcast
    (0x159B440, "082540F9", "082140F9", True),  # I1 sub 0x10 (reader): send to server -> broadcast
    (0x159C9D0, "082540F9", "082140F9", True),  # I1 sub 3 (dead path): send to server -> broadcast
    (0x159C704, "482E02B0", "689C01D0", True),  # I3 create only on authority
    (0x159C708, "081146F9", "08617F39", True),  # I3 create only on authority
    (0x159C70C, "08696F39", "1F2003D5", True),  # I3 create only on authority
    (0x159C710, "68180034", "68180035", True),  # I3 create only on authority
    (0x15A3D40, "000B0054", "1F2003D5", True),  # I4a server create runs in mode 6
    (0x15A3E4C, "50FEFF97", "C7690295", True),  # I4b bl cave_push
    (0x15A4204, "08240034", "1F2003D5", True),  # I5 award block runs online
    (0x15A42B0, "081300B4", "9C680215", True),  # I6b b cave_m6a
    (0x15A4484, "680400B4", "30680215", True),  # I6c b cave_m6b
    (0x15A55F4, "40040054", "1F2003D5", True),  # I7 remove broadcast in mode 6
    (0x1597400, "81000054", "409C0215", True),  # I2 b cave_f (filter, apply last)
]
ITEMS_3 = [  # ITEMS-3 event creators (optional)
    (0x15AE9C0, "A82D02F0", "E89B0190", True),  # I8 event creator 0x15ae9c0 authority only
    (0x15AE9C4, "081146F9", "08617F39", True),  # I8 event creator 0x15ae9c0 authority only
    (0x15AE9C8, "08696F39", "1F2003D5", True),  # I8 event creator 0x15ae9c0 authority only
    (0x15AE9CC, "C8060034", "C8060035", True),  # I8 event creator 0x15ae9c0 authority only
    (0x15AF3CC, "A82D02D0", "C89B01F0", True),  # I8 event creator 0x15af3cc authority only
    (0x15AF3D0, "081146F9", "08617F39", True),  # I8 event creator 0x15af3cc authority only
    (0x15AF3D4, "08696F39", "1F2003D5", True),  # I8 event creator 0x15af3cc authority only
    (0x15AF3D8, "E8140034", "E8140035", True),  # I8 event creator 0x15af3cc authority only
    (0x15AA050, "C82D02F0", "089C0190", True),  # I8 event creator 0x15aa050 authority only
    (0x15AA054, "081146F9", "08617F39", True),  # I8 event creator 0x15aa050 authority only
    (0x15AA058, "08696F39", "1F2003D5", True),  # I8 event creator 0x15aa050 authority only
    (0x15AA05C, "88370034", "88370035", True),  # I8 event creator 0x15aa050 authority only
]
LEVERS = [  # LEVERS (A1-A4)
    (0x0D68FC0, "082540F9", "082140F9", True),  # A1 0x97 send -> broadcast
    (0x0D68658, "083140F9", "082940F9", True),  # A2 0x97 read from anyone
    (0x0D67348, "092949F9", "08DE01F0", True),  # A3 kind 0 decided by authority
    (0x0D6734C, "082549F9", "08617F39", True),  # A3 kind 0 decided by authority
    (0x0D67350, "280108CB", "68110035", True),  # A3 kind 0 decided by authority
    (0x0D67354, "E97B8F52", "06000014", True),  # A3 kind 0 decided by authority
    (0x0D67CD8, "E86F02D0", "08DE01F0", True),  # A4 release sent by authority
    (0x0D67CDC, "081146F9", "08617F39", True),  # A4 release sent by authority
    (0x0D67CE0, "08696F39", "1F2003D5", True),  # A4 release sent by authority
    (0x0D67CE4, "88010034", "88010035", True),  # A4 release sent by authority
]
MARKERS = [  # MARKERS
    (0x0F91218, "88060034", "1F2003D5", True),  # M1 producer runs online
    (0x4C4B8F0, "60", "40", False),  # M2 routing 0xA8: 0x60 -> 0x40
]
FINISH = [  # FINISH 0x76
    (0x1137ED8, "083140F9", "082940F9", True),  # F1 0x76 read from anyone
]

ORDER = [ITEMS_1, ITEMS_2, LEVERS, MARKERS, FINISH]  # ITEMS_3 optional, after ITEMS_2
