"""power46a_gen.py: POWER46A, alpha reconstruction (alpha_reconstructions.md b). Writes power46a_live.py.
python power46a_gen.py [--dry]      (from diag/net)
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

POWER46A = [
    (0x1012618, "E8979F1A", "28008052", True),
    (0x1019468, "087B7678", "28008052", True),
    (0x10194A0, "0A7B7678", "2A008052", True),
]

ORDER = [POWER46A]
