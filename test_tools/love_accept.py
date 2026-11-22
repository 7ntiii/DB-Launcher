"""TEST ONLY: Love Ephemeral end to end, hands-free: place the loved one, bearer plays "Flowers for You" (22130),
the loved one presses the "Accept flowers" prompt inside the offering window, Virtue before / after on both games.
Notes: diag/net/sigil15_notes.md (section 1), diag/net/sigil14_notes.md. Run from the workspace root, in Phase I+,
after `sigils.py AB` shows the pair (bearer 240 'list 1: ->p<loved>', loved 250 'list 1: ->p<bearer>').

python diag/twin/love_accept.py BEARER LOVED [options]
  BEARER  game whose local player holds quest 240 (hub row 600040 Senator Samir Patres with the sigil)
  LOVED   game whose local player holds quest 250 (the record target)
options (defaults in brackets):
  dist=1.0     horizontal distance of the spot from the bearer (m)
  spot=F,S     instead of dist/side: F m along the bearer copy's forward, S m to his right; facing the bearer
  scan=1       grid F -0.5..2.0 x S -1.5..1.5 (0.5 m) while the offering shows, hold=0.4 s per spot, polls the
               prompt list *(main+0x5B45958) +8/+0x10 for button 100000; re-emotes (up to emotes=6, gap_emote=2 s)
               until the grid is done; first hit: Y twice, prints spot=F,S. Writes: loved one's pos + yaw only.
  side=auto    front | back | auto (auto: front first, the back spot after half the presses without a reaction)
  dir=315      emote wheel direction (proven for 22130 and 22160), mode=hold (emote.py modes)
  btn=Y        prompt button (every ActionButton prompt seen in this game is Y: pillar, pick-up)
  presses=6    presses inside the window, gap=0.8 s between them, delay=0.4 s after the offering is first seen
  max=30       give up when no offering is seen this many seconds after the emote input starts
  force=1      run even when the quest / pairing / reunited checks fail
  dry          compute and validate the spot only: no memory write, no input
  place        place (and turn) the loved one, then stop: no emote, no press

ALL MEMORY WRITES (only on the LOVED game, only the loved one's own player, via world_lib.W.goto):
  [WCM+0x30 entry 0 +0x28] + 0x70  12 bytes f32 x y z   (position)  - placement, and a re-placement when the
                                                                      loved one drifted > 0.6 m from the spot or
                                                                      side=auto switches to the back spot
  [WCM+0x30 entry 0 +0x28] + 0x64   4 bytes f32 yaw      (heading)   - same moments
  Every written position is validated first: finite, horizontal distance to the bearer's OWN position (bearer
  game) <= 3.0 m and to the bearer copy on the loved game <= 3.0 m, y = the bearer's y (same height), and the
  loved one alive. Nothing else is written; the bearer is never moved.
INPUT: bearer: the emote sequence of emote.py (Plus held, right stick DIR, A); loved: left-stick pushes only when
  the facing after the teleport is > 40 deg off (approach.py measure / turn), then BTN taps (6 frames).
READS (both games): bearer chr [[chr+0x2470]]+0x144 bit 2 'offering' (TAE event 10820, case 0x2A44 of the TAE
  dispatcher 0x193A9A0 -> 0x193B348) and +0x143 bit 3 'accepted' (TAE event 10700 with a non-zero arg ->
  0x193B260; read by the active logic 0x118DE34), the whole flag block +0x100..+0x14F of the bearer and the loved
  one (bit diff = which animation events the press caused), 240 / 250 logic +0x48 reunited, 250 module mask,
  Virtue (pgd +0x42C8 banked + plain win-point counters) of every numbered player on both games.
Prompt geometry [V ActionButtonParam 100000 + shape-1 test 0x1B61298]: box in front of the bearer's dummy poly 80:
  along its Z 0..2.0 m, sideways < 2.0 m, height T.y-2 .. T.y+3, and the loved one's forward (-Z row of
  [chr+0x68]+0x170) within 45 deg of the point. Dummy 80's axis is not read here [I: chr forward], hence side=auto.
Exit: 0 reunited (both flags) / 1 offering seen, no accept / 2 setup failed / 3 no offering."""
import math
import os
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, 'diag/twin')
from world_lib import W, PGD_G  # noqa: E402
import tctl  # noqa: E402
import sigils  # noqa: E402
import emote  # noqa: E402

LOVE_ACTIVE, LOVE_PASSIVE = sigils.LOVE_ACTIVE, sigils.LOVE_PASSIVE
FLAG_LO, FLAG_HI = 0x100, 0x150
MAX_FROM_BEARER = 3.0
FACE_OK = 40.0
GET_FIELD = 0xF6BEC0        # win-point counter getter that returns u32 obj+0x68 (virtue.py) [V]
WRITES = []


# ------------------------------------------------------------------ small readers
def pgd_local(w):
    g = w.g(PGD_G)
    return w.q(g + 0x20) if g else None


def own_no_quest(w):
    p = pgd_local(w)
    return (w.i(p + 0xD0), w.i(p + 0x46E0)) if p else (None, None)


def flag_block(w, chr_):
    st = w.q(w.q(chr_ + 0x2470) or 0) if chr_ else None
    return w.rd(st + FLAG_LO, FLAG_HI - FLAG_LO) if st else None


def love_bits(blk):
    if not blk:
        return None, None
    return blk[0x143 - FLAG_LO] >> 3 & 1, blk[0x144 - FLAG_LO] >> 2 & 1     # accepted, offering


def bit_diff(a, b):
    if not a or not b:
        return 'unreadable'
    out = []
    for k in range(len(a)):
        x = a[k] ^ b[k]
        for bit in range(8):
            if x >> bit & 1:
                out.append('+0x%X b%d %d->%d' % (FLAG_LO + k, bit, a[k] >> bit & 1, b[k] >> bit & 1))
    return ' '.join(out) or 'none'


def gates(w, lno, copy_, own=None):
    """sigil15 section 4: the stock tests of the "Accept flowers" prompt (button 100000, 0x19C9AA0) on the LOVED
    game, read only. key = bearer copy's action key (M = [[copy+0x2470]+0x108], +0x5E else +0x60 else 0xFF; stock
    needs 0 or 50, LOVEACCEPT also takes the offering bit); listed = the loved one's 250 class-B list
    ([logic+0x40]+0x90/+0x98: count +0x58, u32 entries +0x10, +2 flag) holds the copy's handle [[copy+0x20]+0x78]
    with a non-zero flag (0x1183E00 -> vt+0x148 0x118E9DC -> 0x119B2A0). -> (text, {'key': ok, 'listed': ok})"""
    m = w.q((w.q(copy_ + 0x2470) or 0) + 0x108) if copy_ else None
    k5e, k60 = (w.h(m + 0x5E), w.h(m + 0x60)) if m else (None, None)
    key = None if k5e is None else k5e if k5e != 0xFFFF else (k60 if k60 != 0xFFFF else 0xFF)
    pv = w.q(copy_ + 0x20) if copy_ else None
    hnd = w.h(pv + 0x78) if pv else None
    _, lg = sigils._love_logic_of(w, lno, LOVE_PASSIVE)
    root = w.q(lg + 0x40) if lg else None
    cond = (w.q(root + 0x90) or w.q(root + 0x98)) if root else None
    n = (w.q(cond + 0x58) or 0) if cond else 0
    ents = [w.d(cond + 0x10 + 4 * k) or 0 for k in range(min(n, 16))]
    listed = hnd is not None and any((e & 0xFFFF) == hnd and (e >> 16) & 0xFF for e in ents)
    # 0x1B5ADCC..0x1B5AE08 (generic button system, every prompt): the LOCAL chr's flag block [[chr+0x2470]]
    # +0x38.. must have bit row+0x44 set; ActionButtonParam 100000 +0x44 = 0 -> bit 0 of the qword +0x38.
    # (Pillar 8332 / kin circle 9021 use bit 4, which is why those prompts are no hint.)
    blk = w.q(w.q(own + 0x2470) or 0) if own else None
    st38 = w.q(blk + 0x38) if blk else None
    state = None if st38 is None else bool(st38 & 1)
    txt = ('gates on loved game: copy key +0x5E %s +0x60 %s -> %s (stock ok: 0 / 50) | 250 list %d [%s] copy handle '
           '%s -> listed %s | 250 reunited %s | loved own state +0x38 %s: bit 0 %s (needed), bit 4 %s' % (
               None if k5e is None else '0x%X' % k5e, None if k60 is None else '0x%X' % k60, key, n,
               ' '.join('0x%08X' % e for e in ents) or 'EMPTY', None if hnd is None else '0x%X' % hnd,
               listed, w.b(lg + 0x48) if lg else None, None if st38 is None else '0x%016X' % st38, state,
               None if st38 is None else bool(st38 >> 4 & 1)))
    return txt, {'key': key in (0, 50), 'listed': listed, 'state': bool(state)}


CAM_G = 0x5B659A8       # 0x1B5F6FC: camera C = [[*(main+0x5B659A8)]+0x18]+0x10; world matrix C+0x10 (4x4 rows),
#                         near C+0x58 (read by the code); fov C+0x50 / aspect C+0x54 [I FromSoft CSCam layout]
GATE76_G = 0x5B76C38    # 0x1B5AD14 / 0x1B5B024: *(main+0x5B76C38) +0x114 and +0x16C must both be 0     [V]


def _cam_view(w, pts, ref):
    """read only: camera-space of each point; the forward sign is calibrated on `ref` (the local player, always in
    front of the camera). -> text"""
    g = w.g(CAM_G)
    a = w.q(g + 0x18) if g else None
    c = w.q(a + 0x10) if a else None
    raw = w.rd(c + 0x10, 0x50) if c else None
    if not raw:
        return 'camera unreadable'
    m = struct.unpack('<20f', raw)
    rgt, up, fwd, pos = m[0:3], m[4:7], m[8:11], m[12:15]
    fov, asp, near = m[16], m[17], w.f(c + 0x58)
    sane = 0.2 < fov < 2.5
    th = math.tan(fov / 2.0) if sane else math.tan(math.radians(25))
    ax = th * (asp if 0.5 < asp < 4.0 else 16.0 / 9.0)

    def cs(p):
        d = (p[0] - pos[0], p[1] - pos[1], p[2] - pos[2])
        return tuple(sum(d[i] * v[i] for i in range(3)) for v in (rgt, up, fwd))

    sg = 1.0
    if finite(ref):
        sg = 1.0 if cs(ref)[2] >= 0 else -1.0
    out = []
    for name, p in pts:
        if not finite(p):
            out.append('%s ?' % name)
            continue
        x, y, z = cs(p)
        z *= sg
        on = z > (near or 0.1) and abs(x / z) < ax and abs(y / z) < th
        out.append('%s %s (z %.1f, x/z %.2f of %.2f, y/z %.2f of %.2f)' % (
            name, 'ON' if on else 'OFF', z, x / z if z else 0, ax, y / z if z else 0, th))
    return 'screen [0x1B5F6FC, new prompt dropped when OFF]: %s | cam fwd sign %+d fov %.2f asp %.2f near %s' % (
        '; '.join(out), sg, fov, asp, near)


def geo(w, lc, cc):
    """read only, every test of 0x19C9F6C / 0x1B5AB20 that the gates() line does not cover: box (fallback = copy
    origin + copy forward, as 0x1B61348 when dummy 80 is not found), facing, screen, player-state gates"""
    lp, cp = (w.chr_pos(lc) if lc else None), (w.chr_pos(cc) if cc else None)
    fl, fc = forward(w, lc), forward(w, cc)
    parts = []
    if finite(lp) and finite(cp) and fl and fc:
        dx, dz = lp[0] - cp[0], lp[2] - cp[2]
        along, side = dx * fc[0] + dz * fc[1], dx * fc[1] - dz * fc[0]
        dy = lp[1] - cp[1]
        n = math.hypot(dx, dz)
        face = math.degrees(math.acos(max(-1.0, min(1.0, (-dx * fl[0] - dz * fl[1]) / n)))) if n > 1e-4 else 0.0
        ok = 0 <= along < 2.0 and abs(side) < 2.0 and -2.0 < dy < 3.0 and face <= 45.0
        parts.append('box(fallback origin) along %.2f [0..2] side %.2f [<2] dy %.2f [-2..3] facing %.0f deg [<=45]'
                     ' -> %s' % (along, side, dy, face, 'PASS' if ok else 'FAIL'))
    else:
        parts.append('box: positions / model matrices unreadable')
    hand = (cp[0], cp[1] + 1.2, cp[2]) if finite(cp) else None
    parts.append(_cam_view(w, [('copy feet', cp), ('copy +1.2 m', hand)], lp))
    tb = w.q(lc + 0x2470) if lc else None
    d8 = w.q(tb + 0xD8) if tb else None
    m60 = w.q(tb + 0x60) if tb else None
    g76 = w.g(GATE76_G)
    mgr = w.g(PROMPT_MGR_G)
    parts.append('player gates [0x1B5AB20]: mgr+0x38 %s (need 0) | [[me+0x2470]+0xD8]+0x1C %s (need -1) | '
                 '*(main+0x5B76C38) +0x114 %s +0x16C %s (need 0, 0) | [[me+0x2470]+0x60] +0x28 %s +0x29 %s '
                 '(need bit0 1 and 3)' % (
                     w.b(mgr + 0x38) if mgr else None, w.i(d8 + 0x1C) if d8 else None,
                     w.i(g76 + 0x114) if g76 else None, w.i(g76 + 0x16C) if g76 else None,
                     w.b(m60 + 0x28) if m60 else None, w.b(m60 + 0x29) if m60 else None))
    return 'geo: ' + ' || '.join(parts)


def forward(w, chr_):
    m68 = w.q(chr_ + 0x68) if chr_ else None
    z = w.f3(m68 + 0x170) if m68 else None
    if not z:
        return None
    fx, fz = -z[0], -z[2]
    n = math.hypot(fx, fz)
    return (fx / n, fz / n) if n > 1e-6 else None


def finite(p):
    return p is not None and all(isinstance(v, float) and math.isfinite(v) for v in p)


def hd(a, b):
    return math.hypot(a[0] - b[0], a[2] - b[2])


_LOGIC = {}


def logic_state(w, no, vt):
    """240 / 250 logic of player `no` on game w: reunited logic+0x48, module mask +0x38, module state +0x18.
    The (module, logic) pair is looked up once (sigils._love_logic_of walks the SQM) and then cached."""
    key = (w.who, no, vt)
    if key not in _LOGIC or _LOGIC[key][1] is None:
        _LOGIC[key] = sigils._love_logic_of(w, no, vt)
    mm, lg = _LOGIC[key]
    if not lg:
        return None
    return {'reunited': w.b(lg + 0x48), 'mask': (w.q(mm + 0x38) or 0) & 0xFFF, 'state': w.i(mm + 0x18)}


def virtue(w):
    """{player no: (banked s16 pgd+0x42C8, sum of plain counters, n computed counters, wp+0x11)} (virtue.py)"""
    g = w.g(PGD_G)
    if not g:
        return {}
    cand = [w.q(g + o) for o in (0x08, 0x10, 0x20, 0x28)]
    pool = w.q(g + 0x30)
    if pool:
        cand += [pool + i * 0x47F0 for i in range(12)]
    out, seen = {}, set()
    for p in cand:
        if not p or p in seen:
            continue
        seen.add(p)
        no = w.d(p + 0xD0)
        if no in (None, 0xFFFFFFFF):
            continue
        b = w.rd(p + 0x42C8, 2)
        banked = struct.unpack('<h', b)[0] if b else None
        wp = w.q(p + 0x46D8)
        known = unknown = 0
        f11 = None
        if wp:
            f11 = w.b(wp + 0x11)
            raw = w.rd(wp + 0xC18, 26 * 8)
            for obj in (struct.unpack('<26Q', raw) if raw else ()):
                if not obj:
                    continue
                vt = w.q(obj)
                get = (w.q(vt + 0x20) or 0) - w.base if vt else None
                if get == GET_FIELD:
                    known += w.d(obj + 0x68) or 0
                else:
                    unknown += 1
        out[no] = (banked, known, unknown, f11)
    return out


def print_virtue(tag, games):
    res = {}
    for name, w in games:
        v = virtue(w)
        res[name] = v
        print('%s Virtue on %s: %s' % (tag, name, ' | '.join(
            'p%d banked %s + counters %d (?%d computed, wp+0x11 %s)' % (no, *v[no]) for no in sorted(v)) or 'none'))
    return res


# ------------------------------------------------------------------ input
def press(who, btn, frames=6):
    return tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [btn], 'frames': frames},
                                                                          {'frames': 4}]}})


def shot(who, name):
    out = os.path.join(HERE, '%s_%s.png' % (who, name))
    r = tctl.call(who, {'method': 'screenshot', 'params': {'height': 480}}, out)
    print('  shot %s_%s.png%s' % (who, name, '' if 'error' not in (r or '').lower() else ' (' + r[:100] + ')'))


# ------------------------------------------------------------------ placement
class Setup:
    def __init__(self, wb, wl, bno, lno, o):
        self.wb, self.wl, self.bno, self.lno, self.o = wb, wl, bno, lno, o

    def bearer_views(self):
        """bearer as seen on his own game (own entry) and as the copy on the loved game (the prompt is tested there)"""
        bc, _, bpos = self.wb.me()
        cc = sigils._module_chr(self.wl, self.bno)
        cpos = self.wl.chr_pos(cc) if cc else None
        return bc, bpos, cc, cpos

    def spot(self, side):
        bc, bpos, cc, cpos = self.bearer_views()
        if not finite(bpos) or not finite(cpos):
            print('setup: bearer position unreadable (own %s, copy on %s %s)' % (bpos, self.wl.who, cpos))
            return None
        f = forward(self.wl, cc) or forward(self.wb, bc)
        if f is None:
            print('setup: bearer facing unreadable ([chr+0x68]+0x170)')
            return None
        lag = hd(bpos, cpos)
        sgn = 1.0 if side == 'front' else -1.0
        d = self.o['dist']
        s = (cpos[0] + sgn * d * f[0], cpos[1], cpos[2] + sgn * d * f[1])
        if self.o['spot'] and side == 'front':
            fw, sd = self.o['spot']            # metres along the bearer's forward / to his right (x z plane)
            rx, rz = f[1], -f[0]              # right of forward (fx, fz) in this game's x z convention [I]
            s = (cpos[0] + fw * f[0] + sd * rx, cpos[1], cpos[2] + fw * f[1] + sd * rz)
        yaw = math.atan2(cpos[0] - s[0], cpos[2] - s[2])
        print('setup: bearer own (%.2f %.2f %.2f) | copy on %s (%.2f %.2f %.2f), %.2f m apart | forward (%.2f, %.2f) '
              '| %s spot (%.2f %.2f %.2f) yaw %.2f' % (bpos + (self.wl.who,) + cpos + (lag,) + f + (side,) + s + (yaw,)))
        why = []
        if not finite(s):
            why.append('spot not finite')
        if hd(s, bpos) > MAX_FROM_BEARER or hd(s, cpos) > MAX_FROM_BEARER:
            why.append('spot %.2f / %.2f m from the bearer (own / copy) > %.1f' % (hd(s, bpos), hd(s, cpos),
                                                                                  MAX_FROM_BEARER))
        if abs(s[1] - cpos[1]) > 0.01 or abs(cpos[1] - bpos[1]) > 0.6:
            why.append('height: spot y %.2f, copy y %.2f, own y %.2f' % (s[1], cpos[1], bpos[1]))
        if why:
            print('setup: spot REJECTED: ' + '; '.join(why))
            return None
        return s, yaw, cpos

    def write(self, s, yaw, why):
        lc, _, lpos = self.wl.me()
        hp = self.wl.chr_hp(lc) if lc else None
        if not finite(lpos) or (hp is not None and hp <= 0):
            print('setup: loved one not ready (pos %s, HP %s): no write' % (lpos, hp))
            return False
        if self.o['dry']:
            print('DRY: would write %s phys+0x70 = (%.2f %.2f %.2f), phys+0x64 = %.2f (%s)' % ((self.wl.who,) + s +
                                                                                            (yaw, why)))
            return True
        ok = self.wl.goto(s, yaw)
        if ok:
            WRITES.append('%s: own player phys+0x70 (%.2f %.2f %.2f) + phys+0x64 %.2f (%s)' % ((self.wl.who,) + s +
                                                                                            (yaw, why)))
        return ok

    def face_err(self, cpos):
        lc, _, lpos = self.wl.me()
        f = forward(self.wl, lc)
        if f is None or not finite(lpos):
            return None, lpos
        dx, dz = cpos[0] - lpos[0], cpos[2] - lpos[2]
        n = math.hypot(dx, dz)
        if n < 1e-4:
            return None, lpos
        return math.degrees(math.acos(max(-1.0, min(1.0, (f[0] * dx + f[1] * dz) / n)))), lpos

    def place(self, side, turn=True):
        sp = self.spot(side)
        if not sp:
            return None
        s, yaw, cpos = sp
        if not self.write(s, yaw, 'placement %s' % side):
            return None
        if self.o['dry']:
            return sp
        tctl.call(self.wl.who, {'method': 'input_sequence', 'params': {'steps': [{'frames': 30}]}})
        err, lpos = self.face_err(cpos)
        if not finite(lpos) or hd(lpos, s) > 0.6 or abs(lpos[1] - s[1]) > 0.6:
            print('setup: after the teleport the loved one is at %s, not at the spot: stopping' % (lpos,))
            return None
        print('setup: placed, %.2f m from the bearer copy, facing error %s (yaw write %s)' % (
            hd(lpos, cpos), 'unreadable' if err is None else '%.0f deg' % err,
            'took effect' if err is not None and err <= FACE_OK else 'did NOT turn the model' if err else '?'))
        if turn and err is not None and err > FACE_OK:
            import approach
            ap = approach.Approach({'who': self.wl.who, 'tgt': cpos, 'dist': self.o['dist'], 'side': None, 'y': None,
                                    'dy': 0.0, 'hold': None, 'shot': None})
            if ap.measure():
                self.write(s, yaw, 'back to the spot after the stick measure')   # measure moved the player
                tctl.call(self.wl.who, {'method': 'input_sequence', 'params': {'steps': [{'frames': 20}]}})
                ap.turn()
            err, lpos = self.face_err(cpos)
            print('setup: after turning: %.2f m from the bearer copy, facing error %s' % (
                hd(lpos, cpos) if finite(lpos) else -1, 'unreadable' if err is None else '%.0f deg' % err))
        return sp


# ------------------------------------------------------------------ main
def parse(argv):
    if len(argv) < 3 or argv[1] == argv[2]:
        print(__doc__)
        sys.exit(2)
    o = {'bearer': argv[1], 'loved': argv[2], 'dist': 1.0, 'side': 'auto', 'dir': 315, 'mode': 'hold', 'btn': 'Y',
         'presses': 6, 'gap': 0.8, 'delay': 0.4, 'max': 30.0, 'force': False, 'dry': False, 'place': False,
         'spot': None, 'scan': False, 'hold': 0.4, 'emotes': 6, 'gap_emote': 2.0}
    for a in argv[3:]:
        k, _, v = a.partition('=')
        if k in ('dry', 'place') and not _:
            o[k] = True
        elif k == 'scan':
            o[k] = v not in ('0', '')
        elif k == 'emotes':
            o[k] = int(v)
        elif k in ('dist', 'gap', 'delay', 'max', 'hold', 'gap_emote'):
            o[k] = float(v)
        elif k in ('dir', 'presses'):
            o[k] = int(v)
        elif k == 'force':
            o[k] = v not in ('0', '')
        elif k in ('side', 'mode', 'btn'):
            o[k] = v
        elif k == 'spot':
            fw, _, sd = v.partition(',')
            o[k] = (float(fw), float(sd or 0))
            o['side'] = 'front'
        else:
            sys.exit('unknown option %s' % a)
    if o['side'] not in ('front', 'back', 'auto'):
        sys.exit('side must be front, back or auto')
    if not 0.3 <= o['dist'] <= 1.9:
        sys.exit('dist must lie in 0.3 .. 1.9 m (prompt box depth 2.0)')
    return o


PROMPT_MGR_G = 0x5B45958   # x0 of 0x1B5AB20 (0x1B5FCB4): the prompt list every button request lands in   [V]
ACCEPT_BTN = 100000


def prompts(w):
    """The LOCAL player's offered action prompts [V 0x1B5B174..0x1B5B390]: manager *(main+0x5B45958), two singly
    linked lists, heads +8 (new entries are pushed here) and +0x10; node (0x68 bytes) +0 next, +8 request type
    (0x10 = chr button, 0x19C9F6C), +0xC button id, +0x10 target handle (request +0x18 = chr+8), +0x25 state bits.
    A node is added only after EVERY test passed (box, screen, state bit). -> [(list, type, id, handle, bits)]"""
    mgr = w.g(PROMPT_MGR_G)
    out = []
    for name, off in (('+8', 8), ('+0x10', 0x10)):
        node, seen = (w.q(mgr + off) if mgr else None), set()
        while node and node not in seen and len(seen) < 64:
            seen.add(node)
            out.append((name, w.d(node + 8), w.d(node + 0xC), w.d(node + 0x10), w.b(node + 0x25)))
            node = w.q(node)
    return out


def has_accept(w):
    return any(p[2] == ACCEPT_BTN for p in prompts(w))


def scan_run(o, wb, wl, su, B, L, bno, lno, games, before):
    """scan=1: walk the loved one over a grid around the bearer copy while the offering shows; at each spot hold
    0.4 s and poll the prompt list (prompts()) for button 100000. First hit: press, print the spot."""
    grid = [(f / 2.0, s / 2.0) for f in range(-1, 5) for s in range(-3, 4)]     # F -0.5..2.0, S -1.5..1.5
    print('scan: %d spots (forward -0.5..2.0, side -1.5..1.5, step 0.5), %.1f s each; prompt list now: %s' % (
        len(grid), o['hold'], prompts(wl) or 'empty'))
    k, emotes, hit = 0, 0, None
    while k < len(grid) and emotes < o['emotes'] and hit is None:
        emotes += 1
        steps, _ = emote.build(o['mode'], 'Plus', o['dir'], 60)
        th = threading.Thread(target=lambda: tctl.call(B, {'method': 'input_sequence', 'params': {'steps': steps}}))
        t0 = time.time()
        th.start()
        print('emote #%d on %s (spots %d..)' % (emotes, B, k))
        seen = False
        while time.time() - t0 < o['max'] + 15 and k < len(grid):
            cc = sigils._module_chr(wl, bno)
            _, oc = love_bits(flag_block(wl, cc))
            if not oc:
                if seen:
                    break                  # window over: next emote
                time.sleep(0.15)
                continue
            seen = True
            fw, sd = grid[k]
            cpos = wl.chr_pos(cc)
            f = forward(wl, cc)
            if not finite(cpos) or f is None:
                print('scan: copy position / facing unreadable')
                break
            s = (cpos[0] + fw * f[0] + sd * f[1], cpos[1], cpos[2] + fw * f[1] - sd * f[0])   # right = (fz, -fx) [I]
            yaw = math.atan2(cpos[0] - s[0], cpos[2] - s[2]) if math.hypot(s[0] - cpos[0], s[2] - cpos[2]) > 0.05 \
                else math.atan2(-f[0], -f[1])
            if hd(s, cpos) > MAX_FROM_BEARER:
                k += 1
                continue
            su.write(s, yaw, 'scan F %.1f S %.1f' % (fw, sd))
            t1, got = time.time(), False
            while time.time() - t1 < o['hold']:
                if has_accept(wl):
                    got = True
                    break
                time.sleep(0.05)
            print('t+%.1f spot F %+.1f S %+.1f: prompt %s' % (time.time() - t0, fw, sd, 'YES' if got else 'no'))
            if not got:
                print('    ' + geo(wl, wl.me()[0], cc))
            if got:
                hit = (fw, sd)
                press(L, o['btn'])
                time.sleep(0.4)
                press(L, o['btn'])
                break
            k += 1
        th.join(timeout=30)
        if hit is None and k < len(grid):
            time.sleep(o['gap_emote'])
    time.sleep(4.0)
    after = print_virtue('AFTER ', games)
    a240, p250 = logic_state(wb, bno, LOVE_ACTIVE), logic_state(wl, lno, LOVE_PASSIVE)
    cc = sigils._module_chr(wl, bno)
    print('final: 240@%s %s | 250@%s %s | bearer own bits %s | copy bits %s' % (
        B, a240, L, p250, love_bits(flag_block(wb, wb.me()[0])), love_bits(flag_block(wl, cc))))
    print('memory writes made: %d (%s)' % (len(WRITES), '; '.join(WRITES[-3:]) or 'none'))
    if hit is None:
        print('RESULT SCAN NO PROMPT: %d of %d spots tried over %d emotes; no button %d in the prompt list' % (
            k, len(grid), emotes, ACCEPT_BTN))
        return 1
    print('RESULT SCAN PROMPT at spot=%.1f,%.1f (F m along the bearer copy forward, S m to his right, facing him): '
          'rerun with `spot=%.1f,%.1f`; reunited 240 %s / 250 %s' % (
              hit[0], hit[1], hit[0], hit[1], a240 and a240['reunited'], p250 and p250['reunited']))
    return 0


def main():
    o = parse(sys.argv)
    B, L = o['bearer'], o['loved']
    wb, wl = W(B), W(L)
    games = [(B, wb), (L, wl)]
    bno, bq = own_no_quest(wb)
    lno, lq = own_no_quest(wl)
    print('bearer %s: player %s quest %s (want 240) | loved %s: player %s quest %s (want 250)' % (B, bno, bq, L, lno, lq))
    bad = []
    if bq != 240 or lq != 250:
        bad.append('quests are not 240 / 250 (hub: Samir with the sigil on the bearer, no sigil on the loved one)')
    act_b, pas_l = logic_state(wb, bno, LOVE_ACTIVE), logic_state(wl, lno, LOVE_PASSIVE)
    act_l = logic_state(wl, bno, LOVE_ACTIVE)
    print('logics: bearer 240 on %s %s | bearer 240 on %s %s | loved 250 on %s %s' % (B, act_b, L, act_l, L, pas_l))
    if not act_b or not pas_l:
        bad.append('240 / 250 logic missing (sigils.py AB 5b: key PRESENT? list 1?)')
    if act_l is None:
        bad.append('the bearer key has no 240 module on the loved game: the target mirror (row 2501) cannot run')
    if (act_b and act_b['reunited']) or (pas_l and pas_l['reunited']):
        bad.append('already reunited: rows 2401 / 2501 are once-only, nothing left to test this match')
    if bad and not o['force']:
        print('SETUP FAIL: ' + '; '.join(bad) + ' (force=1 to run anyway)')
        return 2
    for b in bad:
        print('warning (force): ' + b)
    before = print_virtue('BEFORE', games)
    su = Setup(wb, wl, bno, lno, o)
    side = 'back' if o['side'] == 'back' else 'front'
    sp = su.place(side)
    if not sp:
        return 2
    if o['dry'] or o['place']:
        print('%s: stopping before the emote. Writes: %s' % ('DRY' if o['dry'] else 'PLACE', WRITES or 'none'))
        return 0
    s, yaw, cpos = sp

    bc, _, cc, _ = su.bearer_views()
    lc = wl.me()[0]
    g_txt, g_ok = gates(wl, lno, cc, lc)
    print('t-0 ' + g_txt)
    print('t-0 ' + geo(wl, lc, cc))
    if o['scan']:
        return scan_run(o, wb, wl, su, B, L, bno, lno, games, before)
    g_seen = {'key': False, 'listed': False, 'state': False}
    blk0 = {'b_own': flag_block(wb, bc), 'b_copy': flag_block(wl, cc), 'l_own': flag_block(wl, lc)}
    steps, _ = emote.build(o['mode'], 'Plus', o['dir'], 60)
    th = threading.Thread(target=lambda: tctl.call(B, {'method': 'input_sequence', 'params': {'steps': steps}}))
    t0 = time.time()
    th.start()
    print('t+0.0 emote 22130 input started on %s (mode %s dir %d)' % (B, o['mode'], o['dir']))
    last, t_off, t_next, presses, switched, success, t_succ = None, None, None, 0, False, False, None
    react = False
    while True:
        t = time.time() - t0
        bo, bcp, lo = flag_block(wb, bc), flag_block(wl, cc), flag_block(wl, lc)
        ab, ob = love_bits(bo)
        ac, oc = love_bits(bcp)
        a240 = logic_state(wb, bno, LOVE_ACTIVE) or {}
        p250 = logic_state(wl, lno, LOVE_PASSIVE) or {}
        st = (ob, ab, oc, ac, str(a240), str(logic_state(wl, bno, LOVE_ACTIVE)), str(p250))
        if st != last:
            print('t+%.1f bearer on %s: offering %s accepted %s | copy on %s: offering %s accepted %s | 240@%s %s | '
                  '240@%s %s | 250@%s %s' % (t, B, ob, ab, L, oc, ac, B, st[4], L, st[5], L, st[6]))
            last = st
        if lo and blk0['l_own'] and lo != blk0['l_own'] and not react and presses:
            react = True
            print('t+%.1f loved one\'s own flag block changed after the press: %s' % (t, bit_diff(blk0['l_own'], lo)))
        if not success and (ab or ac or a240.get('reunited') or p250.get('reunited')):
            success, t_succ = True, t
            print('t+%.1f ACCEPT SEEN' % t)
            shot(L, 'love_accept_ok')
        if oc and t_off is None:
            t_off = t
            t_next = t + o['delay']
            print('t+%.1f offering visible on the loved game: pressing %s from t+%.1f' % (t, o['btn'], t_next))
        if t_off is not None and not success and presses < o['presses'] and t >= t_next:
            lpos = wl.me()[2]
            cnow = wl.chr_pos(cc)
            if finite(lpos) and finite(cnow) and (hd(lpos, s) > 0.6 or abs(lpos[1] - s[1]) > 0.6):
                print('t+%.1f loved one drifted to %s: back to the spot' % (t, lpos))
                su.write(s, yaw, 'drift fix')
            if o['side'] == 'auto' and not switched and not react and presses >= max(1, o['presses'] // 2):
                switched = True
                sp2 = su.spot('back')
                if sp2:
                    s, yaw, cpos = sp2
                    su.write(s, yaw, 'side=auto: back spot')
                    time.sleep(0.25)
            if presses == 0:
                shot(L, 'love_accept_pre')
            g_txt, g_ok = gates(wl, lno, cc, lc)
            for k in g_seen:
                g_seen[k] = g_seen[k] or g_ok[k]
            print('t+%.1f %s' % (t, g_txt))
            print('t+%.1f %s' % (t, geo(wl, lc, cc)))
            print('t+%.1f press %s #%d on %s' % (time.time() - t0, o['btn'], presses + 1, L))
            press(L, o['btn'])
            presses += 1
            t_next = time.time() - t0 + o['gap']
            if presses == 1:
                shot(L, 'love_accept_post')
        if success and t - t_succ > 6.0:
            break
        if t_off is None and t > o['max']:
            break
        if t_off is not None and not success and presses >= o['presses'] and t - t_next > 4.0:
            break
        if t > o['max'] + 40:
            break
        time.sleep(0.15)
    th.join(timeout=30)
    time.sleep(3.0)
    blk1 = {'b_own': flag_block(wb, bc), 'b_copy': flag_block(wl, cc), 'l_own': flag_block(wl, lc)}
    for k, txt in (('b_own', 'bearer own chr on %s' % B), ('b_copy', 'bearer copy on %s' % L),
                   ('l_own', 'loved own chr on %s' % L)):
        print('flag block bits changed, %s: %s' % (txt, bit_diff(blk0[k], blk1[k])))
    after = print_virtue('AFTER ', games)
    for name, _ in games:
        for no in sorted(set(before.get(name, {})) | set(after.get(name, {}))):
            a, b = before.get(name, {}).get(no), after.get(name, {}).get(no)
            if a and b and a[:2] != b[:2]:
                print('CHANGE on %s: p%s banked %s -> %s, counters %s -> %s' % (name, no, a[0], b[0], a[1], b[1]))
    a240, l240, p250 = logic_state(wb, bno, LOVE_ACTIVE), logic_state(wl, bno, LOVE_ACTIVE), logic_state(wl, lno, LOVE_PASSIVE)
    print('final: 240@%s %s | 240@%s %s | 250@%s %s' % (B, a240, L, l240, L, p250))
    print('memory writes made: %s' % ('; '.join(WRITES) or 'none'))
    if t_off is None:
        print('RESULT NO OFFERING: the copy on %s never showed +0x144 bit 2 within %.0f s (emote not played: run '
              '`emote.py %s probe 22130`; or the copy is not updated)' % (L, o['max'], B))
        return 3
    if a240 and a240['reunited'] and p250 and p250['reunited']:
        print('RESULT PASS: reunited on both owner games; expect +4 for p%s on %s (row 2401) and +4 for p%s on %s '
              '(row 2501); confirm with `python diag/twin/sigils.py AB` (2401 x1 / 2501 x1)' % (bno, B, lno, L))
        return 0
    if success:
        print('RESULT PARTIAL: accept seen but not reunited on both (bearer own accepted -> case A; only the copy '
              'on %s accepted -> case B of sigil14 3: the bearer game never learns it)' % L)
        return 1
    print('RESULT NO ACCEPT: %d presses inside the offering window, no accept flag. Look at %s_love_accept_pre.png '
          '(prompt shown?) and the loved one\'s flag-block diff above' % (presses, L))
    if presses:
        why = []
        if not g_seen['listed']:
            why.append('the 250 class-B list on %s never held the bearer copy (EMPTY or stale handle): no prompt '
                       'and no step event 1 (mask 0); fix = late pairing, sigil15 4.3' % L)
        if not g_seen['key']:
            why.append('the copy\'s action key was never 0 / 50 (TAE event 932 not run on the remote chr): bake '
                       'LOVEACCEPT (sigil15 4.2)')
        if not g_seen['state']:
            why.append('the loved one\'s own state bit 0 ([[chr+0x2470]]+0x38, ActionButtonParam 100000 +0x44 = 0, '
                       'test 0x1B5AE08) was never set: no prompt whatever the spot (sigil15 7)')
        print('GATES: ' + ('; '.join(why) if why else 'key, list and state bit passed: the box around the bearer\'s '
                           'dummy 80 is left; try spot=F,S (sigil15 7)'))
    return 1


if __name__ == '__main__':
    sys.exit(main())
