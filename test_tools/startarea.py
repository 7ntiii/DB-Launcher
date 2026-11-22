"""startarea.py GAMES  -- READ-ONLY dump of the start-area selection state (and the airship-support state).

Usage (from the workspace root):  python diag/twin/startarea.py AB
Per game: phase/round, HOST byte, mediator flags, the local pick, the slots (picks as every game sees
them), the decided list (player no / area / spot / position), the coordinator and the airship-support
object. Nothing is written. Offsets: diag/net/startarea_zeppelin_notes.md ([V] bytes, [I] inferred).
"""
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, PAR_G, MGR3_G, PGD_G, GAMEDATA_G  # noqa: E402

MEDIATOR_G = 0x5B44EA0      # start-point mediator M                         [V]
COORD_G = 0x5B44E80         # final coordinator                              [V]
HOST_BYTE = 0x492AFD8       # 0 = host (lowest player no), 1 = guest (assist) [V]
STATES = {1: 'InPhase', 2: 'WaitOpenMenu', 3: 'PointSelecting', 4: 'WaitCloseMenu', 5: 'Finish'}


def pick(w, a):
    """{u8 kind, s32 id} at a ({4,-1} = none, kind 3 = area)"""
    k, i = w.b(a), w.i(a + 4)
    if k is None:
        return '?'
    if k == 4 and i == -1:
        return 'none'
    return 'k%d:%d' % (k, i)


def fmt3(p):
    return '?' if p is None else '(%.2f, %.2f, %.2f)' % p


def game(who):
    w = W(who)
    print('==== game %s ====' % who)
    par = w.g(PAR_G)
    gd = w.g(GAMEDATA_G)
    mgr3 = w.g(MGR3_G)
    print('phase %s round %s  offline(bda) %s  mode %s  HOST byte %s' % (
        w.d(par + 0x50) if par else None, w.d(par + 0xB8) if par else None,
        w.b(gd + 0xBDA) if gd else None, w.d(mgr3 + 0x1268) if mgr3 else None,
        w.b(w.base + HOST_BYTE)))

    pgd = w.g(PGD_G)
    lpgd = w.q(pgd + 0x20) if pgd else None
    me = w.d(lpgd + 0xD0) if lpgd else None
    print('local player no %s' % me)

    m = w.g(MEDIATOR_G)
    if not m:
        print('mediator: null')
        return
    st, nx = w.d(m + 0x50), w.d(m + 0x54)
    print('mediator %#x state %s(%s) next %s' % (m, st, STATES.get(st, '?'), nx))
    print('  +B8 menuClosed %s  +B9 decided %s  +BA allLocked %s' % (w.b(m + 0xB8), w.b(m + 0xB9), w.b(m + 0xBA)))
    print('  +650 timer %s  +658 %s +659 srvReply %s  +668 menuOpen %s  +678 grace %s +680 %s' % (
        w.f(m + 0x650), w.b(m + 0x658), w.b(m + 0x659), w.b(m + 0x668), w.f(m + 0x678), w.b(m + 0x680)))
    print('  +688 warpAll %s +689 %s  +6A8 deferredWarp %s  +620 stage %s  +624 areaKind %s' % (
        w.b(m + 0x688), w.b(m + 0x689), w.b(m + 0x6A8), w.i(m + 0x620), w.i(m + 0x624)))

    a0, a1 = w.q(m + 0x628), w.q(m + 0x630)
    if a0 and a1 and a1 >= a0 and (a1 - a0) <= 0x10 * 64:
        ids = ['k%d:%d' % (w.b(x + 8), w.i(x + 0xC)) for x in range(a0, a1, 0x10)]
        print('  areas (%d): %s' % (len(ids), ' '.join(ids)))
    else:
        print('  areas: ? (%s..%s)' % (a0, a1))

    n = w.q(m + 0x248)
    print('  slots (+C0, count %s):' % n)
    mine = None
    for k in range(min(n or 0, 8)):
        s = m + 0xC0 + k * 0x30
        no = w.d(s)
        if no == me:
            mine = pick(w, s + 0x10)
            # test pick without the menu (startarea_fix_notes.md section 7): u8 3 at +0x10, s32 area at +0x14
            print('    local slot pick at %#x (kind u8) / %#x (area s32), locked at %#x' % (
                s + 0x10, s + 0x14, s + 0x18))
        print('    [%d] no %s pick %s locked %s b19 %s' % (k, no, pick(w, s + 0x10), w.b(s + 0x18), w.b(s + 0x19)))
    print('  local pick (slot) %s' % mine)

    n = w.q(m + 0x5D8)
    print('  decided list (+290, count %s):' % n)
    for k in range(min(n or 0, 8)):
        e = m + 0x290 + k * 0x68
        print('    [%d] no %s flags %#x pick %s area %s spot %s pos %s' % (
            k, w.d(e), w.d(e + 0x04) or 0, pick(w, e + 0x10), pick(w, e + 0x20),
            pick(w, e + 0x38), fmt3(w.f3(e + 0x40))))

    c = w.g(COORD_G)
    if c:
        print('coordinator %#x +D8 %s +DC %s' % (c, w.b(c + 0xD8), w.b(c + 0xDC)))

    # airship support (event 1120 / env 0x0A) at par+0x2C0  [V layout, I meaning]
    if par:
        a = par + 0x2C0
        print('airship AS %#x type %#x ready(+B) %s prep(+C) %s' % (a, w.b(a + 8) or 0, w.b(a + 0xB), w.b(a + 0xC)))
        for name, off, sz in (('ships', 0xF0, 0x40), ('requests', 0x110, 0x38), ('strikes', 0x130, 0x20)):
            b0, b1 = w.q(a + off), w.q(a + off + 8)
            cnt = (b1 - b0) // sz if b0 and b1 and b1 >= b0 else None
            print('  %s: %s' % (name, cnt))
            if name == 'ships' and cnt:
                for x in range(b0, b0 + min(cnt, 8) * sz, sz):
                    print('    id %s count %s valid %s' % (w.h(x), w.d(x + 0x30), w.b(x + 0x38)))
            if name == 'strikes' and cnt:
                for x in range(b0, b0 + min(cnt, 8) * sz, sz):
                    print('    no %s active %s ship %s target %s fromSrv %s' % (
                        w.d(x), w.b(x + 4), w.h(x + 0x18), w.h(x + 0x1A), w.b(x + 0x1C)))
    if w.missing:
        print('missing: %s' % ', '.join(w.missing))


if __name__ == '__main__':
    for g in (sys.argv[1] if len(sys.argv) > 1 else 'AB'):
        try:
            game(g)
        except Exception as ex:  # a closed game must not stop the others
            print('game %s: %s' % (g, ex))
