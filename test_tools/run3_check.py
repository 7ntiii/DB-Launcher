"""Helper of diag/twin/run3.sh (TEST RIG ONLY). Written 2026-11-15 as static work, never run live.

python diag/twin/run3_check.py steps GAMES          one line "A 6 2 B 6 2 C 6 2" (step par+0x50, round par+0xB8; -1 -1 unreadable)
python diag/twin/run3_check.py cpoll [W=C]          alive.sh's line for a game alive.sh does not cover (userC / userD log)
python diag/twin/run3_check.py procs                "A:up B:up C:up" from diag/twin/session.json (GONE = process ended)
python diag/twin/run3_check.py userrun              the user's own game / launcher if running (go4.sh's test), else nothing
python diag/twin/run3_check.py site KILLER VICTIM ALLY GAMES [wait=150]
        Alliance Virtue share (row 35 part, site_virtue_notes.md 1 and 5.3). Waits for an open Ritual Site on the
        KILLER's game, puts VICTIM 1.5 m from a pledge pillar of that site (teleport), sets VICTIM's master HP to 1
        (TEST ONLY, as final_kills.py kill), then KILLER fights VICTIM with killchr.py (KILLER teleported next to it,
        so both stand at the pillar). Reads counter 10040 (CSShelterInsideKillAlliance, record bytes as ritual.py)
        of ALLY's pgd on every game before and after, and 10020 of KILLER.
        Last line: "SITE PASS|PARTIAL|FAIL|SKIP <reason> | <values>"
python diag/twin/run3_check.py final VICTIM GAMES
        Row 19 extra checks after regress_small spectate: on every game VICTIM's stage 04050101, OUT bit
        (chr+0x26E4 & 0x400), elimination entries of VICTIM (deque par+0x38A0 / kill tracker nodes, final_kills.snap),
        and every other game still at step 6. Last line: "FINAL PASS|FAIL <reason> | <values>"
python diag/twin/run3_check.py cleanup              stop ONLY the rig's processes: lichii.exe of build/lichii/bin, and
        python processes whose cwd is under diag/twin (npln_stub, frontdoor, panel_window) or that run a diag/twin /
        diag/net tool from the workspace (twin.py, quic_watch, hold_clock, force_event, ...). Never the user's game
        (another lichii.exe path) or the launcher. Prints every pid it stops.
Writes (all TEST ONLY): site = VICTIM's position and master HP, plus killchr.py's own writes (KILLER's position /
facing, button input). Everything else is read only."""
import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
os.chdir(WS)
sys.path.insert(0, str(WS / 'diag' / 'twin'))

PAR = 0x5B3CDF8


def steps(games):
    from mem import Mem
    out = []
    for w in games:
        try:
            m = Mem(w)
            par = m.u64(m.base + PAR)
            out.append('%s %d %d' % (w, m.u32(par + 0x50), m.u32(par + 0xB8)) if par else '%s -1 -1' % w)
        except Exception:
            out.append('%s -1 -1' % w)
    print(' '.join(out), flush=True)


def cpoll(w):
    f = WS / 'diag' / 'twin' / ('user%s' % w) / 'log' / 'eden_log.txt'
    t, n = [], []
    try:
        for line in open(f, encoding='utf-8', errors='replace'):
            mt = re.match(r'\[\s*([0-9.]+)\]', line)
            if mt:
                t.append(float(mt.group(1)))
                if 'GetCurrentIpAddress' in line:
                    n.append(float(mt.group(1)))
    except OSError as ex:
        print(w, 'no log (%s)' % ex)
        return
    if not t:
        print(w, 'empty log')
        return
    print(w, 'last log %.0f s, last game poll %.0f s, poll age %.0f s' % (t[-1], n[-1] if n else -1, t[-1] - (n[-1] if n else 0)))


def procs():
    import psutil
    try:
        s = json.load(open(WS / 'diag' / 'twin' / 'session.json'))
    except Exception as ex:
        print('no session.json (%s)' % ex)
        return
    print(' '.join('%s:%s' % (w, 'up' if psutil.pid_exists(p) else 'GONE') for w, p in sorted(s['pids'].items())))


def norm(s):
    return (s or '').replace(chr(92), '/').lower()


def userrun():
    import psutil
    rig = 'duskbloodsworkspace/build/lichii/bin/lichii.exe'
    out = []
    for p in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
        name = (p.info['name'] or '').lower()
        exe = norm(p.info['exe'])
        cmd = norm(' '.join(p.info['cmdline'] or []))
        if name == 'lichii.exe' and not exe.endswith(rig):
            out.append('lichii pid %d (%s)' % (p.info['pid'], exe or '?'))
        elif name.startswith('python') and 'launcher' in cmd and 'diag/twin' not in cmd:
            out.append('launcher pid %d' % p.info['pid'])
    if out:
        print('; '.join(out))


def cleanup():
    import psutil
    ws = norm(str(WS))
    rig = ws + '/build/lichii/bin/lichii.exe'
    tools = re.compile(r'twin4?.py|quic_watch|npln_stub|frontdoor|panel_window|hold_clock|force_event|match4|to_hub|'
                       r'to_match|set_rule|regress_small|killchr|final_kills|lives\.py|to_final|clock\.py')
    me = os.getpid()
    victims = []
    for p in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
        if p.info['pid'] in (me, os.getppid()):
            continue
        name = (p.info['name'] or '').lower()
        exe = norm(p.info['exe'])
        cmd = norm(' '.join(p.info['cmdline'] or []))
        try:
            cwd = norm(p.cwd())
        except Exception:
            cwd = ''
        if name == 'lichii.exe':
            if exe == rig:
                victims.append((p, 'rig game'))
            continue
        if not name.startswith('python') or 'launcher' in cmd or 'run3_check' in cmd:
            continue
        under_twin = cwd.startswith(ws + '/diag/twin')
        rig_tool = cwd == ws and ('diag/twin/' in cmd or 'diag/net/' in cmd or 'tools/auto/' in cmd)
        if (under_twin or rig_tool) and tools.search(cmd):
            victims.append((p, cmd[-90:]))
    for p, why in victims:
        try:
            p.kill()
            print('stopped pid %d (%s)' % (p.pid, why))
        except Exception as ex:
            print('could not stop pid %d (%s): %s' % (p.pid, why, ex))
    psutil.wait_procs([p for p, _ in victims], timeout=15)
    print('cleanup: %d rig process(es) stopped' % len(victims))


# ------------------------------------------------------------------ site (row 35 part)
def counter_bytes(x, pgd, cid):
    wp = x.q(pgd + 0x46D8) if pgd else None
    if not wp:
        return None
    n = x.b(wp + 0xC10) or 0
    for k in range(min(n, 48)):
        c = x.q(wp + 0xC18 + 8 * k)
        if c and x.d(c + 8) == cid:
            b, e = x.q(c + 0x38), x.q(c + 0x40)   # vt+0x50 = c+0x10; vector +0x28/+0x30 there (0xE96A7C)
            return (e - b) if b is not None and e is not None else None
    return 0


def pgd_of(x, no):
    gdm = x.g(0x5B57EB8)
    if not gdm:
        return None
    loc = x.q(gdm + 0x20)
    if loc and x.i(loc + 0xD0) == no:
        return loc
    pool = x.q(gdm + 0x30)
    for i in range(12) if pool else []:
        p = pool + i * 0x47F0
        if x.i(p + 0xD0) == no:
            return p
    return None


def site(killer, victim, ally, games, wait):
    import regress_small as RS
    gw = RS.gw
    nk, nv, na = RS.local_no(killer), RS.local_no(victim), RS.local_no(ally)
    if None in (nk, nv, na) or len({nk, nv, na}) < 3:
        print('SITE SKIP player numbers unreadable or equal (killer %s victim %s ally %s) |' % (nk, nv, na))
        return
    t0, sites, pil = time.time(), None, []
    while time.time() - t0 < wait:
        sites, pil = RS.pledge_rows(killer)
        if sites and any(cl == 0 for _, cl in sites):
            break
        time.sleep(3.0)
    if not sites or all(cl != 0 for _, cl in sites):
        print('SITE SKIP no open Ritual Site on %s after %d s (sites %s) |' % (killer, wait, sites))
        return
    pos = None
    for p in pil:
        g = gw(killer).geom_from_handle(p['h']) if p['h'] else None
        pos = gw(killer).geom_pos(g) if g else None
        if pos:
            break
    if not pos:
        print('SITE SKIP open site but no pledge pillar position on %s (pillars %s) |' % (killer, pil))
        return

    def snap():
        out = {}
        for w in games:
            x = gw(w)
            out[w] = (counter_bytes(x, pgd_of(x, na), 10040), counter_bytes(x, pgd_of(x, nk), 10020))
        return out
    s0 = snap()
    print('pillar at %.1f %.1f %.1f; before {game: (ally %s 10040 B, killer %s 10020 B)} %s' % (
        pos[0], pos[1], pos[2], na, nk, s0), flush=True)
    xv = gw(victim)
    xv.goto((pos[0] + 1.5, pos[1] + 0.3, pos[2]), None, True)
    time.sleep(2.0)
    e = xv.player_entry(0)
    if not e or not e[3]:
        print('SITE SKIP no local player entry on %s |' % victim)
        return
    xv.write(e[3] + 0xF30, struct.pack('<i', 1))
    rows = {r['no']: r for r in RS.player_rows(killer)}
    vc = rows.get(nv, {}).get('chr')
    if not vc:
        print('SITE SKIP %s does not see player %s (%s) |' % (killer, nv, sorted(rows)))
        return
    try:
        rc = subprocess.run([sys.executable, 'diag/twin/killchr.py', killer, 'chr=0x%X' % vc, 'rounds=16', 'dist=1.5'],
                            cwd=WS, timeout=150, capture_output=True, text=True).returncode
    except subprocess.TimeoutExpired:
        rc = 'timeout'
    time.sleep(8.0)
    s1 = snap()
    vals = 'killchr rc %s | before %s after %s (ally %s 10040 bytes, killer %s 10020 bytes)' % (rc, s0, s1, na, nk)
    # the share (0xE96A3C..0xE96AB4, every game runs the 0xB0 chain once with SWORD_B0_ALL): ONE 0x18-byte record
    # appended to counter 10040 of the ally's pgd (and one to 10020 of the killer's), on every game
    REC = 0x18
    up = {w: (s1[w][0] or 0) > (s0[w][0] or 0) for w in games}
    one = {w: (s1[w][0] or 0) - (s0[w][0] or 0) == REC for w in games}
    kone = {w: (s1[w][1] or 0) - (s0[w][1] or 0) == REC for w in games}
    if rc != 0 and not any(up.values()):
        print('SITE FAIL victim %s not killed by %s (killchr rc %s) | %s' % (victim, killer, rc, vals))
    elif all(one.values()):
        print('SITE PASS ally %s 10040 +1 record (+24 B) on every game (%s); killer %s 10020 +1 record on %s | %s' % (
            ally, games, killer, ''.join(w for w in games if kone[w]) or 'none', vals))
    elif all(up.values()):
        print('SITE PARTIAL ally %s 10040 rose on every game but not by exactly one record (+24 B) on %s | %s' % (
            ally, ''.join(w for w in games if not one[w]), vals))
    elif up.get(ally):
        print('SITE PARTIAL 10040 rose on %s itself but not on %s | %s' % (
            ally, ''.join(w for w in games if not up[w]), vals))
    else:
        print('SITE FAIL kill inside the site but 10040 of %s did not rise on %s | %s' % (
            ally, ''.join(w for w in games if not up[w]), vals))


# ------------------------------------------------------------------ final (row 19 extras)
def final(victim, games):
    import regress_small as RS
    import final_kills as FK
    nv = RS.local_no(victim)
    per, ok_stage, ok_once, ok_others = {}, True, True, True
    out_own = None
    for w in games:
        try:
            s = FK.snap(RS.gw(w)) or {}
        except Exception as ex:                       # a game whose stage is gone must not hide the others
            s = {}
            print('%s: final_kills.snap failed: %s' % (w, ex), flush=True)
        st = RS.step_round(w)
        pl = next((p for p in s.get('players', []) if p['no'] == nv), None)
        stage = pl['stage'] if pl else None
        out = bool(pl['26e4'] & 0x400) if pl and pl['26e4'] is not None else None
        ev = (s.get('deque') or (0, []))[1]
        dq = sum(1 for x in ev if x and x[0] == nv)
        nd = sum(1 for v, dead in s.get('nodes', []) if v == nv and dead)
        per[w] = 'step %s stage %s out %s deque %d nodes %d' % (st, stage, out, dq, nd)
        ok_stage &= stage == '04050101'
        ok_once &= dq == 1 or (dq == 0 and nd == 1)
        if w == victim:
            out_own = out
        elif st[0] != 6:
            ok_others = False
    vals = 'victim %s (player %s): %s' % (victim, nv, '; '.join('%s %s' % kv for kv in per.items()))
    if ok_stage and ok_once and ok_others and out_own:
        print('FINAL PASS stage 04050101 + elimination once on every game, OUT on %s, others at step 6 | %s' % (victim, vals))
    else:
        print('FINAL FAIL stage ok %s, once ok %s, OUT on own %s, others at step 6 %s | %s' % (
            ok_stage, ok_once, out_own, ok_others, vals))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    opts = {k: v for k, _, v in (x.partition('=') for x in a if '=' in x)}
    a = [x for x in a if '=' not in x]
    if a[0] == 'steps':
        steps(a[1] if len(a) > 1 else 'AB')
    elif a[0] == 'cpoll':
        cpoll(a[1] if len(a) > 1 else 'C')
    elif a[0] == 'procs':
        procs()
    elif a[0] == 'userrun':
        userrun()
    elif a[0] == 'cleanup':
        cleanup()
    elif a[0] == 'site' and len(a) >= 5:
        site(a[1], a[2], a[3], a[4], float(opts.get('wait', 150)))
    elif a[0] == 'final' and len(a) >= 3:
        final(a[1], a[2])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
