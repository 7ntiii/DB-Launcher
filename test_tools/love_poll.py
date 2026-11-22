"""TEST ONLY, no debugger: which gate keeps "Accept flowers" (button 100000) off the loved one's game, by POLLING the
data each gate tests while the bearer offers the flowers (diag/net/love3_notes.md; replaces the breakpoint probes).

python diag/twin/love_poll.py [BEARER LOVED] [secs=30] [hz=10] [side=front|back] [noplace]
python diag/twin/love_poll.py poll LOVED BEARER_NO [secs=30] [hz=10]
  poll only (real bearer, e.g. the laptop): no bearer setup checks, no emote, no placing, no writes.
  defaults: bearer B, loved A. Run from the workspace root in Phase I+, after the pairing (love_accept.py dry ok).
Steps: love_accept.py's setup checks (quests 240 / 250, logics, not reunited) -> place the loved one in front of the
bearer copy facing it (love_accept.Setup.place: the ONLY memory writes, the loved one's own position + yaw) ->
emote 22130 on the bearer -> poll the LOVED game ~hz times a second for `secs` s. No button is pressed.

Per sample, in the order the code tests them (0x19C9AA0 -> 0x19C9F6C -> 0x1B5F6FC -> 0x1B5AB20):
  offering  copy [[copy+0x2470]]+0x144 bit 2 (the window; samples outside it are not judged)
  key       copy M+0x5E / +0x60 = 0 or 50 (stock), or the offering bit (LOVEACCEPT)            data, exact
  list      the 250 class-B list holds the copy handle with flag byte != 0, and not reunited    data, NEAR
            (the code also decodes the SQM module key against pgd+0xD0 and resolves the handle via 0x17E7828:
             not replicated)
  box       loved one 0..2 m in front of the copy, |side| < 2, dy -2..3, facing <= 45 deg       data, NEAR
            (computed on the copy ORIGIN + forward = the code's fallback; dummy poly 80 is not readable)
  screen    copy feet or copy +1.2 m inside the camera frustum                                data, ESTIMATE
  gates     mgr+0x38 == 0, [[me+0x2470]+0xD8]+0x1C == -1, *(main+0x5B76C38)+0x114 / +0x16C == 0,
            [[me+0x2470]+0x60]+0x28 bit 0 and +0x29 == 3, own state +0x38 bit 0                data, exact
  prompt    a node with id 100000 in the prompt lists *(main+0x5B45958) +8 / +0x10             data, exact
NOT readable as data (stay undecided): whether 0x19C9AA0 runs for the remote copy at all (the per-chr updater
slot +0x118), dummy 80's exact position, event flag 20000.
Output: one line per state change, a table (true / samples per gate inside the window), and
  RESULT <gate> fix <n>: ...   (fix numbers = love3_notes.md section 4)."""
import math
import sys
import threading
import time

sys.path.insert(0, 'diag/twin')
import love_accept as LA   # noqa: E402
import emote               # noqa: E402
import tctl                # noqa: E402
from world_lib import W    # noqa: E402

ORDER = ['key', 'list', 'box', 'screen', 'gates']
FIX = {'key': 1, 'list': 2, 'box': 3, 'screen': 4, 'gates': 4}


def opts(argv):
    o = {'bearer': 'B', 'loved': 'A', 'secs': 30.0, 'hz': 10.0, 'side': 'front', 'noplace': False}
    pos = [a for a in argv[1:] if '=' not in a and a != 'noplace']
    if len(pos) >= 2:
        o['bearer'], o['loved'] = pos[0].upper(), pos[1].upper()
    for a in argv[1:]:
        if a == 'noplace':
            o['noplace'] = True
        elif '=' in a:
            k, v = a.split('=', 1)
            o[k] = v if k == 'side' else float(v)
    return o


def sample(wl, lno, cc, lc):
    """one read of every gate's data on the loved game -> dict of booleans (None = unreadable)"""
    r = {}
    blk = LA.flag_block(wl, cc)
    r['offering'] = None if blk is None else bool(LA.love_bits(blk)[1])
    # key (0x19C9AA0 key gate; LOVEACCEPT also takes the offering bit)
    m = wl.q((wl.q(cc + 0x2470) or 0) + 0x108) if cc else None
    k5e, k60 = (wl.h(m + 0x5E), wl.h(m + 0x60)) if m else (None, None)
    key = None if k5e is None else k5e if k5e != 0xFFFF else (k60 if k60 != 0xFFFF else 0xFF)
    r['keyval'] = key
    r['key'] = None if key is None else (key in (0, 50) or bool(r['offering']))
    # list (0x1183E00 -> 0x118E9DC: not reunited AND 0x119B2A0)
    _, ok = LA.gates(wl, lno, cc, lc)
    st = LA.logic_state(wl, lno, LA.LOVE_PASSIVE) or {}
    r['list'] = bool(ok['listed']) and not st.get('reunited')
    # box (fallback origin) + facing
    lp, cp = (wl.chr_pos(lc) if lc else None), (wl.chr_pos(cc) if cc else None)
    fl, fc = LA.forward(wl, lc), LA.forward(wl, cc)
    if LA.finite(lp) and LA.finite(cp) and fl and fc:
        dx, dz = lp[0] - cp[0], lp[2] - cp[2]
        along, side = dx * fc[0] + dz * fc[1], dx * fc[1] - dz * fc[0]
        dy = lp[1] - cp[1]
        n = math.hypot(dx, dz)
        face = math.degrees(math.acos(max(-1.0, min(1.0, (-dx * fl[0] - dz * fl[1]) / n)))) if n > 1e-4 else 0.0
        r['geo'] = 'along %.2f side %.2f dy %.2f face %.0f' % (along, side, dy, face)
        r['box'] = 0 <= along < 2.0 and abs(side) < 2.0 and -2.0 < dy < 3.0 and face <= 45.0
    else:
        r['geo'], r['box'] = 'unreadable', None
    # screen (estimate)
    hand = (cp[0], cp[1] + 1.2, cp[2]) if LA.finite(cp) else None
    txt = LA._cam_view(wl, [('feet', cp), ('hand', hand)], lp)
    r['screen'] = None if 'unreadable' in txt else ('feet ON' in txt or 'hand ON' in txt)
    # general gates of 0x1B5AB20 + own state bit 0
    tb = wl.q(lc + 0x2470) if lc else None
    d8 = wl.q(tb + 0xD8) if tb else None
    m60 = wl.q(tb + 0x60) if tb else None
    g76 = wl.g(LA.GATE76_G)
    mgr = wl.g(LA.PROMPT_MGR_G)
    blk_me = wl.q(tb) if tb else None
    vals = {'mgr38': wl.b(mgr + 0x38) if mgr else None, 'd8_1c': wl.i(d8 + 0x1C) if d8 else None,
            'g114': wl.i(g76 + 0x114) if g76 else None, 'g16c': wl.i(g76 + 0x16C) if g76 else None,
            'm28': wl.b(m60 + 0x28) if m60 else None, 'm29': wl.b(m60 + 0x29) if m60 else None,
            'st38': wl.q(blk_me + 0x38) if blk_me else None}
    r['gatevals'] = vals
    if any(v is None for v in vals.values()):
        r['gates'] = None
    else:
        # love5_notes 2: m28 bit 0 + m29 == 3 is only ONE way through 0x1B5B040; with it false the code still passes
        # when the request byte +0x14 != 0 or a flag word & 0x40001 (0x1B5B3E0..0x1B5B418): not a block, info only
        r['gates'] = (vals['mgr38'] == 0 and vals['d8_1c'] == -1 and vals['g114'] == 0 and vals['g16c'] == 0
                      and vals['st38'] & 1 == 1)
    r['prompt'] = LA.has_accept(wl)
    return r


def main():
    o = opts(sys.argv)
    B, L = o['bearer'], o['loved']
    wb, wl = W(B), W(L)
    bno, bq = LA.own_no_quest(wb)
    lno, lq = LA.own_no_quest(wl)
    print('bearer %s: player %s quest %s | loved %s: player %s quest %s' % (B, bno, bq, L, lno, lq))
    act_b, pas_l = LA.logic_state(wb, bno, LA.LOVE_ACTIVE), LA.logic_state(wl, lno, LA.LOVE_PASSIVE)
    if bq != 240 or lq != 250 or not act_b or not pas_l or act_b.get('reunited') or pas_l.get('reunited'):
        print('SETUP FAIL: quests %s/%s (want 240/250), logics 240 %s 250 %s' % (bq, lq, act_b, pas_l))
        return 2
    lo = LA.parse(['love_accept.py', B, L, 'side=%s' % o['side']])
    su = LA.Setup(wb, wl, bno, lno, lo)
    if not o['noplace'] and not su.place(o['side']):
        print('SETUP FAIL: placement refused (see above)')
        return 2
    _, _, cc, _ = su.bearer_views()
    lc = wl.me()[0]
    if not cc or not lc:
        print('SETUP FAIL: bearer copy %s / loved chr %s unreadable' % (cc, lc))
        return 2
    steps, _ = emote.build(lo['mode'], 'Plus', lo['dir'], 60)
    th = threading.Thread(target=lambda: tctl.call(B, {'method': 'input_sequence', 'params': {'steps': steps}}),
                          daemon=True)
    t0 = time.time()
    th.start()
    print('t+0.0 emote 22130 on %s; polling %s at ~%.0f Hz for %.0f s (no presses)' % (B, L, o['hz'], o['secs']))
    return poll(wl, lno, cc, lc, o, t0)


def poll_only(argv):
    """love_poll.py poll LOVED BEARER_NO [secs=30] [hz=10]: the bearer is NOT a rig game (real player). No setup
    checks on the bearer, no emote, no placing, no writes: find the copy of player BEARER_NO on LOVED and poll."""
    pos = [a for a in argv[2:] if '=' not in a]
    if len(pos) < 2:
        print(__doc__)
        return 2
    o = {'secs': 30.0, 'hz': 10.0}
    for a in argv[2:]:
        if '=' in a:
            k, v = a.split('=', 1)
            o[k] = float(v)
    L, bno = pos[0].upper(), int(pos[1])
    wl = W(L)
    lno, lq = LA.own_no_quest(wl)
    pas_l = LA.logic_state(wl, lno, LA.LOVE_PASSIVE)
    print('poll only: loved %s = player %s quest %s, logic 250 %s | bearer = player %d (not a rig game)' % (
        L, lno, lq, pas_l, bno))
    if not pas_l:   # any slot: slot 0 may hold the loved one's own sigil (e.g. Eye 200, love4_notes 2)
        print('NOTE: no 250 logic for player %s on %s (any slot): this game is NOT the loved one; the list gate will '
              'be false' % (lno, L))
    cc, lc, t_end = None, None, time.time() + 10
    while time.time() < t_end and not (cc and lc):
        cc = LA.sigils._module_chr(wl, bno)
        lc = wl.me()[0]
        if not (cc and lc):
            time.sleep(0.5)
    if not cc or not lc:
        print('SETUP FAIL: copy of player %d on %s %s / loved chr %s unreadable' % (bno, L, cc, lc))
        return 2
    print('copy of player %d on %s: chr 0x%x; loved chr 0x%x' % (bno, L, cc, lc))
    t0 = time.time()
    print('t+0.0 polling %s at ~%.0f Hz for %.0f s (no presses, no writes): do the emote now' % (L, o['hz'], o['secs']))
    return poll(wl, lno, cc, lc, o, t0)


def poll(wl, lno, cc, lc, o, t0):
    gates = ORDER + ['prompt']
    win = {g: [0, 0] for g in gates}        # inside the offering window: [true, readable samples]
    n = n_win = n_all = 0
    last = None
    while time.time() - t0 < o['secs']:
        ts = time.time()
        try:
            r = sample(wl, lno, cc, lc)
        except Exception as e:  # noqa: BLE001
            print('t+%.1f read error %s' % (ts - t0, e))
            time.sleep(0.2)
            continue
        n += 1
        if r['offering']:
            n_win += 1
            n_all += all(r[g] is not False for g in ORDER)
            for g in gates:
                if r[g] is not None:
                    win[g][1] += 1
                    win[g][0] += bool(r[g])
        key = tuple((g, r[g]) for g in ['offering'] + gates)
        if key != last:
            last = key
            print('t+%.1f offering %s | key %s (%s) | list %s | box %s (%s) | screen %s | gates %s %s | prompt %s' % (
                ts - t0, r['offering'], r['key'], r['keyval'], r['list'], r['box'], r['geo'], r['screen'],
                r['gates'], r['gatevals'], r['prompt']), flush=True)
        time.sleep(max(0.0, 1.0 / o['hz'] - (time.time() - ts)))
    print('\nsamples %d, inside the offering window %d (%.1f Hz)' % (n, n_win, n / max(o['secs'], 1)))
    print('%-8s %s' % ('gate', 'true / readable samples inside the window'))
    for g in gates:
        print('%-8s %d / %d' % (g, win[g][0], win[g][1]))
    if n_win == 0:
        print('RESULT undecided fix -: the offering bit was NEVER seen on the copy (0x%x) in %.0f s (emote did not '
              'play, or the copy never gets the bit: then no gate is judged)' % (cc, o['secs']))
        return 1
    if win['prompt'][0]:
        print('RESULT prompt present fix 5: node 100000 seen in %d samples: the prompt is offered; the press / '
              'bearer side is the gap (sigil15 case B)' % win['prompt'][0])
        return 0
    for g in ORDER:
        t, k = win[g]
        if k and t == 0:
            print('RESULT %s fix %d: false in all %d readable samples of the window%s' % (
                {'box': '2 m box', 'gates': 'general gates'}.get(g, g), FIX[g], k,
                ' (computed on the copy origin; dummy 80 may differ)' if g == 'box' else
                ' (camera estimate)' if g == 'screen' else ' (near: module-key decode not replicated)'
                if g == 'list' else ''))
            return 0
    unread = [g for g in ORDER if not win[g][1]]
    if not n_all:
        worst = min(ORDER, key=lambda g: (win[g][0] / win[g][1]) if win[g][1] else 2)
        print('RESULT %s fix %d: no sample had every readable gate true at once; %s was true least often (%d / %d)' % (
            worst, FIX[worst], worst, win[worst][0], win[worst][1]))
        return 0
    print('samples with every readable gate true at once: %d' % n_all)
    print('RESULT not reached / code-only gate fix 1: every readable gate was true at least once in the window%s and '
          'no prompt node appeared: the blocker is one that cannot be read as data (0x19C9AA0 not run for the copy, '
          'dummy 80 box, event flag 20000)' % ((' (unreadable: %s)' % ', '.join(unread)) if unread else ''))
    return 0


if __name__ == '__main__':
    sys.exit(poll_only(sys.argv) if len(sys.argv) > 1 and sys.argv[1] == 'poll' else main())
