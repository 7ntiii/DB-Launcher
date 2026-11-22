"""TEST ONLY - NEVER SHIP. Love Ephemeral accept with a REAL bearer (a person on another PC, e.g. the laptop).
python diag/twin/pkgtest.py run diag/twin/love_live.py NO [secs=60] [dist=1.2] [presses=4] [games=AB] [dry]
  NO = the bearer's player number (the laptop). Phase I+ of a match in which the bearer picked the Senator row.
Steps (diag/net/love4_notes.md):
  1. find the loved rig game: the game whose OWN player has a 250 logic in ANY slot (slot 0 may hold its own
     sigil, e.g. Eye 200; that is fine). None found -> RESULT NOT LOVED (the random pick chose the other player).
  2. read the bearer's copy on that game (position + forward); validated spot = copy + dist m along the copy's
     forward, same height; refused if not finite, height off by > 0.6 m, loved one dead / unreadable.
  3. one real step in place through input (stick forward 4 frames, back 4 frames: opens the action-state gate
     m28 bit 0 / m29 == 3 that was 0 / 0 on an idle rig player), then W.goto(spot, yaw facing the copy), up to 3
     tries until gates are true. Memory writes: ONLY the loved one's own position + yaw (W.goto).
  4. "tell the user to emote NOW", poll the loved game 10 Hz for secs (love_poll.sample: offering, key, list, box,
     screen, gates, prompt). While NOT offering and the box is false for 3 s (the user moved): re-place, max 3.
  5. offering + prompt node 100000 -> screenshot, press Y (tctl input) up to `presses` times 0.8 s apart while the
     prompt is there; then watch 10 s for the reunited flags (250 logic of the loved one, 240 logic of the bearer
     on the loved game) and the Virtue change on every rig game.
One RESULT line: REUNITED / PRESSED NO REUNITE / PROMPT NEVER / NO OFFERING / NOT LOVED / SETUP FAIL."""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import love_accept as LA   # noqa: E402
import love_poll as LP     # noqa: E402
import tctl                # noqa: E402
from world_lib import W    # noqa: E402

STEP = [{'left_stick': [0, 1], 'frames': 4}, {'left_stick': [0, -1], 'frames': 4}, {'frames': 20}]


def opts(argv):
    pos = [a for a in argv[1:] if '=' not in a and a != 'dry']
    if not pos:
        print(__doc__)
        sys.exit(2)
    o = {'no': int(pos[0]), 'secs': 60.0, 'dist': 1.2, 'presses': 4, 'games': 'AB', 'dry': 'dry' in argv[1:]}
    for a in argv[1:]:
        if '=' in a:
            k, v = a.split('=', 1)
            o[k] = v.upper() if k == 'games' else int(v) if k == 'presses' else float(v)
    if not 0.3 <= o['dist'] <= 1.9:
        sys.exit('dist must lie in 0.3 .. 1.9 m (prompt box depth 2.0)')
    return o


def find_loved(o):
    found = []
    for g in o['games']:
        w = W(g)
        lno, q0 = LA.own_no_quest(w)
        st = LA.logic_state(w, lno, LA.LOVE_PASSIVE) if lno is not None else None
        print('%s: player %s, slot-0 quest %s, own 250 logic %s' % (g, lno, q0, st))
        if st is not None and lno != o['no']:
            found.append((g, w, lno))
    return found


def views(wl, bno):
    cc = LA.sigils._module_chr(wl, bno)
    lc, _, lpos = wl.me()
    cpos = wl.chr_pos(cc) if cc else None
    return cc, lc, cpos, lpos


def place(o, wl, lno, bno, why):
    """step in place, then the validated spot; up to 3 tries until the gates read true. -> (cc, lc) or None"""
    for k in range(3):
        cc, lc, cpos, lpos = views(wl, bno)
        hp = wl.chr_hp(lc) if lc else None
        f = LA.forward(wl, cc) if cc else None
        if not (cc and lc and LA.finite(cpos) and LA.finite(lpos) and f) or (hp is not None and hp <= 0):
            print('place: unreadable or dead (copy %s pos %s fwd %s | loved %s pos %s HP %s)' % (
                cc, cpos, f, lc, lpos, hp))
            return None
        s = (cpos[0] + o['dist'] * f[0], cpos[1], cpos[2] + o['dist'] * f[1])
        yaw = math.atan2(cpos[0] - s[0], cpos[2] - s[2])
        if not LA.finite(s) or LA.hd(s, cpos) > o['dist'] + 0.05:
            print('place: spot refused (spot %s, copy %s)' % (s, cpos))
            return None
        print('place (%s, try %d): copy (%.2f %.2f %.2f) fwd (%.2f %.2f) -> spot (%.2f %.2f %.2f) yaw %.2f' % (
            why, k + 1, *cpos, *f, *s, yaw))
        if o['dry']:
            print('DRY: no step, no write')
            return cc, lc
        tctl.call(wl.who, {'method': 'input_sequence', 'params': {'steps': STEP}})       # one real step
        wl.goto(s, yaw)
        tctl.call(wl.who, {'method': 'input_sequence', 'params': {'steps': [{'frames': 30}]}})
        cc, lc, cpos, lpos = views(wl, bno)
        if not (LA.finite(lpos) and LA.finite(cpos)) or LA.hd(lpos, s) > 0.6 or abs(lpos[1] - s[1]) > 0.6:
            print('place: the loved one is at %s after the write, not at the spot' % (lpos,))
            continue
        r = LP.sample(wl, lno, cc, lc)
        print('place: box %s (%s) | gates %s %s | key %s list %s screen %s' % (
            r['box'], r['geo'], r['gates'], r['gatevals'], r['key'], r['list'], r['screen']))
        if r['gates'] and r['box']:
            return cc, lc
    print('place: gates / box still false after 3 tries (going on: the poll shows them)')
    return views(wl, bno)[:2]


def flags(wl, lno, bno):
    p = LA.logic_state(wl, lno, LA.LOVE_PASSIVE) or {}
    a = LA.logic_state(wl, bno, LA.LOVE_ACTIVE) or {}
    return p.get('reunited'), a.get('reunited'), p.get('mask')


def main():
    o = opts(sys.argv)
    bno = o['no']
    loved = find_loved(o)
    if not loved:
        print('RESULT NOT LOVED: no rig game holds a 250 logic for its own player (the bearer\'s random pick chose '
              'another player, or no Senator sigil in this match)')
        return 1
    L, wl, lno = loved[0]
    games = [(g, W(g)) for g in o['games']]
    print('loved one: %s (player %s); bearer player %d (real person)' % (L, lno, bno))
    if not LA.sigils._module_chr(wl, bno):
        print('RESULT SETUP FAIL: no copy of player %d on %s' % (bno, L))
        return 2
    before = LA.print_virtue('BEFORE', games)
    f0 = flags(wl, lno, bno)
    print('BEFORE flags on %s: 250 reunited %s, bearer 240 reunited %s, 250 mask %s' % ((L,) + f0))
    got = place(o, wl, lno, bno, 'start')
    if not got:
        print('RESULT SETUP FAIL: placement refused (see above)')
        return 2
    cc, lc = got
    print('\n' + '=' * 60 + '\n  >>> TELL THE USER TO EMOTE NOW (hold Plus, right stick, A), 2-3 times <<<\n' + '=' * 60,
          flush=True)
    t0 = time.time()
    n_off = n_prompt = presses = replaced = 0
    box_bad_since, last, t_press = None, None, 0.0
    while time.time() - t0 < o['secs']:
        ts = time.time()
        try:
            r = LP.sample(wl, lno, cc, lc)
        except Exception as e:  # noqa: BLE001
            print('t+%.1f read error %s' % (ts - t0, e))
            time.sleep(0.3)
            cc, lc = views(wl, bno)[:2]
            continue
        n_off += bool(r['offering'])
        n_prompt += bool(r['prompt'])
        key = tuple(r[g] for g in ('offering', 'key', 'list', 'box', 'screen', 'gates', 'prompt'))
        if key != last:
            last = key
            print('t+%.1f offering %s | key %s (%s) | list %s | box %s (%s) | screen %s | gates %s %s | prompt %s' % (
                ts - t0, r['offering'], r['key'], r['keyval'], r['list'], r['box'], r['geo'], r['screen'],
                r['gates'], r['gatevals'], r['prompt']), flush=True)
        if r['prompt'] and n_prompt == 1:
            LA.shot(L, 'love_live_prompt')
        if r['prompt'] and presses < o['presses'] and ts - t_press >= 0.8 and not o['dry']:
            print('t+%.1f prompt 100000 on %s: press Y #%d' % (ts - t0, L, presses + 1), flush=True)
            LA.press(L, 'Y')
            presses += 1
            t_press = time.time()
        if presses and flags(wl, lno, bno)[0]:
            break
        if not r['offering'] and r['box'] is False:
            box_bad_since = box_bad_since or ts
            if ts - box_bad_since > 3.0 and replaced < 3 and not presses:
                replaced += 1
                got = place(o, wl, lno, bno, 'the user moved (%d)' % replaced)
                if got:
                    cc, lc = got
                box_bad_since = None
        else:
            box_bad_since = None
        time.sleep(max(0.0, 0.1 - (time.time() - ts)))
    if presses:
        t_end = time.time() + 10
        while time.time() < t_end and not flags(wl, lno, bno)[0]:
            time.sleep(0.5)
    f1 = flags(wl, lno, bno)
    print('AFTER flags on %s: 250 reunited %s, bearer 240 reunited %s, 250 mask %s' % ((L,) + f1))
    after = LA.print_virtue('AFTER', games)
    dv = []
    for g, _ in games:
        for no in sorted(after.get(g, {})):
            b, a = before.get(g, {}).get(no), after[g][no]
            if b and a and (b[0], b[1]) != (a[0], a[1]):
                dv.append('%s p%d %s+%s -> %s+%s' % (g, no, b[0], b[1], a[0], a[1]))
    LA.shot(L, 'love_live_after')
    tail = 'prompt samples %d, offering samples %d, presses %d, re-placed %d; Virtue %s' % (
        n_prompt, n_off, presses, replaced, '; '.join(dv) or 'unchanged')
    if f1[0]:
        print('RESULT REUNITED: %s' % tail)
        return 0
    if presses:
        print('RESULT PRESSED NO REUNITE: %s (look at %s_love_live_prompt.png)' % (tail, L))
    elif n_off:
        print('RESULT PROMPT NEVER: the offering was seen but node 100000 never appeared; %s (the poll lines name the '
              'false gate)' % tail)
    else:
        print('RESULT NO OFFERING: the bearer copy never showed the offering bit in %.0f s; %s' % (o['secs'], tail))
    return 1


if __name__ == '__main__':
    sys.exit(main())
