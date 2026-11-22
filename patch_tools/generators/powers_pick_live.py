"""powers_pick_gen.py: the "Select what to receive" dialog gives the chosen entry in a LAN match (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py (through cave_lib). Writes powers_pick_live.py and claims its
far ranges in cave_registry.md (owner `powers_pick_gen`).
python powers_pick_gen.py [--dry]      (from diag/net; --dry = check and print only, claim / write nothing)
Notes: powers3_notes.md (sections 1-4 = trace, 8 = this group).

GFLAG = main+0xC50F27C.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

POWERS_PICK_CAVE = [  # FAR cave records
    (0xC501B58, "00000000", "88000034", True),
    (0xC501B5C, "00000000", "B085FAD0", True),
    (0xC501B60, "00000000", "10723C91", True),
    (0xC501B64, "00000000", "00021FD6", True),
    (0xC501B68, "00000000", "E10300F9", True),
    (0xC501B6C, "00000000", "E40B00B9", True),
    (0xC501B70, "00000000", "E00313AA", True),
    (0xC501B74, "00000000", "811240B9", True),
    (0xC501B78, "00000000", "1085FAB0", True),
    (0xC501B7C, "00000000", "10820C91", True),
    (0xC501B80, "00000000", "00023FD6", True),
    (0xC501B84, "00000000", "800000B5", True),
    (0xC501B88, "00000000", "B085FAD0", True),
    (0xC501B8C, "00000000", "10C23E91", True),
    (0xC501B90, "00000000", "00021FD6", True),
    (0xC501B94, "00000000", "E10340F9", True),
    (0xC501B98, "00000000", "E40B40B9", True),
    (0xC501B9C, "00000000", "690000D0", True),
    (0xC501BA0, "00000000", "2A008052", True),
    (0xC501BA4, "00000000", "2AF10939", True),
    (0xC501BA8, "00000000", "89424039", True),
    (0xC501BAC, "00000000", "0A008012", True),
    (0xC501BB0, "00000000", "E00313AA", True),
    (0xC501BB4, "00000000", "280040B9", True),
    (0xC501BB8, "00000000", "E4AB0229", True),
    (0xC501BBC, "00000000", "E1430091", True),
    (0xC501BC0, "00000000", "830E40F9", True),
    (0xC501BC4, "00000000", "E7031FAA", True),
    (0xC501BC8, "00000000", "220D0012", True),
    (0xC501BCC, "00000000", "84824039", True),
    (0xC501BD0, "00000000", "851640F9", True),
    (0xC501BD4, "00000000", "E81300B9", True),
    (0xC501BD8, "00000000", "86C64039", True),
    (0xC501BDC, "00000000", "B085FA90", True),
    (0xC501BE0, "00000000", "10021091", True),
    (0xC501BE4, "00000000", "00023FD6", True),
    (0xC501BE8, "00000000", "690000D0", True),
    (0xC501BEC, "00000000", "3FF10939", True),
    (0xC501BF0, "00000000", "B085FAD0", True),
    (0xC501BF4, "00000000", "10A23D91", True),
    (0xC501BF8, "00000000", "00021FD6", True),
    (0xC501840, "00000000", "E80000B4", True),
    (0xC501844, "00000000", "690000D0", True),
    (0xC501848, "00000000", "29F14939", True),
    (0xC50184C, "00000000", "89000035", True),
    (0xC501850, "00000000", "B085FA90", True),
    (0xC501854, "00000000", "10921591", True),
    (0xC501858, "00000000", "00021FD6", True),
    (0xC50185C, "00000000", "B085FA90", True),
    (0xC501860, "00000000", "10F21F91", True),
    (0xC501864, "00000000", "00021FD6", True),
    (0x15A1308, "00000000", "107B0590", True),
    (0x15A130C, "00000000", "10622D91", True),
    (0x15A1310, "00000000", "00021FD6", True),
    (0x15A1314, "00000000", "107B0590", True),
    (0x15A1318, "00000000", "10022191", True),
    (0x15A131C, "00000000", "00021FD6", True),
]
POWERS_PICK = [
    (0x15B7F18, "88030034", "FCA4FF17", True),
    (0x15B5560, "E81400B4", "6DAFFF17", True),
]

ORDER = [POWERS_PICK_CAVE, POWERS_PICK]
CAVES = {'PICK': 0xC501B58, 'GIVE': 0xC501840, 'GFLAG': 0xC50F27C, 'TR_PICK': 0x15A1308, 'TR_GIVE': 0x15A1314}
