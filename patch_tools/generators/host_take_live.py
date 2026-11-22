"""host_take_gen.py: the LAN host takes its OWN Power drop locally, without the self-link round trip (static generator).
Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes host_take_live.py.
python host_take_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)
Notes: pickup4_notes.md section 3. Needs PICKUP_ADD2 (pickup_gen2.py) for the inventory add.

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

HOST_TAKE_CAVE = [  # FAR cave records
    (0xC501F54, "00000000", "1F190071", True),
    (0xC501F58, "00000000", "80000054", True),
    (0xC501F5C, "00000000", "1085FAF0", True),
    (0xC501F60, "00000000", "10B22691", True),
    (0xC501F64, "00000000", "00021FD6", True),
    (0xC501F68, "00000000", "5021FCB0", True),
    (0xC501F6C, "00000000", "10627F39", True),
    (0xC501F70, "00000000", "30030035", True),
    (0xC501F74, "00000000", "910E0012", True),
    (0xC501F78, "00000000", "3F260071", True),
    (0xC501F7C, "00000000", "C1020054", True),
    (0xC501F80, "00000000", "B0B2FCD0", True),
    (0xC501F84, "00000000", "105E47F9", True),
    (0xC501F88, "00000000", "700200B4", True),
    (0xC501F8C, "00000000", "111640F9", True),
    (0xC501F90, "00000000", "710000B5", True),
    (0xC501F94, "00000000", "111240F9", True),
    (0xC501F98, "00000000", "F10100B4", True),
    (0xC501F9C, "00000000", "31D240B9", True),
    (0xC501FA0, "00000000", "310E0012", True),
    (0xC501FA4, "00000000", "91010034", True),
    (0xC501FA8, "00000000", "907E1B53", True),
    (0xC501FAC, "00000000", "100E0012", True),
    (0xC501FB0, "00000000", "1F02116B", True),
    (0xC501FB4, "00000000", "01010054", True),
    (0xC501FB8, "00000000", "700000D0", True),
    (0xC501FBC, "00000000", "31008052", True),
    (0xC501FC0, "00000000", "11220C39", True),
    (0xC501FC4, "00000000", "F87E4092", True),
    (0xC501FC8, "00000000", "1085FAF0", True),
    (0xC501FCC, "00000000", "10F22791", True),
    (0xC501FD0, "00000000", "00021FD6", True),
    (0xC501FD4, "00000000", "1085FAF0", True),
    (0xC501FD8, "00000000", "10022691", True),
    (0xC501FDC, "00000000", "00021FD6", True),
    (0xC502240, "00000000", "700000B0", True),
    (0xC502244, "00000000", "11224C39", True),
    (0xC502248, "00000000", "B1000034", True),
    (0xC50224C, "00000000", "1F220C39", True),
    (0xC502250, "00000000", "1085FAD0", True),
    (0xC502254, "00000000", "10722E91", True),
    (0xC502258, "00000000", "00021FD6", True),
    (0xC50225C, "00000000", "81000054", True),
    (0xC502260, "00000000", "1085FAD0", True),
    (0xC502264, "00000000", "10423391", True),
    (0xC502268, "00000000", "00021FD6", True),
    (0xC50226C, "00000000", "1085FAD0", True),
    (0xC502270, "00000000", "10722E91", True),
    (0xC502274, "00000000", "00021FD6", True),
    (0x15656E4, "00000000", "F07C0590", True),
    (0x15656E8, "00000000", "10523D91", True),
    (0x15656EC, "00000000", "00021FD6", True),
    (0x15656F0, "00000000", "F07C05B0", True),
    (0x15656F4, "00000000", "10020991", True),
    (0x15656F8, "00000000", "00021FD6", True),
]
HOST_TAKE = [
    (0x15A4978, "1F190071", "5B03FF17", True),
    (0x15A4B98, "C0090054", "D602FF17", True),
]

ORDER = [HOST_TAKE_CAVE, HOST_TAKE]
CAVES = {'HTAKE': 0xC501F54, 'HAWARD': 0xC502240, 'HFLAG': 0xC50F308, 'TR': 0x15656E4}
NEEDS = ['PICKUP_ADD2']
