"""cutvote_gen.py: road_to_100 row 55, cutscene skip by vote (cutscene_vote_notes.md). Static generator: reads
nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib. Writes cutvote_live.py.
python cutvote_gen.py [--dry]
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

CUTSCENE_VOTE = [
    (0x11B932C, "610C0054", "610C0054", True),
    (0x11B9330, "680240B9", "63000014", True),
]

ORDER = [CUTSCENE_VOTE]
