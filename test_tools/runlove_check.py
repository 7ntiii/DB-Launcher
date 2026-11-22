"""Helper of diag/twin/runlove.sh (love3_notes.md section 3). TEST RIG ONLY. Run from the workspace root.

python diag/twin/runlove_check.py others          rig / launcher processes already running (empty = none)
python diag/twin/runlove_check.py copym           on A: the bearer copy's action module M = [[copy+0x2470]+0x108]
                                                   (bearer = B's own player number), absolute hex, or 'none'
python diag/twin/runlove_check.py clearbp OFF,..  on A's gdbstub (6543): halt, remove the breakpoints, resume
python diag/twin/runlove_check.py probe OFF,.. SECS [x19=HEX] [x21=HEX]
                                                   filtered breakpoint probe on A (bpprobe.py format; always cleared)
python diag/twin/runlove_check.py judge N FILE [M] the verdict of probe N from bpprobe's output FILE:
                                                   prints 'NEXT <n>' or 'RESULT <gate> fix <k>: <reason>'
Read only on the games, except clearbp (removes our own breakpoints and resumes A)."""
import re
import socket
import sys
import time

sys.path.insert(0, 'diag/twin')
sys.path.insert(0, 'diag/net')

BUTTON = 0x186A0          # 100000 "Accept flowers"


def others():
    import psutil
    out = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            name = (p.info['name'] or '').lower()
            cmd = ' '.join(p.info['cmdline'] or []).replace('\\', '/')
        except Exception:  # noqa: BLE001
            continue
        if name.startswith('python') and re.search(r'twin4?\.py|to_hub|to_match|go4b?\.sh|run[234]\.sh|love_accept|'
                                                   r'bpprobe|crystal_test|match4', cmd):
            out.append('%s pid %d' % (cmd.split('/')[-1][:40], p.info['pid']))
        elif name == 'bash.exe' and re.search(r'run[234]\.sh|go4b?\.sh|go_hub\.sh|go\.sh', cmd) and 'runlove' not in cmd:
            out.append('bash %s pid %d' % (cmd.split('/')[-1][:40], p.info['pid']))
    print('; '.join(out))


def copym():
    from world_lib import W
    import love_accept as LA
    import sigils
    wb, wl = W('B'), W('A')
    bno, _ = LA.own_no_quest(wb)
    c = sigils._module_chr(wl, bno) if bno is not None else None
    bag = wl.q(c + 0x2470) if c else None
    m = wl.q(bag + 0x108) if bag else None
    print('0x%x' % m if m else 'none')


def clearbp(offs):
    from mem import Mem
    from gdb import Gdb
    base = Mem('A').base
    try:
        g = Gdb(6543)
    except OSError as e:
        print('clearbp: no gdbstub on 6543 (%s): nothing set' % e)
        return
    try:
        g.s.sendall(b'\x03')
        try:
            g._recv(timeout=5)
        except socket.timeout:
            pass
        for o in offs:
            g.cmd('z0,%x,4' % (base + o))
        g._send('c')
        time.sleep(0.3)
        print('clearbp: removed %s, A resumed' % ' '.join(hex(o) for o in offs))
    finally:
        g.s.close()


def probe(offs, secs, flt):
    """bpprobe.py with a filter: breakpoints at main+OFFS on A for SECS s; every hit is resumed at once, only hits
    whose registers match flt ({'x19': v} / {'x21': v}, empty = all) are printed (bpprobe's line format), at most
    40; every hit counted. The breakpoints are removed and A resumed on EVERY exit (finally, also on Ctrl+C)."""
    from mem import Mem
    from gdb import Gdb
    base = Mem('A').base
    g = Gdb(6543)
    shown = total = 0
    try:
        print('connected', g.cmd('?')[:20], flush=True)
        for o in offs:
            print('bp main+%#x %s' % (o, g.cmd('Z0,%x,4' % (base + o))), flush=True)
        g._send('c')
        end = time.time() + secs
        while time.time() < end and total < 5000:
            try:
                r = g._recv(timeout=max(0.1, end - time.time()))
            except socket.timeout:
                break
            if r.startswith('O') or r in ('OK', ''):
                continue
            x = g.regs()
            total += 1
            regs = {'x%d' % i: x[i] for i in list(range(0, 9)) + list(range(19, 29))}
            if all(regs.get(k) == v for k, v in flt.items()) and shown < 40:
                shown += 1
                print(time.strftime('%H:%M:%S'), 'hit main+%#x' % (x[32] - base),
                      ' '.join('%s=%#x' % kv for kv in regs.items()), 'lr=main+%#x' % (x[30] - base), flush=True)
            g._send('c')
    finally:
        try:
            g.s.sendall(b'\x03')
            try:
                g._recv(timeout=5)
            except socket.timeout:
                pass
            for o in offs:
                g.cmd('z0,%x,4' % (base + o))
            g._send('c')
            time.sleep(0.3)
        finally:
            g.s.close()
        print('probe done: %d hits in all, %d matching %s shown; breakpoints removed, A resumed' % (
            total, shown, flt or 'any'), flush=True)


def release(secs):
    """LICHII_GDBSTUB suspends the guest until a debugger continues (k_process.cpp: 'suspending guest process until
    a debugger continues execution'; first runlove run: A black for 300 s). Connect to 6543 as soon as it listens,
    continue, close (hp_watch.py does the same)."""
    from gdb import Gdb
    end = time.time() + secs
    while time.time() < end:
        try:
            g = Gdb(6543)
        except OSError:
            time.sleep(1)
            continue
        try:
            print('release: connected', g.cmd('?')[:20], flush=True)
            g._send('c')
            time.sleep(1)
            print('release: A continued', flush=True)
            return 0
        finally:
            g.s.close()
    print('release: no gdbstub on 6543 within %.0f s' % secs, flush=True)
    return 1


def fallback():
    """B: the by-hand hub sequence of handoff 1 (2026-11-16): Minus, R, A, Down, Right x4, A, Plus, L. Only from the
    hub screen (up to 3 B presses first to close a menu pick_sigil.py left open). Y is never pressed."""
    from screen import grab, state, press
    for _ in range(4):
        s = state(grab('B'), 'B')[0]
        if s == 'hub':
            break
        press('B', 'B')
        time.sleep(1.5)
    else:
        print('fallback: B not on the hub screen (%s): nothing pressed' % s)
        return
    for b in ['Minus', 'R', 'A', 'Down', 'Right', 'Right', 'Right', 'Right', 'A', 'Plus', 'L']:
        press('B', b)
        time.sleep(1.5)
    print('fallback: sequence pressed on B; check with pick_bloodsworn.py B show')


def hits(path):
    """[(off, {reg: value})] from bpprobe lines 'HH:MM:SS hit main+0x.. x0=0x.. ...'"""
    out = []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = re.search(r'hit main\+(0x[0-9a-f]+) (.*)', line)
        if m:
            regs = dict((k, int(v, 16)) for k, v in re.findall(r'\b(x\d+)=(0x[0-9a-f]+)', m.group(2)))
            out.append((int(m.group(1), 16), regs))
    return out


def judge(n, path, m=None):
    txt = open(path, encoding='utf-8', errors='replace').read()
    if 'connected' not in txt or 'probe done' not in txt:
        print('RESULT undecided fix -: probe %d did not run cleanly (no gdbstub on 6543? see %s)' % (n, path))
        return
    h = hits(path)
    offs = {o for o, _ in h}
    if n == 1:
        a, b = 0x19C9DD4 in offs, 0x19C9DEC in offs
        if a and b:
            print('RESULT not the prompt (registered: key, list, box, screen, gates all pass) fix 5: the press / bearer '
                  'side (sigil15 case B, 0x118DE34)')
        elif a:
            print('NEXT 3')
        else:
            print('NEXT 2')
    elif n == 2:
        mm = int(m, 16) if m and m != 'none' else None
        mine = [(o, r) for o, r in h if mm is None or r.get('x19') == mm]
        if mm is None:
            print('RESULT undecided fix -: copy M unreadable, probe 2 cannot tell the copy from other chrs (%d hits)' %
                  len(h))
        elif not any(o == 0x19C9DA4 for o, _ in mine):
            print('RESULT key / not reached fix 1: 0x19C9AA0 never passes the key gate for the bearer copy (M 0x%x): '
                  'the copy is not updated through 0xD9B520, or LOVEACCEPT is not active (check the record)' % mm)
        else:
            r = [x for o, x in mine if o == 0x19C9DD0]
            if r and not any(x.get('x0', 0) & 1 for x in r):
                print('RESULT list fix 2: 0x1183E00 returned 0 for the bearer copy (the tool said listed): module key '
                      '/ handle compare, kin8 class')
            elif r:
                print('RESULT undecided fix -: list gate passed in probe 2 but 0x19C9DD4 missed in probe 1 '
                      '(window timing); run again')
            else:
                print('RESULT undecided fix -: key gate passed, 0x19C9DD0 not hit (0x1183E00 SQM missing?)')
    elif n == 3:
        ours = [(o, r) for o, r in h if r.get('x21') == BUTTON]
        box = [r.get('x0', 0) & 1 for o, r in ours if o == 0x19CA1B8]
        scr = [r.get('x0', 0) & 1 for o, r in ours if o == 0x19CA2EC]
        if not box:
            print('RESULT undecided fix -: no 0x19CA1B8 hit for button 100000 (%d hits in all)' % len(h))
        elif not any(box):
            print('RESULT 2 m box fix 3: 0x1B5DB10 returned 0 in %d of %d checks (placement / dummy 80)' %
                  (len(box), len(box)))
        elif scr and not any(scr):
            print('RESULT screen / general gates fix 4: box passed, 0x1B5F6FC returned 0 (%d checks); the '
                  'love_accept geo: line names the gate' % len(scr))
        else:
            print('RESULT undecided fix -: box %s screen %s (mixed)' % (box, scr))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    if a[0] == 'others':
        others()
    elif a[0] == 'copym':
        copym()
    elif a[0] == 'clearbp':
        clearbp([int(t, 16) for t in a[1].split(',')])
    elif a[0] == 'release':
        return release(float(a[1]) if len(a) > 1 else 240)
    elif a[0] == 'fallback':
        fallback()
    elif a[0] == 'probe':
        flt = {}
        for t in a[3:]:
            k, v = t.split('=')
            flt[k] = int(v, 16)
        probe([int(t, 16) for t in a[1].split(',')], float(a[2]), flt)
    elif a[0] == 'judge':
        judge(int(a[1]), a[2], a[3] if len(a) > 3 else None)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
