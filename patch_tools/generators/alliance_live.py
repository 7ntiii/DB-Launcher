"""Paste-ready patch records: (offset_from_main, orig_hex, new_hex, is_code). Bytes are little-endian as in memory.

Remaining alliance work after group A (ALLY_SEND_ALL 0x10AF424, routing 0x4C4B600, ACCEPT_LOCAL 0x10B5D38,
ACCEPT_NOCHECK 0x10AFA78, FORM_GUEST 0x10AD748, NO_4B_WIRE 0x10B07B4), which is shipped.
Every original word was re-read from diag/net/nso/main_text.bin and every new word decoded with capstone
at its own address (script + output: scratchpad alv_verify.py / alv_verify.txt). All records are 4-byte code words.
Details and the message tables: diag/net/alliance_notes.md.

Shared facts:
- "mode 6" = mgr3(*(main+0x5B3CE08))+0x1268 == 6 (online guest). Offline (bots) has mode != 6 and bda = 1, so a
  "cmp #6 -> cmp #0xff" or a nop on a "bda == 0" / "mode == 6" branch does not change the offline path.
- Groups DISCARD / MEMBER_GONE / MATCH_END all need NO_4B_WIRE (group A): each game makes the 0x4B result
  itself, nothing goes on the wire.
- MEMBER_GONE and MATCH_END gates are "mode == 6 OR byte main+0x5B65C70 == 2 -> skip" (ccmp #2). The patch only
  removes the mode-6 half. If that byte is 2 in our LAN match the two groups do nothing (read it once first).
"""

# --- DISCARD: end an alliance by choice at the phase change (discard window) -----------------------------
# Before: the hold-to-discard gauge shows, but holding it does nothing; the alliance stays forever.
# After:  at the phase change each game opens the 60 s window as offline does; a player who holds the button
#         sends 0x4A kind 3 to everyone, everyone else (and alliance-less players, auto) sends kind 4 "keep";
#         when all have answered (or 60 s pass) each game dissolves the queued alliances locally (0x4B kind 1,
#         reason 1): HP bar of the ally and team colour go away, "alliance dissolved" notice.
# Offline: unchanged (all five are on mode-6 / bda==0 branches; 0x10B036C only runs when mode == 6).
# Cheapest live check: one-shot bp 0x10ADD60 in a guest match (is the window reached in mode 6, which phase?),
#         then AM(*(main+0x5B3CDD0))+0x118 == 0 and +0x110 bits on both games; after holding: AM+0x38 drops to 0.
# Ship without a live test: no (0x10ADD60 being reached in mode 6 is not verified; a stuck +0x118 = 0 window is
#         harmless, but the timing of the dissolve is untested).
DISCARD = [
    (0x10B036C, "082540F9", "082140F9", True),  # KEEP_SEND_ALL: kind 4 send: ldr x8,[x8,#0x48] (to server) -> [x8,#0x40] (broadcast)
    (0x10B5E34, "29EBFF34", "1F2003D5", True),  # DISCARD_LOCAL: kind 3 handler: cbz w9(bda),#0x10b5b98 -> nop (queue +0x148, mark bit)
    (0x10B5ED4, "29E6FF34", "1F2003D5", True),  # KEEP_LOCAL: kind 4 handler: cbz w9(bda),#0x10b5b98 -> nop (mark bit)
    (0x10ADDE4, "28030034", "1F2003D5", True),  # WINDOW_LOCAL: cbz w8(bda),#0x10ade48 -> nop (+0x118 = 0, bits cleared, 60 s timer)
    (0x10AB380, "00F7FF54", "1F2003D5", True),  # DISSOLVE_GUEST: after cmp mode,#6: b.eq #0x10ab260 -> nop (dissolve queued, reason 1)
]

# --- MEMBER_GONE: a member left / was eliminated -> alliance ends ------------------------------------------
# Before: if an ally disconnects or is flagged out (chr +0x46b2), the alliance entry stays (ally HP bar of a
#         missing player; the pair still counts as allied for the score merge and the pair-win rule below).
# After:  each game dissolves it itself with reason 8 (chr gone) or 7 (flag), same as the host branch.
# Offline: unchanged (cmp #0xff: offline mode is never 6 nor 0xff; the nop is on the mode-6 branch).
# Cheapest live check: read byte main+0x5B65C70 in a match (must not be 2); then ally A, B; kill/quit B's game;
#         AM+0x38 on A goes 1 -> 0 within a frame or two.
# Ship without a live test: yes if byte main+0x5B65C70 != 2 (pure mirror of the host code, no wire traffic);
#         otherwise it is a no-op, also harmless.
MEMBER_GONE = [
    (0x10A9D6C, "3F190071", "3FFD0371", True),  # GONE_GUEST: cmp w9(mode),#6 -> cmp w9,#0xff (host section of the update runs)
    (0x10AA1F8, "E0010054", "1F2003D5", True),  # GONE_DISSOLVE: after cmp mode,#6: b.eq #0x10aa234 -> nop (0x10b06a0 dissolve, reason 7/8)
]

# --- MATCH_END: dissolve every alliance at match end (reason 9) --------------------------------------------
# Before: alliances are not dissolved by 0x10B0500 at match end in mode 6.
# After:  0x10B0500 dissolves all of them on each game (0x4B kind 1, reason 9) -> clean state for the next match.
# Offline: unchanged (cmp #0xff).
# Cheapest live check: ally, finish a match, enter the next one: AM+0x38 at the start of the next match.
#         If it is already 0 (AM rebuilt per match), skip this group.
# Ship without a live test: yes (same pattern as MEMBER_GONE), but it is likely unneeded.
MATCH_END = [
    (0x10B0534, "1F190071", "1FFD0371", True),  # MATCHEND_GUEST: cmp w8(mode),#6 -> cmp w8,#0xff
]

# --- NPC_OFFER: NPC (id 0x989680+n) offers an alliance ------------------------------------------------------
# Before: the NPC event sends 0x4A kind 7 (pre-check) to the server (= self); the online handler ignores it, so
#         the pending pair AM+0x1cc stays set and blocks every later NPC offer (guard 0x10b0bfc); no dialog.
# After:  each game answers its own kind 7 with kind 8 in its local queue -> yes/no dialog opens; "no" clears
#         +0x1cc. "Yes" goes through 0x10ae220 (bot path, formed locally on that game only) -> may diverge from
#         the other games, and in mode 6 the bot auto-answer (0x10b6edc, bda) does not run, so the request
#         may just time out.
# Offline: unchanged (nop on the bda == 0 branch).
# Cheapest live check: trigger an NPC offer, see the dialog, answer no, then trigger another (dialog again).
# Ship without a live test: no (only fixes the hang; "yes" behaviour across games is unknown).
NPC_OFFER = [
    (0x10B5CC0, "C9F6FF34", "1F2003D5", True),  # NPC_PRECHECK_LOCAL: kind 7 handler: cbz w9(bda),#0x10b5b98 -> nop
]

# --- CROSS: guard for observation (2), requests in both directions ----------------------------------------
# Cause: the real server's kind-0 branch (0x10B5C60..0x10B5FEC) checks for the reverse step (+0xb8 == b,
#        +0xbc == a): "B requests A while A->B is pending" = instant accept -> 0x10af9c0 -> form. 0x10ae220 has no
#        such check; it relies on the server. Our games take the online branch (cbz w9 at 0x10B5BE4 ->
#        0x10af600), which only adds a second step, so a "request back" forms nothing.
# Before: A->B and B->A pending, nothing forms (the "accept" was most likely the request gesture back).
# After:  the second request forms the alliance on every game when it arrives (whichever of the two arrives
#         second on that game), exactly like the server. A later accept is refused by 0x10ad600 (already allied).
#         Non-crossing requests: identical to today (0x10af4ac re-send is a no-op when bda == 0, then the
#         same 0x10af600 tail with the same x0/x1).
# Offline: unchanged (bda = 1 already takes this branch; the tbz nop removes the "invalid -> kind 5" reject, so
#         offline an invalid bot request would now be applied: the step just times out). If that matters, ship
#         only the first record (then a request that fails 0x10ae700 on some game is rejected there).
# Cheapest live check: A requests B, B requests A (no accept): AM+0x38 == 1 on both games; bp 0x10B5FEC hits once
#         per game.
# Ship without a live test: yes for 0x10B5BE4 (low risk); the second record is optional (keeps today's "every
#         game applies the request even if its own validity check says no").
CROSS = [
    (0x10B5BE4, "C9200034", "1F2003D5", True),  # CROSS_FORM: kind 0 handler: cbz w9(bda),#0x10b5ffc -> nop (run the server branch)
    (0x10B5C5C, "96190036", "1F2003D5", True),  # CROSS_NOREJECT: tbz w22(valid),#0,#0x10b5f8c -> nop (never reject locally)
]

# --- NO_PAIR_WIN: optional, NOT recommended; only if the lead wants allies in a 2-player test to keep playing --
# Observation (1) is the game's rule, not a side effect (see score manager vt+0x68 = 0xF87C80):
#   collect the score entries with flag +0x42 == 0 (still in); if exactly one is left, or exactly two are left
#   (0xF87D84 cmp x9,#0x10) and they are allied in the AM deque (0xF87E08..0xF87E4C) and
#   !(*(main+0x5B3CDF8)+0xc0 & 0x10), the match is decided: every entry not at stage 4 gets event 2 (still in)
#   or 1 (flagged) via 0x11383e8 -> stage 4 -> vt+0x70 kind 2 -> DefaultTransEndPhase sets match over -> 10 -> 14.
# This record skips only the "two left and allied" test; the last-one-standing and round-limit tests stay.
NO_PAIR_WIN = [
    (0xF87D88, "41060054", "32000014", True),  # b.ne #0xf87e50 -> b #0xf87e50 (never treat an allied last pair as the winner)
]

# Recommended order: CROSS[0] now; MEMBER_GONE after reading main+0x5B65C70; DISCARD after the 0x10ADD60 bp check;
# MATCH_END only if AM+0x38 survives into the next match; NPC_OFFER last; NO_PAIR_WIN only for 2-player tests.
