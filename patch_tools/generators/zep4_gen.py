"""zep4_gen.py -> zep4_live.py: ZEP4_SEND (zeppelin 0x9E request / answer to the PLAYERS, not to the server link).
Static only. python zep4_gen.py [--dry]   (from diag/net)

Why [V]: the 0x9E send block 0xF107FC..0xF108E0 (used by a guest's request after ZEP_S3 and by ZEP3_C3's kind-1
answer, which jumps to 0xF107FC) sends with transport vt+0x48 = 0x1CD8220 "send to the server": member
mgr3+0x658 (server link) when connected. With the shipped LAN setup (launcher DUSK_P2P_FORMAT=self) every game's
server link is ITSELF, so a guest's request never reaches the host and C3's answer never reaches a guest; the
receiver drops its own copy (ZEP_S4 guest / ZEP_S6 host). The twin rig uses 'cross' (server link = the other
game), which hides this with two games and breaks with three.
Fix: 0xF108DC `ldr x8,[x8,#0x48]` (F9402508) -> `ldr x8,[x8,#0x40]` (F9402108) = vt+0x40 0x1CD8008 broadcast
(thunk: x0 -= 0x10, w4 = 0, -> 0x1CD7C80, same x0..w3 as the send) routed by the 0x9E attribute, which ZEP_S2
already set to 0x20 = players only (members with +0xE0 == 0, i.e. not the server link). The receiver 0xF11E58 is
vt+0x50 "from anyone" [V], so the host takes a guest's kind 0 and a guest takes the host's kind 1.
Copies [I]: with mgr3+0x668 == 0 the routing is skipped and the broadcast also reaches the server link (= self or,
in the rig, the other game a second time): a game's own kind 0 / kind 1 is dropped by S4 / S6; a second kind 0 at
the host updates the same queue entry or (later frame) is decided again and denied (ship busy, 0xF11734); a
second kind 1 on a guest is dropped by ZEP3_D1 (ship busy). One request = one strike.
Same record on every game. 0xF108DC is not a built-in record today, so stock == live orig (ZEP4_SEND_LIVE = same).
"""
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TXT = open(os.path.join(HERE, 'nso', 'main_text.bin'), 'rb').read()
CPP = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')

RECS = [(0xF108DC, 0xF9402508, 0xF9402108, 'ldr x8,[x8,#0x48] -> ldr x8,[x8,#0x40] (0x9E: server link -> broadcast)')]
# ZEP4_NOPH (2026-11-15, zeppelin4_notes 7): the 0x9F reader (pump 0xF0C858..0xF0C8EC) appends a placeholder
# strike {player, +4 0, +0x1C 0, ship 0xFFFF} when no strike of that player exists. With the self link every
# requester hears its OWN 0x9F after its strike was erased -> a stale "pN w0 r0 sffff pend0" that the next kind-1 /
# decision UPDATES (+4 stays 0): that game fires at once and never sends 0x9F, so the host's strike waits forever.
# Fix: 0x9F without a strike is ignored (b.eq to the loop's next message 0xF0C900, as the found path 0xF0C88C).
NOPH = [(0xF0C884, 0x54000060, 0x540003E0, 'b.eq #0xf0c890 -> b.eq #0xf0c900 (0x9F: no placeholder strike)')]
# ZEP4_END (zeppelin4_notes 9): the airship AI's attack report 0xA0 (sender 0xF10B..: 0xF10BEC) and volley end 0xA1
# (sender 0xF10D60: 0xF10F34) go with vt+0x48 "send to the server" = the self link -> only the driving game (host)
# ever reads them (reader 0xF0CEF4 / 0xF0D1F4, vt+0x58 any). The relay that would forward them (0xF0D3E8 / 0xF0D124
# vt+0x40) runs only when mode != 6. So a guest copy made busy by the host's strike is never cleared.
# Fix: both sends -> vt+0x40 broadcast (thunk w4 = 0; attribute 0x00 = every member incl. the self link, as 0x9F).
END = [(0xF10BEC, 0xF9402508, 0xF9402108, 'ldr x8,[x8,#0x48] -> #0x40 (0xA0 attack report: self link -> broadcast)'),
       (0xF10F34, 0xF9402508, 0xF9402108, 'ldr x8,[x8,#0x48] -> #0x40 (0xA1 volley end: self link -> broadcast)')]
# ZEP4_ROUTE (zeppelin4_notes 9.2): 0x9E attribute (ro 0x4C4B8A0) 0x20 players-only (members with +0xE0 == 0) ->
# 0x00 every member, the attribute of 0x9F / 0xA0 / 0xA1 / 0x4E whose broadcasts are seen to arrive. Stock 0x40,
# built in (ZEP_S2) 0x20: stock record ZEP4_ROUTE (40 -> 00, bake: UPDATE of DUSK_W_4C4B8A0), live ZEP4_ROUTE_LIVE
# (20 -> 00). Own copies: kind 0 on a guest -> ZEP_S4 drops, kind 1 on the host -> ZEP_S6 drops.
ROUTE = (0x4C4B8A0, 0x40, 0x20, 0x00)
# context that must be stock (send block): mov w1,#0x9e ; mov w3,w20 ; (site) ; blr x8
CTX = [(0xF108D4, 0x528013C1), (0xF108D8, 0x2A1403E3), (0xF108E0, 0xD63F0100),
       # 0x9F reader: cmp x10,x8 (site) / strb wzr,[x10,#4] / b #0xf0c900 ; loop continue 0xF0C900 adrp x8
       (0xF0C880, 0xEB08015F), (0xF0C888, 0x3900115F), (0xF0C88C, 0x1400001D),
       # 0xA0 / 0xA1 senders: mov w1,#0xa0|#0xa1 ; mov w3,w20 ; (site) ; blr x8 ; x0 = mgr3+0x10 (0xF10BA8 / 0xF10EEC)
       (0xF10BE4, 0x52801401), (0xF10BE8, 0x2A1403E3), (0xF10BF0, 0xD63F0100), (0xF10BA8, 0x91004273),
       (0xF10F2C, 0x52801421), (0xF10F30, 0x2A1403E3), (0xF10F38, 0xD63F0100), (0xF10EEC, 0x91004273)]
RO = open(os.path.join(HERE, 'nso', 'main_ro.bin'), 'rb').read()
assert struct.unpack_from('<I', RO, ROUTE[0] - 4 - 0x492B000)[0] == 0x9E and RO[ROUTE[0] - 0x492B000] == ROUTE[1]


def word(off):
    return struct.unpack_from('<I', TXT, off)[0]


def hx(w):
    return struct.pack('<I', w).hex().upper()


def main():
    for off, w in CTX:
        assert word(off) == w, 'context %#x: %08X != %08X' % (off, word(off), w)
    cpp = open(CPP, encoding='utf-8', errors='replace').read()

    def built_in(off):
        m = re.search(r'DUSK_W_%X\{([^}]*)\}' % off, cpp)
        return bytes(int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]+)', m.group(1))).hex().upper() if m else None

    for off, orig, new, _ in RECS + NOPH + END:
        assert word(off) == orig, 'stock %#x: %08X' % (off, word(off))
    for off, *_ in END:
        assert built_in(off) is None, 'already a built-in record at %#x' % off
    assert built_in(ROUTE[0]) == '%02X' % ROUTE[2], 'ZEP_S2 built-in byte changed: %s' % built_in(ROUTE[0])
    # ZEP4_SEND may be built in already (v3.6) but only with its own word; ZEP4_NOPH must not be built in yet.
    for off, orig, new, _ in RECS:
        b = built_in(off)
        assert b in (None, hx(new)), 'built-in %#x has %s' % (off, b)
    for off, *_ in NOPH:
        assert built_in(off) is None, 'already a built-in record at %#x' % off
    others = []
    for fn in os.listdir(HERE):
        if fn.endswith('_live.py') and fn != 'zep4_live.py':
            s = open(os.path.join(HERE, fn), encoding='utf-8', errors='replace').read()
            for off, *_ in RECS + NOPH + END:
                if re.search(r'\(0x0*%X\s*,' % off, s, re.I):
                    others.append((fn, hex(off)))
    assert not others, others

    def rows(rs):
        return ',\n'.join('    (0x%X, "%s", "%s", True),  # %s' % (off, hx(o), hx(n), c) for off, o, n, c in rs)
    out = ('"""ZEP4 groups for the zeppelin event 1120. Generated by zep4_gen.py (stock words + context checked).\n'
           '(offset_from_main, orig_hex, new_hex, is_code). Apply on EVERY game, after ZEP_S1..S6 and the ZEP3 groups.\n'
           'ZEP4_SEND (built in since v3.6): 0x9E request / answer as a players broadcast (zeppelin4_notes 6).\n'
           'ZEP4_NOPH: the 0x9F reader no longer creates placeholder strikes (zeppelin4_notes 7). NOT live-tested."""\n\n'
           'ZEP4_SEND = [\n%s\n]\n'
           '# 0xF108DC: built in (v3.6) with the new word; on such a build ZEP4_SEND_LIVE is already applied.\n'
           'ZEP4_SEND_LIVE = list(ZEP4_SEND)\n\n'
           'ZEP4_NOPH = [\n%s\n]\n'
           '# 0xF0C884 is not a built-in record: the live orig is the stock word.\n'
           'ZEP4_NOPH_LIVE = list(ZEP4_NOPH)\n\n'
           'ZEP4_END = [\n%s\n]\n'
           '# 0xF10BEC / 0xF10F34 are not built-in records: the live orig is the stock word.\n'
           'ZEP4_END_LIVE = list(ZEP4_END)\n\n'
           '# 0x4C4B8A0 (ro) 0x9E attribute -> 0x00 every member. Stock record (bake: UPDATE of ZEP_S2, do not give\n'
           '# ZEP_S2 in the same bake set); the live variant starts from the built-in 0x20.\n'
           'ZEP4_ROUTE = [\n    (0x%X, "%02X", "%02X", False),  # 0x9E attribute stock 0x40 -> 0x00\n]\n'
           'ZEP4_ROUTE_LIVE = [\n    (0x%X, "%02X", "%02X", False),  # 0x9E attribute built-in 0x20 -> 0x00\n]\n'
           % (rows(RECS), rows(NOPH), rows(END), ROUTE[0], ROUTE[1], ROUTE[3], ROUTE[0], ROUTE[2], ROUTE[3]))
    if '--dry' in sys.argv:
        print(out)
        return
    open(os.path.join(HERE, 'zep4_live.py'), 'w', newline='\n').write(out)
    print('wrote zep4_live.py:', ', '.join('%#x %s -> %s' % (o, hx(a), hx(b)) for o, a, b, _ in RECS + NOPH + END),
          '+ ROUTE %#x' % ROUTE[0])


if __name__ == '__main__':
    main()
