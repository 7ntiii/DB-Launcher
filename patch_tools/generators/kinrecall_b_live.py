"""kinrecall_b_gen.py (helper 4 review of kinrecall_gen.py, audit_new_groups_notes.md): a kin recalled from the Function Menu (hold Y + Down) always leaves; re-summon works after it
(static generator, kin6_notes.md). Reads nso/*.bin, patch_manager.cpp and every *_live.py through cave_lib.
Writes kinrecall_b_live.py (replaces kinrecall_live.py: the same KREC row and trampoline; only the cave words
differ).
python kinrecall_b_gen.py [--dry]      (from diag/net; --dry = check and print only, write nothing)

REGISTRY: allocated with Gen(dry=True); cave_registry.md is NOT written. The lead adds the printed rows.

Why (2-game run 2026-11-16, kin_recall FAIL: B (guest owner) 3 -> 4 RequestUnsummon and stuck there; A stays 3)
[V code below, kin6_notes.md 1]:
- The whole recall is decided on the OWNER's game; no message is sent for state 4, no host and no server answer:
  SummonState 0xD83360 -> 4 on the owner; RequestUnsummon 0xD83874 sets the per-frame request bit
  [[kin+0x2470]+0]+0x14C8 bit 1 (cleared every frame by 0x1904220) = HKS env IsBuddyUnsummonRequestReceived
  (0xAB00DC) and waits for the KIN'S OWN ANSWER: 0xD8375C (kin action 0x1B8 and an owner-target condition), or
  the kin chr's dead / disappear bit [[kin+0x18]+0x30]+0x18 bit 0, or step cc bits 2 / 3 (0x54 kind 1 or 0xE839DC).
  Only after that -> 8 FinishUnsummon: the owner sets step+0xD0 bits 1 | 0, the BM update 0xE80E20 hides the chr
  (BM vt+0x48 0xE84C60) and sends 0x54 kind 1 (BM vt+0x38 0xE851E0 on the others: cc bit 3 -> their 3 -> 8), then
  9 WaitRevive -> 0x54 kind 2 -> 2 on every game. Re-summon: UnsummonState 0xD82FC0 on the owner (action 0x165)
  -> kin vt+0x8F0 -> 3, 0x54 kind 0 (0xE84FC0) -> 3 on the others. 0x54 is sent with send vt+0x40 (every member)
  and read from anyone: nothing of it is server-only.
- So the stuck request is the kin's behaviour never giving its answer on the owner's game (live: 12 s, an enemy
  near) [I: either the stock in-combat wait or the behaviour not completing on that copy; the host-owner run of
  kin_recall tells which].
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

KINRECALL_CAVE = [  # FAR cave records
    (0xC502BC0, "00000000", "10B3FCF0", True),
    (0xC502BC4, "00000000", "101246F9", True),
    (0xC502BC8, "00000000", "106A6F39", True),
    (0xC502BCC, "00000000", "B0030035", True),
    (0xC502BD0, "00000000", "705E40F9", True),
    (0xC502BD4, "00000000", "700300B4", True),
    (0xC502BD8, "00000000", "101240F9", True),
    (0xC502BDC, "00000000", "300300B4", True),
    (0xC502BE0, "00000000", "11BA40B9", True),
    (0xC502BE4, "00000000", "D0B1FCD0", True),
    (0xC502BE8, "00000000", "10C646F9", True),
    (0xC502BEC, "00000000", "B00200B4", True),
    (0xC502BF0, "00000000", "10D640F9", True),
    (0xC502BF4, "00000000", "700200B4", True),
    (0xC502BF8, "00000000", "003A52F9", True),
    (0xC502BFC, "00000000", "000040F9", True),
    (0xC502C00, "00000000", "600000B4", True),
    (0xC502C04, "00000000", "00404039", True),
    (0xC502C08, "00000000", "C0013037", True),
    (0xC502C0C, "00000000", "101240F9", True),
    (0xC502C10, "00000000", "900100B4", True),
    (0xC502C14, "00000000", "107A40B9", True),
    (0xC502C18, "00000000", "1F02116B", True),
    (0xC502C1C, "00000000", "21010054", True),
    (0xC502C20, "00000000", "200840BD", True),
    (0xC502C24, "00000000", "61E240BD", True),
    (0xC502C28, "00000000", "2128201E", True),
    (0xC502C2C, "00000000", "61E200BD", True),
    (0xC502C30, "00000000", "1018A852", True),
    (0xC502C34, "00000000", "0002271E", True),
    (0xC502C38, "00000000", "2020201E", True),
    (0xC502C3C, "00000000", "AA000054", True),
    (0xC502C40, "00000000", "E00313AA", True),
    (0xC502C44, "00000000", "1044FAB0", True),
    (0xC502C48, "00000000", "10B22291", True),
    (0xC502C4C, "00000000", "00021FD6", True),
    (0xC502C50, "00000000", "7FE200B9", True),
    (0xC502C54, "00000000", "1044FAB0", True),
    (0xC502C58, "00000000", "10622391", True),
    (0xC502C5C, "00000000", "00021FD6", True),
    (0xD06DCC, "00000000", "F0BF0590", True),
    (0xD06DD0, "00000000", "10022F91", True),
    (0xD06DD4, "00000000", "00021FD6", True),
]
KINRECALL_HOOK = [
    (0xD838A8, "E00313AA", "490DFE17", True),
]

ORDER = [KINRECALL_CAVE, KINRECALL_HOOK]
HOLD_WORD_AT = 0xC502C08  # tbnz w0, #6 (owner hold kept); nop = kinrecall_gen behaviour
CAVES = {'KREC': 0xC502BC0}
SITE = 0xD838A8
HOOK_WORD = 0x17FE0D49
SECS = 6.0
SECS_WORD_AT = 0xC502C30  # movz w16, #hi16(float secs), lsl #16: live tuning
