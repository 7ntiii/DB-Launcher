"""Paste-ready patch records for the social features: (offset_from_main, orig_hex, new_hex, is_code).
Bytes are little-endian as in memory. Every orig was re-read from nso/main_text.bin / main_ro.bin and every new
code word decoded with capstone at its address (scratch gen_social.py / gen_social2.py).
Cave records have orig "00000000" (zero padding past the ro file end, main+0x563E45C..0x563F000);
this file uses 0x563E600..0x563E63B only. Apply each group in list order; the enabling hook is last.
Details: summon_struggle_notes.md sections 2-4."""

# JOINT_STRUGGLE (0x59). No cave.
# Player before: joining / recruiting into a joint struggle (RequestJointStruggleWarp, recruit entry) hangs in
#   WaitReceiveAllowJoinWarp; participant list never updates on the other game.
# Player after: the requester's own game acts as server for its own request (decides, applies, broadcasts kind 4/6);
#   the join warp proceeds; the other game adds the participant.
# Live check: send trace type 0x59, first byte low nibble 8 (join request) or 3, then a broadcast 0x59 kind 4.
#   Memory: requester's recruit step leaves WaitReceiveAllowJoinWarp.
# Offline: J1-J3 patch the mode-6 jump table (ro 0x4C490FC), used only when mode == 6 -> stock offline.
#   J4 is reached only when session members (mgr3+0x1248..0x1250) >= 1 -> stock offline (0 members).
# SHIP? NO without a live test: two games can each decide (limits checked per game), and the kind-6 apply
#   (0x1025260) was not checked for double apply (local apply + self echo). Feature must also be reachable in the test.
JOINT_STRUGGLE = [
    (0x1023574, "6B2D8152", "6B288152", True),  # J4 authority mask 0x96B -> 0x943: accept result kinds 4/6 from peers  [mov w11, #0x96b -> mov w11, #0x943]
    (0x4C49102, "5201", "1701", False),  # J1 mode-6 table: kind 3 (entry request) -> server handler 0x1023A2C
    (0x4C49106, "5201", "2801", False),  # J2 mode-6 table: kind 5 request -> server handler 0x1023A70
    (0x4C4910C, "5201", "4601", False),  # J3 mode-6 table: kind 8 (join-warp request) -> server handler 0x1023AE8
]

# FRIENDLY_GROUP (0x91). No cave.
# Player before: group/sub-quest membership changes (kinds 0/1/3 broadcasts, and the mode-6 join request kind 5)
#   are seen only by the acting game; the join request is dropped everywhere (no client handles kind 5).
# Player after: the other game applies the same group state; the join becomes the kind-2 result, applied by
#   every game (own game via the self echo).
# Live check: send trace type 0x91 with first u32 == 2 from the acting game; on the peer the acting chr's
#   [[chr+0x2470]+0x280]+0x18+8*group -> +0x1C == 1.
# Offline: G3 vt+0x60 -> vt+0x50: unconnected both read the local loopback queue (+0x50 also scans members, none)
#   -> same result [I]. G1/G2 are inside the mode == 6 branch (0xE4EE94) -> stock offline.
# SHIP? G3 alone: yes (values are absolute, idempotent). G1+G2: live test first - relies on the self echo
#   for the acting game's own join (if no echo, own game never applies it; fallback in summon_struggle_notes.md).
FRIENDLY_GROUP = [
    (0x0E4EB18, "083140F9", "082940F9", True),  # G3 0x91 read from anyone  [ldr x8, [x8, #0x60] -> ldr x8, [x8, #0x50]]
    (0x0E4EEA0, "AB008052", "4B008052", True),  # G1 mode-6 join request kind 5 -> kind 2 (result format)  [mov w11, #5 -> mov w11, #2]
    (0x0E4EF88, "082540F9", "082140F9", True),  # G2 0x91 join: send to server -> broadcast  [ldr x8, [x8, #0x48] -> ldr x8, [x8, #0x40]]
]

# EQUIP_SKILL (0x5B). Two caves at main+0x563E600 / 0x563E620 (ro padding), single-word hooks applied last.
# Player before: own equip-skill change works (self echo of 0x5B is the answer); other players never see it.
# Player after: 0x5B is broadcast; every game applies {player id, equip data} to that player's PlayerGameData.
# Live check: send trace (hook 0x1CD7C80) type 0x5B from the acting game; on the peer, the acting player's
#   pgd (chr vt+0x298) fields +0xED0 / +0x1C6C / +0x28F0 change after the equip.
# Offline: both hooks are in the connected branch only (after cbz w8 on mgr3+0x18 at 0x14E4E8C / 0x14E4F48)
#   -> stock loopback path offline.
# SHIP? NO without a live test: the apply chain (0xD4E4A0 / 0xD4BEA0 / 0xD49460) on a REMOTE chr was not
#   read for side effects (inventory/UI); 0xA2 at-join push still missing (late joiners).
EQUIP_SKILL = [
    (0x563E620, "00000000", "E2330291", True),  # cave_es_read (0x5B read from anyone)  [add x2, sp, #0x8c]
    (0x563E624, "00000000", "610B8052", True),  # cave_es_read (0x5B read from anyone)  [mov w1, #0x5b]
    (0x563E628, "00000000", "834C8052", True),  # cave_es_read (0x5B read from anyone)  [mov w3, #0x264]
    (0x563E62C, "00000000", "082940F9", True),  # cave_es_read (0x5B read from anyone)  [ldr x8, [x8, #0x50]]
    (0x563E630, "00000000", "E4031FAA", True),  # cave_es_read (0x5B read from anyone)  [mov x4, xzr]
    (0x563E634, "00000000", "00013FD6", True),  # cave_es_read (0x5B read from anyone)  [blr x8]
    (0x563E638, "00000000", "4D9AFA16", True),  # cave_es_read (0x5B read from anyone)  [b #0x14e4f6c]
    (0x563E600, "00000000", "E2B30291", True),  # cave_es_send (0x5B broadcast)  [add x2, sp, #0xac]
    (0x563E604, "00000000", "610B8052", True),  # cave_es_send (0x5B broadcast)  [mov w1, #0x5b]
    (0x563E608, "00000000", "E303042A", True),  # cave_es_send (0x5B broadcast)  [mov w3, w4]
    (0x563E60C, "00000000", "E4031F2A", True),  # cave_es_send (0x5B broadcast)  [mov w4, wzr]
    (0x563E610, "00000000", "9C651A97", True),  # cave_es_send (0x5B broadcast)  [bl #0x1cd7c80]
    (0x563E614, "00000000", "2B9AFA16", True),  # cave_es_send (0x5B broadcast)  [b #0x14e4ec0]
    (0x14E4F50, "E3330291", "B4650515", True),  # E2 hook: connected 0x5B read -> cave_es_read  [add x3, sp, #0x8c -> b #0x563e620]
    (0x14E4E90, "080C41F8", "DC650515", True),  # E1 hook: connected 0x5B send -> cave_es_send  [ldr x8, [x0, #0x10]! -> b #0x563e600]
]

# SPECIAL_REWARD (0x9A). No cave.
# Player before: own reward applies (self echo); other games never apply it to that player.
# Player after: 0x9A broadcast; every game applies 0xD56F74(pgd+0x898, pgd+0x8A8, value) to the pgd of the id in it.
# Live check: send trace type 0x9A from the acting game; peer's copy of that player's pgd+0x898 changes.
# Offline: 0xD573C0 sends only for ids whose member is found in mgr3+0x1248 (empty offline) -> S1 never runs
#   offline; S2 as G3 (loopback either way) -> stock offline.
# SHIP? Prefer a live test: 0xD56F74 not read (set vs add); if it adds, any duplicate delivery doubles a reward.
SPECIAL_REWARD = [
    (0x14E51DC, "082540F9", "082140F9", True),  # S1 0x9A send to server -> broadcast  [ldr x8, [x8, #0x48] -> ldr x8, [x8, #0x40]]
    (0x0D572A0, "083140F9", "082940F9", True),  # S2 0x9A read from anyone  [ldr x8, [x8, #0x60] -> ldr x8, [x8, #0x50]]
]

# Safest first. JOINT_STRUGGLE and EQUIP_SKILL need a live test before shipping (see group comments).
ORDER = [FRIENDLY_GROUP, SPECIAL_REWARD, JOINT_STRUGGLE, EQUIP_SKILL]
