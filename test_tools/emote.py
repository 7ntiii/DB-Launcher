"""Perform an emote (default 22160 "A Third Eye I Seek", Eye of Muralis) on one twin game and check it played.
Run from the workspace root, in a match, on the Eye bearer's game (hub row 600010 Bloodhand Jan, Eye ON).
Notes: diag/net/emote_notes.md ([V] verified in text / params / code, [I] inferred, [G] guess).

  python diag/twin/emote.py WHO [EMOTE_ID] [dir DEG] [mode hold|tap|release] [open Plus|Minus] [hold F] [wait S]
        perform once: screenshots diag/twin/<WHO>_emote<N>.png, third eye / effect list before + after, PASS/FAIL
  python diag/twin/emote.py WHO probe [EMOTE_ID]   opener check (Plus, Minus), then modes x 8 directions until PASS
  python diag/twin/emote.py WHO state              read only (third eye, active effect list, goods count)
  python diag/twin/emote.py params                 static: EmoteParam rows, goods / role / skill rows, every param
                                                   row that holds the emote id, SpEffect rows with state 0x1FD

INPUT [V text]: PHX 130501 "Open info screen / Hold to open emote menu" (info screen = Plus), TutorialBody 17004000
"Hold <1016>: Emote menu / <keyControlCamera>: Select emote / <1005>: Execute" -> hold Plus, right stick picks,
A executes [I: 1005 = A, 1016 = Plus]. [G]: whether Plus must stay held, and the wheel direction of the emote.
  mode hold    (default) Plus held all the time, right stick pushed, A pressed while both are held
  mode tap     Plus held F frames and released (menu stays open?), then right stick + A
  mode release Plus held, right stick pushed, Plus released while the stick is still pushed, then A
  dir DEG      wheel direction, 0 = up, 90 = right (clockwise). Default 0.
STATE [V code, mirror of 0x118F9C0 via sigils._third_eye]: effect list [[chr+0x20]+0x90], gate +0x2CA & 0x1C,
node row [+0x80] u16 +0x146 == 0x1FD = third eye. PASS (22160) = off before, ACTIVE at some poll after.
For other ids PASS = a new active effect node (row, state) appeared [I].
Side effects: only pad input (menus, an emote animation). On FAIL, B x2 closes any menu left open (not on PASS:
B may be dodge and cut the emote). wait S (default 6) counts from the end of the input sequence.
"""
import math
import os
import struct
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
import tctl  # noqa: E402

EYE_ID = 22160
EYE_FX = 0x1FD
FX_MASK = 0x800C0003
EFFECT_SYNC = 0x59E1B28   # [[main+0x59E1B28]]+0x2180 item-use request counter (zeppelin4_notes 5) [V]
WCM_G = 0x5B3CD88
HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS = os.path.join(HERE, '..', 'scripts_decoded', 'param', 'gameparam', 'gameparam_nt.parambnd')

shot_no = [0]


# ---------------------------------------------------------------- input / screenshots
def seq(who, steps):
    return tctl.call(who, {'method': 'input_sequence', 'params': {'steps': steps}})


def shot(who, label=''):
    out = os.path.join(HERE, '%s_emote%d.png' % (who, shot_no[0]))
    r = tctl.call(who, {'method': 'screenshot', 'params': {'height': 480}}, out)
    print('  shot %s_emote%d.png %s%s' % (who, shot_no[0], label, '' if 'error' not in (r or '').lower() else ' (' + r[:120] + ')'))
    shot_no[0] += 1


def stick(deg):
    a = math.radians(deg)
    return [round(math.sin(a), 3), round(math.cos(a), 3)]


def build(mode, opener, deg, hold):
    """returns (steps, [(seconds after start, label) for screenshots while the sequence runs])"""
    rs = stick(deg)
    if mode == 'hold':
        steps = [{'buttons': [opener], 'frames': hold},
                 {'buttons': [opener], 'right_stick': rs, 'frames': 20},
                 {'buttons': [opener, 'A'], 'right_stick': rs, 'frames': 6},
                 {'buttons': [opener], 'frames': 10}, {'frames': 20}]
    elif mode == 'release':
        steps = [{'buttons': [opener], 'frames': hold},
                 {'buttons': [opener], 'right_stick': rs, 'frames': 20},
                 {'right_stick': rs, 'frames': 10},
                 {'buttons': ['A'], 'frames': 6}, {'frames': 20}]
    else:  # tap
        steps = [{'buttons': [opener], 'frames': hold}, {'frames': 15},
                 {'right_stick': rs, 'frames': 20},
                 {'buttons': ['A'], 'right_stick': rs, 'frames': 6}, {'frames': 20}]
    # [I] 30-60 presents per second: 0.9 s is inside a 60-frame hold at either rate; the second shot aims at
    # "stick pushed" (late in the sequence); timing is approximate (subprocess start ~0.2-0.5 s)
    sec = hold / 60.0
    return steps, [(0.9, 'menu (%s held)' % opener), (sec + 0.9, 'stick %d deg' % deg)]


# ---------------------------------------------------------------- memory
class G:
    def __init__(self, who):
        from world_lib import W
        self.w = W(who)

    def chr(self):
        w = self.w
        wcm = w.g(WCM_G)
        c = w.q(wcm + 0x1A8) if wcm else None          # local chr (use_item.py local()) [V]
        if not c:
            e = w.player_entry(0)
            c = e[0] if e else None
        return c

    def effects(self, c):
        """(gate byte, [(node, row, flags, state)]) walking exactly like sigils._third_eye, without the early exit"""
        w = self.w
        data = w.q(c + 0x20) if c else None
        mgr = w.q(data + 0x90) if data else None
        if not mgr:
            return None, None
        gate = w.b(mgr + 0x2CA)
        out, seen = [], set()
        node, outer = w.q(mgr + 8), mgr + 8
        for _ in range(256):
            n = 0
            while node and node not in seen and n < 512:
                seen.add(node)
                fl = w.d(node + 0x20) or 0
                row = w.q(node + 0x80)
                out.append((node, row, fl, w.h(row + 0x146) if row else None))
                node = w.q(node + 0x88)
                n += 1
            outer = w.q(outer + 0x18) if outer else None
            if not outer:
                break
            node = w.q(outer)
        return gate, out

    def state(self):
        w = self.w
        c = self.chr()
        gate, fx = self.effects(c)
        eye = None
        if fx is not None:
            eye = bool((gate or 0) & 0x1C) and any(st == EYE_FX and not fl & FX_MASK for _, _, fl, st in fx)
        try:   # cross-check with the reader the lead already uses
            import sigils
            eye2 = sigils._third_eye(w, c)
        except Exception:
            eye2 = 'n/a'
        h = w.g(EFFECT_SYNC)
        mgr = w.q(h) if h else None
        data = w.q(c + 0x20) if c else None
        pgd = w.q(data + 0x1D0) if data else None
        return {'chr': c, 'gate': gate, 'fx': fx, 'eye': eye, 'eye_sigils': eye2,
                'requests': w.d(mgr + 0x2180) if mgr else None, 'pgd': pgd}

    def goods(self, pgd, gid):
        try:
            import zeppelin as Z
            return Z.goods_count(self.w, pgd, gid)
        except Exception:
            return None


def active(st):
    return {(row, s) for _, row, fl, s in (st['fx'] or []) if not fl & FX_MASK}


def show(g, tag, st, emote):
    w = g.w
    eye = {True: 'ACTIVE', False: 'off', None: 'unreadable'}[st['eye']]
    print('%s chr %s | effect gate +0x2CA %s | active effects %s | third eye 0x%X %s (sigils.py: %s) | '
          'item-use requests %s | goods %d x %s' % (
              tag, w.rel(st['chr']), None if st['gate'] is None else '0x%X' % st['gate'],
              len(active(st)), EYE_FX, eye, st['eye_sigils'], st['requests'], emote, g.goods(st['pgd'], emote)))


def list_fx(g, st, only=None):
    for row, s in sorted(only if only is not None else active(st), key=lambda x: (x[1] or 0, x[0] or 0)):
        print('     row %s state +0x146 %s%s' % (g.w.rel(row), s if s is None else '0x%X (%d)' % (s, s),
                                                 '  <- third eye' if s == EYE_FX else ''))


# ---------------------------------------------------------------- one attempt
def attempt(who, g, emote, mode, opener, deg, hold, wait):
    print('-- %s: emote %d mode %s open %s dir %d hold %d' % (who, emote, mode, opener, deg, hold))
    before = g.state()
    show(g, ' before', before, emote)
    shot(who, 'before')
    steps, shots = build(mode, opener, deg, hold)
    th = threading.Thread(target=lambda: seq(who, steps))
    t0 = time.time()
    th.start()
    seen_eye, new = None, set()
    pending = list(shots)
    t_end = None                                # wait S counts from the end of the input sequence
    while th.is_alive() or t_end is None or time.time() - t_end < wait:
        if t_end is None and not th.is_alive():
            t_end = time.time()
        if pending and time.time() - t0 >= pending[0][0]:
            shot(who, pending.pop(0)[1])
            continue
        if not th.is_alive() and pending:      # sequence ended before its planned shots
            shot(who, pending.pop(0)[1] + ' (late)')
            continue
        st = g.state()
        if st['eye'] and seen_eye is None:
            seen_eye = time.time() - t0
            shot(who, 'third eye ACTIVE')
        new |= active(st) - active(before)
        time.sleep(0.25)
        if time.time() - t0 > wait + 60:
            break
    th.join(timeout=30)
    after = g.state()
    show(g, ' after ', after, emote)
    shot(who, 'after')
    if new:
        print('   new effect nodes during the try:')
        list_fx(g, None, new)
    if emote == EYE_ID:
        ok = not before['eye'] and seen_eye is not None
        why = ('third eye 0x1FD became ACTIVE at %.1f s' % seen_eye) if ok else (
            'third eye was already ACTIVE before' if before['eye'] else
            'third eye never ACTIVE (%s)' % ('new effects seen: an emote / other action played' if new
                                             else 'no new effect: emote not performed / menu not reached'))
    else:
        ok = bool(new)
        why = '%d new effect node(s)' % len(new) if ok else 'no new effect node [I: emote may add none]'
    print(' %s: %s' % ('PASS' if ok else 'FAIL', why))
    return ok


def close_menus(who):
    seq(who, [{'buttons': ['B'], 'frames': 6}, {'frames': 20}, {'buttons': ['B'], 'frames': 6}, {'frames': 60}])


def probe(who, g, emote, wait):
    print('== probe 1: which button opens the emote menu (look at the "menu" shots)')
    for opener in ('Plus', 'Minus'):
        print('-- hold %s 90 frames' % opener)
        th = threading.Thread(target=lambda: seq(who, [{'buttons': [opener], 'frames': 90}, {'frames': 20}]))
        th.start()
        time.sleep(0.9)
        shot(who, 'hold %s (menu should show)' % opener)
        th.join(timeout=30)
        shot(who, 'after releasing %s' % opener)
        close_menus(who)
    print('== probe 2: modes x 8 directions (stops at the first PASS)')
    for mode in ('hold', 'tap', 'release'):
        for deg in range(0, 360, 45):
            if attempt(who, g, emote, mode, 'Plus', deg, 60, wait):
                print('== FOUND: python diag/twin/emote.py %s %d mode %s dir %d' % (who, emote, mode, deg))
                return True           # no B here: a dodge could cut the emote / third eye
            close_menus(who)
            time.sleep(2.0)
    print('== probe: no PASS. Look at the shots: menu never opened -> opener wrong (try open Minus); menu opened but '
          'no "%s" entry -> not the Eye bearer (sigils.py E. must say BEARER); entry visible -> note its direction '
          'and run with dir DEG.' % emote)
    return False


# ---------------------------------------------------------------- static params
def param_rows(path):
    b = open(path, 'rb').read()
    n = struct.unpack_from('<H', b, 0xA)[0]
    rs = [struct.unpack_from('<ixxxxqq', b, 0x40 + i * 24) for i in range(n)]
    offs = sorted(o for _, o, _ in rs)
    size = min((y - x for x, y in zip(offs, offs[1:]) if y > x), default=0)
    return b, rs, size


def words(b, off, size):
    return ' '.join('%#x:%d' % (k * 4, w) for k, w in enumerate(struct.unpack_from('<%di' % (size // 4), b, off)) if w)


def params(emote):
    def dump(name, ids):
        p = os.path.join(PARAMS, name)
        if not os.path.exists(p):
            print('%s: not in scripts_decoded' % name)
            return
        b, rs, size = param_rows(p)
        print('# %s: %d rows, row size %#x' % (name, len(rs), size))
        for rid, off, _ in rs:
            if ids is None or rid in ids:
                print('  %d | %s' % (rid, words(b, off, size)))
    dump('EmoteParam.param', None)
    dump('EquipParamGoods.param', {20000, 22000, 22130, emote})
    dump('SubQuestRoleParam.param', {30, 200, 205})
    dump('SkillParam.param', {1010020})
    print('# every param row holding the int %d (any 4-byte aligned word):' % emote)
    for name in sorted(os.listdir(PARAMS)):
        if not name.endswith('.param'):
            continue
        try:
            b, rs, size = param_rows(os.path.join(PARAMS, name))
        except Exception:
            continue
        if size <= 0:
            continue
        for rid, off, _ in rs:
            ws = struct.unpack_from('<%di' % (size // 4), b, off) if off + size <= len(b) else ()
            hits = ['%#x' % (k * 4) for k, w in enumerate(ws) if w == emote]
            if hits:
                print('  %s row %d at %s' % (name, rid, ' '.join(hits)))
    print('# SpEffect rows with u16 +0x146 == 0x%X (third eye state):' % EYE_FX)
    for name in sorted(os.listdir(PARAMS)):
        if name.startswith('SpEffectParam') and name.endswith('.param'):
            b, rs, size = param_rows(os.path.join(PARAMS, name))
            hit = [rid for rid, off, _ in rs if size > 0x148 and struct.unpack_from('<H', b, off + 0x146)[0] == EYE_FX]
            print('  %s (%d rows, size %#x): %s' % (name, len(rs), size, hit or 'none (real SpEffectParam may be '
                                                                         'in the regulation)'))


# ---------------------------------------------------------------- main
def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == 'params':
        params(int(a[1]) if len(a) > 1 else EYE_ID)
        return
    who, rest = a[0], a[1:]
    emote, opts, cmd = EYE_ID, {}, 'go'
    i = 0
    while i < len(rest):
        t = rest[i]
        if t in ('probe', 'state'):
            cmd = t
        elif t in ('dir', 'mode', 'open', 'hold', 'wait') and i + 1 < len(rest):
            opts[t] = rest[i + 1]
            i += 1
        elif t.isdigit():
            emote = int(t)
        else:
            sys.exit('unknown argument %r' % t)
        i += 1
    g = G(who)
    wait = float(opts.get('wait', 6))
    if cmd == 'state':
        st = g.state()
        show(g, 'state', st, emote)
        list_fx(g, st)
        return
    if cmd == 'probe':
        probe(who, g, emote, wait)
        return
    mode = opts.get('mode', 'hold')
    if mode not in ('hold', 'tap', 'release'):
        sys.exit('mode must be hold, tap or release')
    if not attempt(who, g, emote, mode, opts.get('open', 'Plus'), int(opts.get('dir', 0)), int(opts.get('hold', 60)),
                   wait):
        close_menus(who)      # only on FAIL: B may be dodge and cut a playing emote


if __name__ == '__main__':
    main()
