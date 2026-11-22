"""rewardonce_gen.py: REWARDONCE (alpha 13 fire fix). Static generator. Writes rewardonce_live.py.
python rewardonce_gen.py [--dry]   (from diag/net)
The final coordinator 0x116A6A0 (UpdatePhase of the last phase; host only through the shipped 0x116ACE0 record)
lists every frame the dead players with no respawn whose pgd+0x46B0 stage byte is 1 (collector 0x116C638),
hands them to its death list vt+0x98 and then, per listed player, gives the phase reward 0x15AA020(MapItemMan,
&player_no, vt+0xB8()) at 0x116B810. Stock (server) the death list's deque entry is consumed at once and the
player's stage leaves 1, so the list holds it for one frame and the reward is given once. In LAN the deque is
consumed only when the assist feeds the player (FINALOUT, never for our own player, v418, and never for the
last two), so the host gave the reward every frame (~14/s), and cave_push broadcast each item: the fire.
REWARDONCE: the call at 0x116B810 goes through a cave that gives the reward at most once per player number per
final: RObox u32 mask (bit = player no 0..31; numbers >= 32 are given as stock), u32 gives, u32 skips.
The assist clears the box at every final reset (FinalReset).
Cave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as
BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""

REWARDONCE_CAVE = [  # FAR cave records
    (0xC5046AC, "00000000", "290040B9", True),
    (0xC5046B0, "00000000", "3F810071", True),
    (0xC5046B4, "00000000", "82010054", True),
    (0xC5046B8, "00000000", "4A910510", True),
    (0xC5046BC, "00000000", "4B0140B9", True),
    (0xC5046C0, "00000000", "6C25C91A", True),
    (0xC5046C4, "00000000", "6C010037", True),
    (0xC5046C8, "00000000", "2C008052", True),
    (0xC5046CC, "00000000", "8C21C91A", True),
    (0xC5046D0, "00000000", "6B010C2A", True),
    (0xC5046D4, "00000000", "4B0100B9", True),
    (0xC5046D8, "00000000", "4C0540B9", True),
    (0xC5046DC, "00000000", "8C050011", True),
    (0xC5046E0, "00000000", "4C0500B9", True),
    (0xC5046E4, "00000000", "3085FAD0", True),
    (0xC5046E8, "00000000", "10820091", True),
    (0xC5046EC, "00000000", "00021FD6", True),
    (0xC5046F0, "00000000", "4C0940B9", True),
    (0xC5046F4, "00000000", "8C050011", True),
    (0xC5046F8, "00000000", "4C0900B9", True),
    (0xC5046FC, "00000000", "C0035FD6", True),
    (0x10ED90C, "00000000", "B0A005F0", True),
    (0x10ED910, "00000000", "10B21A91", True),
    (0x10ED914, "00000000", "00021FD6", True),
]
REWARDONCE = [
    (0x116B810, "04FA1094", "3F08FE97", True),
]

ORDER = [REWARDONCE_CAVE, REWARDONCE]
