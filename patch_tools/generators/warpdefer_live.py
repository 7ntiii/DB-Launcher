"""warpdefer_gen.py: WARPDEFER (v4.50, alpha 11): hold the guest's own start-point warp until the final's world is
loaded. Static generator, Gen(dry=True): cave_registry.md is NOT written (rows printed). Writes warpdefer_live.py.
python warpdefer_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

WARPDEFER_CAVE = [  # FAR cave records
    (0xC504338, "00000000", "CAD20510", True),
    (0xC50433C, "00000000", "50014039", True),
    (0xC504340, "00000000", "D0000034", True),
    (0xC504344, "00000000", "500540B9", True),
    (0xC504348, "00000000", "10060011", True),
    (0xC50434C, "00000000", "500500B9", True),
    (0xC504350, "00000000", "08008052", True),
    (0xC504354, "00000000", "02000014", True),
    (0xC504358, "00000000", "08696938", True),
    (0xC50435C, "00000000", "905FFA90", True),
    (0xC504360, "00000000", "10920191", True),
    (0xC504364, "00000000", "00021FD6", True),
    (0xC504368, "00000000", "4AD10510", True),
    (0xC50436C, "00000000", "50014039", True),
    (0xC504370, "00000000", "D0000034", True),
    (0xC504374, "00000000", "500940B9", True),
    (0xC504378, "00000000", "10060011", True),
    (0xC50437C, "00000000", "500900B9", True),
    (0xC504380, "00000000", "08008052", True),
    (0xC504384, "00000000", "02000014", True),
    (0xC504388, "00000000", "08696938", True),
    (0xC50438C, "00000000", "505FFAF0", True),
    (0xC504390, "00000000", "10A22191", True),
    (0xC504394, "00000000", "00021FD6", True),
    (0x1074EE4, "00000000", "90A40590", True),
    (0x1074EE8, "00000000", "10E20C91", True),
    (0x1074EEC, "00000000", "00021FD6", True),
    (0x1077814, "00000000", "70A405B0", True),
    (0x1077818, "00000000", "10A20D91", True),
    (0x107781C, "00000000", "00021FD6", True),
]
WARPDEFER = [
    (0x10F4060, "08696938", "A103FE17", True),
    (0x10EF864, "08696938", "EC1FFE17", True),
]

ORDER = [WARPDEFER_CAVE, WARPDEFER]
