"""READ-ONLY check for the guest loading stall ("player 0x.. has no character here yet: player data asked
for again (#n)", guest stuck at Intermission step 26 round 1). Only Mem.read: no write, no breakpoint, no
code change. Run it on BOTH games while the guest still waits (audit_v392_notes.md section 2):

    python diag/twin/stallcheck.py AB

Per game it prints: session state / loader step / phase, the local player number from both local pgd
pointers (net table +0x20 and +0x28, the order 0x14DC040 and the assist use), the role byte, the message-4
mailbox and the re-request box, every session member (id, slot, link, pending, type-5 seen, remote number),
the slot ready bytes (0x1F = all five answer parts), the pump's deferred-answer list, and the answer
serializer's box (AABB #3) against the own chr position. Then a verdict per waiting member.
Addresses: remote_player_hang_notes.md sections 1, 5b, 5c; selflink_notes.md section 1."""
import struct
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

SESSION_REF = 0x59DFEC8
NET_PLAYERS = 0x5B57EB8
WCM = 0x5B3CD88
STAGE = 0x5B3CDF8
AABB = 0x5B65C38
ROLE = 0x492AFD8
MAILBOX = 0x492AFE0
REREQUEST = 0x492AFF0


class R:
    def __init__(self, m):
        self.m = m

    def q(self, a):
        try:
            return self.m.u64(a) if a else 0
        except Exception:
            return 0

    def d(self, a):
        try:
            return self.m.u32(a) if a else 0
        except Exception:
            return 0

    def b(self, a):
        try:
            return self.m.read(a, 1)[0] if a else 0
        except Exception:
            return 0

    def f(self, a, n):
        try:
            return struct.unpack('<%df' % n, self.m.read(a, 4 * n))
        except Exception:
            return None


def s32(v):
    return v - (1 << 32) if v >= 1 << 31 else v


def game(who):
    m = Mem(who)
    r = R(m)
    base = m.base
    print('== game %s  main %#x' % (who, base))
    mgr = r.q(r.q(base + SESSION_REF))
    stage = r.q(base + STAGE)
    loader = r.q(mgr + 0x14C8) if mgr else 0
    print('  session %#x state %d mode %d loader step %d | phase %d round %d' % (
        mgr, s32(r.d(mgr + 0x126C)) if mgr else -1, s32(r.d(mgr + 0x1268)) if mgr else -1,
        s32(r.d(loader + 0x50)) if loader else -1, s32(r.d(stage + 0x50)) if stage else -1,
        s32(r.d(stage + 0xB8)) if stage else -1))
    table = r.q(base + NET_PLAYERS)
    loc, alt = r.q(table + 0x20), r.q(table + 0x28)
    used = alt or loc
    own_no = s32(r.d(used + 0xD0)) if used else None
    print('  local pgd +0x20 %#x no %s team %s | +0x28 %#x no %s team %s | %s' % (
        loc, s32(r.d(loc + 0xD0)) if loc else '-', r.b(loc + 0x104) if loc else '-',
        alt, s32(r.d(alt + 0xD0)) if alt else '-', r.b(alt + 0x104) if alt else '-',
        'same object' if loc == alt else ('ALT DIFFERS (0x14DC040 / THOST2 / LocalPlayerNo read +0x28)' if alt else 'no ALT')))
    print('  own number used by the type-7 answer 0x14DC040: %s -> %s' % (
        own_no, 'type 5 is SENT' if own_no is not None and 1 <= own_no <= 0x270D else
        'type 5 is NOT sent (answer = 8 and 0xC0 only)'))
    print('  role byte %d | mailbox no %d team %d armed %d | re-request box %d' % (
        r.d(base + ROLE), s32(r.d(base + MAILBOX)), r.b(base + MAILBOX + 4), r.d(base + MAILBOX + 8),
        r.d(base + REREQUEST)))
    ready = r.q(table + 0x50) if table else 0
    pump = r.q(mgr + 0x1468) if mgr else 0
    if pump:
        b, e, c = r.q(pump + 0x88), r.q(pump + 0x90), r.q(pump + 0x98)
        print('  pump %#x run flag +0x1318 %d | deferred answers begin %#x end %#x cap %#x (%d queued)' % (
            pump, r.d(mgr + 0x1318), b, e, c, (e - b) // 8 if b and e >= b else -1))
    waiting = []
    begin, end = (r.q(mgr + 0x1248), r.q(mgr + 0x1250)) if mgr else (0, 0)
    if begin and end > begin and (end - begin) % 0xF8 == 0 and end - begin <= 16 * 0xF8:
        for mem in range(begin, end, 0xF8):
            mid = r.q(mem + 0x10)
            slot = r.b(mem + 0xD1)
            conn = r.q(mem + 0xC0)
            rb = r.b(ready + slot) if ready and slot <= 11 else None
            row = dict(id=mid, slot=slot, block=r.b(mem + 0xD0), rno=s32(r.d(mem + 0xD4)),
                       server=r.b(mem + 0xE0), self=r.b(mem + 0xE3), pending=r.b(mem + 0xE4),
                       t5=r.b(mem + 0xE8), conn=conn, open=(r.b(conn + 0xC) & 1) if conn else 0,
                       station=r.q(mem), ready=rb)
            print('  member %010x slot %3d +D0 %d no %3d server %d self %d pending %d type5 %d '
                  'conn %#x open %d station %#x ready %s' % (
                      mid & 0xFFFFFFFFFF, slot, row['block'], row['rno'], row['server'], row['self'],
                      row['pending'], row['t5'], conn, row['open'], row['station'],
                      '%#04x' % rb if rb is not None else '-'))
            if not row['server'] and not row['self'] and row['pending']:
                waiting.append(row)
    t = r.q(base + AABB)
    chr_ = r.q(r.q(base + WCM) + 0x1A8)
    pos = r.f(r.q(r.q(chr_ + 0x2470) + 0xE8) + 0x70, 3) if chr_ else None
    lo, hi = (r.f(t + 0x1C10, 3), r.f(t + 0x1C20, 3)) if t else (None, None)
    valid = r.b(t + 0x1C50) if t else None
    inside = None
    if pos and lo and hi:
        inside = lo[0] <= pos[0] <= hi[0] and lo[2] <= pos[2] <= hi[2]
    print('  answer box #3 valid %s min %s max %s | own chr pos %s -> %s' % (
        valid, lo, hi, pos, 'inside' if inside else ('OUTSIDE (type 5 serializes to 0 bytes)'
                                                     if inside is False else 'unknown')))
    for w in waiting:
        bits = w['ready'] or 0
        why = []
        if not bits & 0x02:
            why.append('no type 5 from it (its own number invalid, its answer box, or our requests '
                       'filed under its server station there)')
        if not w['conn'] or not w['open'] or w['block']:
            why.append('OUR LINK TO IT IS NOT OPEN / BLOCKED: our re-requests are dropped silently here')
        print('  WAITING for %010x: ready %#04x missing %#04x; %s' % (
            w['id'] & 0xFFFFFFFFFF, bits, 0x1F & ~bits, '; '.join(why) or 'all parts in, pop pending'))
    return own_no


if __name__ == '__main__':
    for who in (sys.argv[1] if len(sys.argv) > 1 else 'AB'):
        try:
            game(who)
        except Exception as e:  # a game that is not running
            print('== game %s: not readable (%s)' % (who, e))
