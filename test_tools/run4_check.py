"""Helper of diag/twin/run4.sh, the 4-game programme (TEST RIG ONLY). Written 2026-11-17 as static work, never run.
Notes: diag/net/run4_notes.md. Expected values: diag/net/players8_notes.md 0 (who is cut), bbfinal_notes.md 5,
assist_v396_notes.md 4b / 4c. Read only, except `kill2` (killchr.py's own writes: the killer's position, facing and
buttons; no HP write anywhere).

python diag/twin/run4_check.py commit NEED_GB      free commit + paging-file growth vs NEED_GB (precheck)
python diag/twin/run4_check.py prereq              exe has lazy commit? twin4.py passes per-game texture caps? userD?
python diag/twin/run4_check.py vram GAMES          VRAM / memory health: fatal log lines -> "VRAM STOP ...", else
                                                   "VRAM ok ..." with the live per-game GiB (card + paged out)
python diag/twin/run4_check.py lazy GAMES          commit mode per game: log line if shown, else the process's
                                                   mapped-memory split (VirtualQueryEx, query only)
python diag/twin/run4_check.py nos GAMES           "A=1 B=2 C=3 D=4" (local player numbers)
python diag/twin/run4_check.py cuts ROUND KEEP EXPECT GAMES [teams]
        After the cut of ROUND (2 or 3): per game the F1 cut list of that round from dusk_lan.txt (cutcheck.parse),
        the H1 / F4 cut lines of rounds ROUND..ROUND+1, the phase entries in memory (no, rank, state), and the
        game's step / round. KEEP = players kept (6 after II, 3 after III); EXPECT = how many must go (4 players:
        0 after II, 1 after III; Bloodbound with 2 pairs: 0 and 0, then pass `teams`: no rank test, nobody out).
        Last line "CUT PASS|FAIL|SKIP <reason> | <values>"; a line "CUTNOS <nos>" before it names the culled numbers.
python diag/twin/run4_check.py final GAMES [ALL] [order=N,N,N]
        Standard final over: result rows (no, rank) equal on the finalists GAMES; the "final placement" line present
        and equal on ALL (every game of the match, culled ones too); no "review3 F1 bound" run-down; optional rank
        order (player numbers, rank 1 first). "FINAL PASS|FAIL|SKIP ..."
python diag/twin/run4_check.py cutlog ROUND GAMES [hold_max=1.5] [teams]
        After the cut of ROUND (2 / 3, 4 games; cutauth_notes 4, audit_v401_notes 2.4): per game the CUTAUTH lines
        (phase end waits, list in the mailbox + clock held T s, cut here / by the authority: same), the V400-1
        answers and send count on the authority, the F1 verdict, the mailbox (u32 key main+0xC50F318, rank bytes
        +8) and each guest's cut time after the authority's. "AUTH PASS|FAIL ..."
python diag/twin/run4_check.py finalstate GAMES VICTIM   after VICTIM's last death in a 3+ player final: VICTIM at
        its result screen (29..36), the others in (6, 4) with an "out of the final" line for it, no early run-down.
python diag/twin/run4_check.py finalon GAMES       every game still in step 6 of round 4. "ON ..."
python diag/twin/run4_check.py netsim GAMES        LICHII_NET_SIM arrived (twin4 line + emulator-log start line,
                                                   no parse error) on every game given. "NETSIM ..."
python diag/twin/run4_check.py bbfinal GAMES       Bloodbound final over (bbfinal_notes 5.3 / 5.4): entries, ranks
                                                   255, row place +0x50, pair placement line equal. "BBFINAL ..."
python diag/twin/run4_check.py pairs GAMES         pairs.py parsed: rule 2 everywhere and pairs equal. "PAIRS ..."
python diag/twin/run4_check.py kill2 KILLER VICTIM two REAL deaths of VICTIM by KILLER (killchr.py, spectate_notes
                                                   3: wait until the respawn is over in between). "KILL2 ..."
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
os.chdir(WS)
sys.path.insert(0, str(WS / 'diag' / 'twin'))
TWIN = WS / 'diag' / 'twin'
APPDATA = Path(os.environ.get('APPDATA', ''))
PAR_G = 0x5B3CDF8


def eden_log(w):
    return APPDATA / 'eden' / 'log' / 'eden_log.txt' if w == 'A' else TWIN / ('user%s' % w) / 'log' / 'eden_log.txt'


def lan_log(w):
    return APPDATA / 'eden' / 'log' / 'dusk_lan.txt' if w == 'A' else TWIN / ('user%s' % w) / 'log' / 'dusk_lan.txt'


def ps(cmd, timeout=60):
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception as ex:
        return 'ERR %s' % ex


# ------------------------------------------------------------------ commit / prerequisites
def commit_info():
    """Commit limit and growth room, all in GB. The limit = RAM + paging file; a system-managed paging file can grow
    to 3 x RAM, limited by C: free (we keep 10 GB of C: free)."""
    out = ps('$o = Get-CimInstance Win32_OperatingSystem; $c = Get-CimInstance Win32_ComputerSystem; '
             '$p = (Get-CimInstance Win32_PageFileUsage | Measure-Object AllocatedBaseSize -Sum).Sum; '
             '$f = (Get-PSDrive C).Free; '
             '[string]::Format([cultureinfo]::InvariantCulture, "{0} {1} {2} {3} {4} {5}", '
             '$o.TotalVirtualMemorySize, $o.FreeVirtualMemory, $c.TotalPhysicalMemory, $c.AutomaticManagedPagefile, '
             '$p, $f)')
    try:
        lim_kb, free_kb, ram_b, auto, pf_mb, cfree_b = out.split()
    except ValueError:
        return None, out
    lim, free = float(lim_kb) / 2**20, float(free_kb) / 2**20
    ram, pf, cfree = float(ram_b) / 2**30, float(pf_mb or 0) / 1024, float(cfree_b) / 2**30
    grow = max(0.0, min(3 * ram, pf + max(0.0, cfree - 10)) - pf) if auto.lower() == 'true' else 0.0
    return {'limit': lim, 'used': lim - free, 'free': free, 'ram': ram, 'auto': auto, 'pagefile': pf,
            'cfree': cfree, 'grow': grow, 'headroom': free + grow}, out


def commit(need):
    c, raw = commit_info()
    if not c:
        print('COMMIT SKIP unreadable (%s)' % raw)
        return
    txt = ('limit %.1f used %.1f free %.1f GB | RAM %.1f | paging file %.1f GB, system-managed %s, can grow %.1f | '
           'C: free %.1f | headroom %.1f, need %.1f' % (c['limit'], c['used'], c['free'], c['ram'], c['pagefile'],
                                                        c['auto'], c['grow'], c['cfree'], c['headroom'], need))
    print('COMMIT %s %s' % ('ok' if c['headroom'] >= need else 'LOW', txt))


def prereq():
    exe = WS / 'build' / 'lichii' / 'bin' / 'lichii.exe'
    try:
        lazy = b'lazy commit on first touch' in exe.read_bytes()
    except OSError:
        lazy = None
    tw = (TWIN / 'twin4.py').read_text(encoding='utf-8', errors='replace')
    caps = 'TWIN_TC_MAX_' in tw
    lazyenv = 'LICHII_LAZY_COMMIT' in tw
    userd = (TWIN / 'userD' / 'config').is_dir()
    print('PREREQ exe_lazy=%s twin_caps=%s twin_lazy=%s userD=%s' % (lazy, caps, lazyenv, userd))


# ------------------------------------------------------------------ VRAM / memory health
FATAL = [('device lost', r'DEVICE_LOST|device lost'), ('failed image', r'Image \d+x\d+x\d+ .* failed:'),
         ('RT unbacked', r'Render target in unbacked image'), ('lazy commit failed', r'Lazy commit failed'),
         ('commit 1455', r'1455|paging file is too small')]
WARN = [('over budget', r'is over the memory budget'), ('unbacked', r'does not fit; using an unbacked'),
        ('host memory', r'placed in host memory'), ('OOM margin', r'Out of device memory: keeping'),
        ('no fastmem', r'Failed to allocate \d+ MiB of backing memory')]


def scan(path, kinds):
    hits = {k: 0 for k, _ in kinds}
    try:
        for line in open(path, encoding='utf-8', errors='replace'):
            for k, pat in kinds:
                if re.search(pat, line):
                    hits[k] += 1
    except OSError:
        return None
    return {k: v for k, v in hits.items() if v}


def vram_live():
    cmd = r'''
$s = Get-Content diag/twin/session.json -Raw | ConvertFrom-Json
$map = @{}; $s.pids.PSObject.Properties | ForEach-Object { $map[[string]$_.Value] = $_.Name }
$out = @{}
foreach ($k in "Dedicated Usage", "Shared Usage") {
  (Get-Counter "\GPU Process Memory(*)\$k" -ErrorAction SilentlyContinue).CounterSamples | ForEach-Object {
    $p = ($_.InstanceName -split "_")[1]
    if ($map.ContainsKey($p)) { $out["$($map[$p]) $k"] = [math]::Round($_.CookedValue / 1GB, 2) } } }
$card = ((Get-Counter "\GPU Adapter Memory(*)\Dedicated Usage" -ErrorAction SilentlyContinue).CounterSamples |
         Measure-Object CookedValue -Maximum).Maximum / 1GB
$games = ($map.Values | Sort-Object | ForEach-Object { "$_ {0}+{1}" -f $out["$_ Dedicated Usage"], $out["$_ Shared Usage"] }) -join ", "
[string]::Format([cultureinfo]::InvariantCulture, "GiB on card+paged out: {0}; card total {1:F1} GiB", $games, $card)
'''
    return ps(cmd, 90)


def vram(games):
    fatal, warn = {}, {}
    for w in games:
        f = scan(eden_log(w), FATAL)
        if f is None:
            fatal[w] = {'no log': 1}
            continue
        if f:
            fatal[w] = f
        x = scan(eden_log(w), WARN)
        if x:
            warn[w] = x
    live = vram_live()
    c, _ = commit_info()
    mem = ('commit used %.1f of %.1f GB, headroom %.1f GB' % (c['used'], c['limit'], c['headroom'])
           if c else 'commit unreadable') + ' | ' + procmem(games) + ' | mode ' + ' '.join(memmode(games))
    low = c is not None and c['headroom'] < 2.0
    if fatal or low:
        print('VRAM STOP fatal %s%s | warnings %s | %s | %s' % (fatal, ' commit headroom under 2 GB' if low else '',
                                                               warn or '-', live, mem))
    else:
        print('VRAM ok warnings %s | %s | %s' % (warn or 'none', live, mem))


def session_pids():
    try:
        return {k: int(v) for k, v in json.load(open(TWIN / 'session.json'))['pids'].items()}
    except Exception:
        return {}


def mapped_split(pid):
    """(committed GiB, reserved GiB) of the MEM_MAPPED regions of a process, by VirtualQueryEx (query only: no
    memory of the game is read or written). The backing buffer is a pagefile-backed section mapped into the
    arena: full commit (SEC_COMMIT) shows its views as MEM_COMMIT; lazy (SEC_RESERVE) shows the untouched part as
    MEM_RESERVE until first touch [D: VirtualQueryEx / SEC_RESERVE; I: no other large mapped reserve exists]."""
    import ctypes
    from ctypes import wintypes as wt

    class MBI(ctypes.Structure):
        _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                    ('AllocationProtect', wt.DWORD), ('PartitionId', wt.WORD), ('RegionSize', ctypes.c_size_t),
                    ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.OpenProcess.restype = wt.HANDLE
    k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
    k32.VirtualQueryEx.restype = ctypes.c_size_t
    h = k32.OpenProcess(0x0400, False, pid)               # PROCESS_QUERY_INFORMATION
    if not h:
        return None
    com = res = 0
    addr, mbi = 0, MBI()
    try:
        while addr < 0x7FFFFFFF0000:
            if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
                break
            size = mbi.RegionSize or 0x1000
            if mbi.Type == 0x40000:                           # MEM_MAPPED
                if mbi.State == 0x1000:
                    com += size
                elif mbi.State == 0x2000:
                    res += size
            addr = (mbi.BaseAddress or 0) + size
    finally:
        k32.CloseHandle(h)
    return com / 2**30, res / 2**30


def memmode(games):
    pids = session_pids()
    out = []
    for w in games:
        p = pids.get(w)
        sp = mapped_split(p) if p else None
        if not sp:
            out.append('%s=?(no pid / no access)' % w)
            continue
        com, res = sp
        # run4_dry_notes.md fix 4: no backing section mapped at all (its CreateFileMapping2 failed, the game runs
        # on the fallback buffer without fastmem) used to read as 'full'
        mode = 'lazy' if res > 2.0 else 'full' if com > 8.0 else 'nofastmem'
        out.append('%s=%s(mapped commit %.1f reserve %.1f GiB)' % (w, mode, com, res))
    return out


def lazy(games):
    """mode per game: the Backing memory log line when the log shows it (HW.Memory Info is hidden by the rig's
    log_filter '*:Warning', run4_notes 7), else the mapped-memory split of the process"""
    logm = {}
    for w in games:
        try:
            for line in open(eden_log(w), encoding='utf-8', errors='replace'):
                if 'Backing memory' in line:
                    logm[w] = 'lazy' if 'lazy commit on first touch' in line else 'full'
                elif re.search(r'Failed to allocate \d+ MiB of backing memory', line):   # Critical: shown
                    logm[w] = 'nofastmem'
        except OSError:
            pass
    mm = memmode(games)
    print('MEMMODE ' + ' '.join(mm) + (' | log %s' % logm if logm else ' | log: no Backing memory line'))
    print('LAZY ' + ' '.join('%s=%s' % (w, logm.get(w) or m.split('=', 1)[1].split('(')[0])
                             for w, m in zip(games, mm)))


def procmem(games):
    """Get-Process per game: private bytes (PrivateMemorySize64), paged (PagedMemorySize64), working set, GB.
    The backing section's commit is charged to the system, not to private bytes [D], so lazy vs full shows in
    the system commit and in memmode, not here."""
    pids = session_pids()
    ids = ','.join(str(pids[w]) for w in games if w in pids)
    if not ids:
        return 'procmem: no pids'
    out = ps('Get-Process -Id %s -ErrorAction SilentlyContinue | ForEach-Object { [string]::Format('
             '[cultureinfo]::InvariantCulture, "{0} {1:F1} {2:F1} {3:F1}", $_.Id, $_.PrivateMemorySize64/1GB, '
             '$_.PagedMemorySize64/1GB, $_.WorkingSet64/1GB) }' % ids)
    byid = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0].isdigit():
            byid[int(parts[0])] = parts[1:]
    return 'procmem GB private/paged/ws: ' + ' '.join(
        '%s %s' % (w, '/'.join(byid[pids[w]]) if pids.get(w) in byid else 'gone') for w in games)


# ------------------------------------------------------------------ cuts
def phase_entries(x):
    par = x.g(PAR_G)
    if not par:
        return None
    n = x.d(par + 0x3858) or 0
    out = []
    for i in range(min(n, 12)):
        e = x.rd(par + 0x33D0 + 0x60 * i, 0x60)
        if e:
            out.append((int.from_bytes(e[0:4], 'little', signed=True), int.from_bytes(e[0x10:0x14], 'little'),
                        int.from_bytes(e[0x20:0x24], 'little'), e[0x40:0x44].hex()))
    return sorted(out)


def result_rows(x):
    par = x.g(PAR_G)
    if not par:
        return None
    n = x.d(par + 0x45F0) or 0
    out = []
    for i in range(min(n, 8)):
        r = x.rd(par + 0x3968 + 0x190 * i, 0x90)
        if r:
            out.append((int.from_bytes(r[0:4], 'little', signed=True), int.from_bytes(r[0x20:0x24], 'little'),
                        int.from_bytes(r[0x50:0x54], 'little'), int.from_bytes(r[0x80:0x82], 'little', signed=True)))
    return sorted(out)


def last_match(w):
    import cutcheck
    try:
        g = cutcheck.parse(w, str(lan_log(w)))
    except OSError:
        return None, None
    return g, (g.matches[-1] if g.matches else None)


def cuts(rnd, keep, expect, games, teams):
    import regress_small as RS
    nos = {w: RS.local_no(w) for w in games}
    per, hashes, rank_cut, logged, ents, steps = {}, {}, {}, {}, {}, {}
    for w in games:
        g, m = last_match(w)
        lists = m[rnd].cutlists if m and rnd in m else []
        verd = m[rnd].verdicts if m and rnd in m else []
        cl = set()
        for r in (rnd, rnd + 1):
            if m and r in m:
                cl |= m[r].cut
        logged[w] = cl
        if lists:
            step, entries, hsh, role = lists[-1]
            hashes[w] = hsh
            rank_cut[w] = set() if teams else {no for no, rk, _t in entries if rk > keep}
            per[w] = 'F1 %s %s %s' % (role, hsh, ' '.join('%d:%d' % (no, rk) for no, rk, _t in entries))
        else:
            per[w] = 'F1 none'
        if verd:
            per[w] += ' [%s]' % verd[-1]
        ents[w] = phase_entries(RS.gw(w))
        steps[w] = RS.step_round(w)
    out_games = {nos[w] for w in games if steps[w] != (6, rnd + 1)}
    vals = '; '.join('%s(no %s) step %s %s | H1/F4 cut %s | entries %s' % (
        w, nos[w], steps[w], per[w], sorted(logged[w]) or '-', ents[w]) for w in games)
    if not hashes:
        print('CUTNOS ' + ' '.join(str(n) for n in sorted(out_games)))
        print('CUT SKIP no F1 cut list of round %d in any log (build without v3.9.4?) | %s' % (rnd, vals))
        return
    cutset = set().union(*rank_cut.values()) if rank_cut else set()
    print('CUTNOS ' + ' '.join(str(n) for n in sorted(cutset | out_games)))
    bad = []
    if len(hashes) < len(games):
        bad.append('F1 list missing on %s' % ''.join(w for w in games if w not in hashes))
    if len(set(hashes.values())) > 1:
        bad.append('F1 hashes differ %s' % hashes)
    if len({frozenset(v) for v in rank_cut.values()}) > 1:
        bad.append('cut by rank differs %s' % {w: sorted(v) for w, v in rank_cut.items()})
    if not teams and len(cutset) != expect:
        bad.append('%d cut by rank, expected %d' % (len(cutset), expect))
    if out_games != cutset:
        bad.append('games out of the next phase %s != cut %s' % (sorted(out_games), sorted(cutset)))
    for w in games:
        if nos[w] in cutset:
            continue
        if logged[w] - cutset:
            bad.append('%s logged a cut of %s' % (w, sorted(logged[w] - cutset)))
        if cutset and not cutset <= logged[w]:
            bad.append('%s has no H1/F4 line for %s' % (w, sorted(cutset - logged[w])))
    live = [w for w in games if nos[w] not in cutset]
    if len({json.dumps(ents[w]) for w in live}) > 1:
        bad.append('phase entries differ between the games that play on')
    if bad:
        print('CUT FAIL %s | %s' % ('; '.join(bad), vals))
    else:
        print('CUT PASS round %d: cut %s on every game (expected %d), same F1 hash, entries equal | %s' % (
            rnd, sorted(cutset) or 'nobody', expect, vals))


R_PLACE = re.compile(r'final placement \(step \d+\): (.*)')


def placement_lines(w):
    out = []
    try:
        for line in open(lan_log(w), encoding='utf-8', errors='replace'):
            m = R_PLACE.search(line)
            if m:
                out.append(re.sub(r'\(\d+(\.\d+)? s left\)', '(s left)', m[1]).strip())
    except OSError:
        pass
    return out[-1] if out else None


def final(games, *more):
    """final FINALISTS [ALL] [order=N,N,..]: result ranks equal on the finalists; with ALL (every game of the match,
    the culled one too) the 'final placement' line must be present and equal on all of them; order = the player
    numbers expected in rank order (first = rank 1); no 'review3 F1 bound' run-down on any game."""
    import regress_small as RS
    allg = next((x for x in more if re.fullmatch(r'[A-D]+', x)), games)
    order = next(([int(n) for n in x.split('=', 1)[1].split(',') if n] for x in more if x.startswith('order=')), None)
    rows = {w: result_rows(RS.gw(w)) for w in games}
    steps = {w: RS.step_round(w) for w in allg}
    pl = {w: placement_lines(w) for w in allg}
    bound = {w: sum(1 for _, s in match_lines(w) if L_BOUND.search(s)) for w in allg}
    vals = '; '.join('%s step %s rows (no, rank, place, Virtue) %s | placement %s | bound %d' % (
        w, steps[w], rows.get(w, 'not a finalist'), (pl[w] or '-')[:160], bound[w]) for w in allg)
    if not any(rows.values()):
        print('FINAL SKIP no result rows on any game yet | %s' % vals)
        return
    ranks = {w: [(no, rk) for no, rk, _p, _v in rows[w]] for w in games if rows[w]}
    same = len({json.dumps(v) for v in ranks.values()}) == 1
    bad = []
    if not same or len(ranks) != len(games):
        bad.append('result ranks equal %s (on %s)' % (same, ''.join(ranks)))
    if any(not pl[w] for w in allg):
        bad.append('no "final placement" line on %s' % ''.join(w for w in allg if not pl[w]))
    if len({v for v in pl.values() if v}) > 1:
        bad.append('"final placement" lines differ')
    if any(bound.values()):
        bad.append('"review3 F1 bound" run-down on %s' % ''.join(w for w in allg if bound[w]))
    if order and ranks:
        got = [no for no, rk in sorted(next(iter(ranks.values())), key=lambda r: r[1]) if no in order]
        if got != order:
            bad.append('rank order %s, expected %s' % (got, order))
    if bad:
        print('FINAL FAIL %s | %s' % ('; '.join(bad), vals))
    else:
        print('FINAL PASS result ranks equal on %s, placement line equal on %s%s | %s' % (
            games, allg, ', order %s' % order if order else '', vals))


def bbfinal(games):
    import regress_small as RS
    nos = {w: RS.local_no(w) for w in games}
    ents = {w: phase_entries(RS.gw(w)) for w in games}
    rows = {w: result_rows(RS.gw(w)) for w in games}
    pl = {w: placement_lines(w) for w in games}
    signs = {}
    for w in games:
        try:
            txt = open(lan_log(w), encoding='utf-8', errors='replace').read()
        except OSError:
            txt = ''
        s = [k for k in ('every pair is out', '1 pair(s) in this final') if k in txt]
        if s:
            signs[w] = s
    vals = '; '.join('%s(no %s) entries %s | rows %s | placement %s' % (w, nos[w], ents[w], rows[w], (pl[w] or '-')[:200])
                     for w in games)
    bad = []
    if sorted(nos.values()) != [1, 2, 3, 4]:
        bad.append('player numbers %s, not 1..4 (pairs assumed (1,2) (3,4))' % nos)
    ok12 = ('04020001', '04040001', '04040101')
    ok34 = ('04050101', '04030101')
    for w in games:
        e = ents[w] or []
        if len(e) != 4:
            bad.append('%s has %d entries' % (w, len(e)))
            continue
        for no, rk, team, st in e:
            if rk != 0xFF:
                bad.append('%s entry %d rank %d (want 255)' % (w, no, rk))
            if (no in (1, 2) and st not in ok12) or (no in (3, 4) and st not in ok34):
                bad.append('%s entry %d state %s' % (w, no, st))
        r = rows[w] or []
        for no, rk, place, _v in r:
            if place != (1 if no in (1, 2) else 2):
                bad.append('%s row %d place %d' % (w, no, place))
    if len({json.dumps(ents[w]) for w in games}) > 1:
        bad.append('entries differ between games')
    if len({pl[w] for w in games}) > 1 or not all(pl.values()):
        bad.append('pair placement line missing or different')
    if signs:
        bad.append('fail signs %s' % signs)
    if not any(ents.values()):
        print('BBFINAL SKIP no phase entries readable | %s' % vals)
    elif bad:
        print('BBFINAL FAIL %s | %s' % ('; '.join(bad)[:500], vals))
    else:
        print('BBFINAL PASS pair (1+2) place 1, pair (3+4) place 2, ranks 255, same entries and placement on %s | %s'
              % (games, vals))


def pairs(games):
    try:
        out = subprocess.run([sys.executable, 'diag/twin/pairs.py', games], capture_output=True, text=True,
                             timeout=120, cwd=WS).stdout
    except subprocess.TimeoutExpired:
        print('PAIRS FAIL pairs.py timed out |')
        return
    rules = re.findall(r'^([A-D]) .*\| rule (\d+)', out, re.M)
    eq = re.search(r'pairs \(a, b, slot\) equal on all games read: (yes|NO)', out)
    ent = re.findall(r'^  ([A-D]) entries (.*?) \|', out, re.M)
    vals = 'rules %s | equal %s | entries %s' % (rules, eq[1] if eq else '?', ent)
    if len(rules) == len(games) and all(r == '2' for _, r in rules) and eq and eq[1] == 'yes':
        print('PAIRS PASS rule 2 on %s, pairs equal | %s' % (games, vals))
    else:
        print('PAIRS FAIL | %s | %s' % (vals, out.strip().splitlines()[-1] if out.strip() else 'no output'))


# ------------------------------------------------------------------ two real deaths
def kill2(killer, victim):
    import regress_small as RS
    nv = RS.local_no(victim)
    xv = RS.gw(victim)
    log = []

    def vstate():
        e = xv.player_entry(0)
        if not e or not e[0]:
            return None
        c = e[0]
        data = xv.q(c + 0x20)
        return {'hp': xv.i(e[3] + 0xF30) if e[3] else None, 'rsp': (xv.b(data + 0x2D0) or 0) & 1 if data else None,
                'flag16': bool((xv.d(c + 0x26E4) or 0) & 0x10000), 'out': bool((xv.d(c + 0x26E4) or 0) & 0x400),
                'pend': xv.b(c + 0x25E9)}
    for life in (1, 2):
        vc = next((r['chr'] for r in RS.player_rows(killer) if r['no'] == nv), None)
        if not vc:
            print('KILL2 SKIP %s does not see player %s | %s' % (killer, nv, log))
            return
        try:
            rc = subprocess.run([sys.executable, 'diag/twin/killchr.py', killer, 'chr=0x%X' % vc, 'seconds=60', 'every=3'],
                                cwd=WS, timeout=120, capture_output=True, text=True).returncode
        except subprocess.TimeoutExpired:
            rc = 'timeout'
        time.sleep(3.0)
        log.append('death %d: killchr rc %s, victim %s' % (life, rc, vstate()))
        if rc != 0 and ((vstate() or {}).get('hp') or 0) > 0:
            print('KILL2 FAIL victim %s survived 60 s of real hits (death %d) | %s' % (victim, life, log))
            return
        if life == 1:
            t0, done = time.time(), False
            while time.time() - t0 < 60:
                s = vstate() or {}
                if (s.get('hp') or 0) > 0 and not s.get('rsp') and not s.get('flag16') and not s.get('pend'):
                    done = True
                    break
                time.sleep(1.0)
            if not done:
                print('KILL2 FAIL no finished respawn within 60 s after death 1 | %s' % log)
                return
            time.sleep(5.0)
    print('KILL2 PASS two real deaths of %s (player %s) | %s' % (victim, nv, log))


def nos(games):
    import regress_small as RS
    print(' '.join('%s=%s' % (w, RS.local_no(w)) for w in games))


# ------------------------------------------------------------------ v400 / v401 CUTAUTH after a cut
# Log lines (dusk_lan.cpp as built: v401c CutAuth, V400-1 CutCheck; cutauth_notes.md 4, audit_v401_notes 2.4).
CUTAUTH_BOX, CUTAUTH_KEY = 0xC50F318, 0xC0710000
L_TIME = re.compile(r'^(\d\d):(\d\d):(\d\d) (.*)$')
L_WAIT = re.compile(r'cut \(CUTAUTH\): round (\d+): our phase end waits for the authority')
L_IN = re.compile(r'cut \(CUTAUTH\): round (\d+): the authority\'s list \(player (\d+), hash ([0-9a-f]{8})\) is in the '
                  r'mailbox.*?our cut will use it(?: \(clock held ([\d.]+) s, (\d+) raise\(s\)\))?')
L_SAME = re.compile(r'cut \(CUTAUTH\): round (\d+): cut here((?: \d+)+| none), cut by the authority((?: \d+)+| none): '
                    r'(same|DIFFERENT)')
L_TIMEOUT = re.compile(r'cut \(CUTAUTH\): round (\d+): no list from the authority in (\d+) s')
L_MISSING = re.compile(r'cut \(CUTAUTH\): the group is not in this build')
L_ACK = re.compile(r'cut check \(V400-1\): round (\d+): (every listed player has our list|!!! not every listed player '
                   r'answered in 10 s) after (\d+) send\(s\), ([\d.]+) s \(answered by([ \d]*| nobody)\)')
L_EARLY = re.compile(r'cut check \(V400-1\): round (\d+): the authority.s list .*came before our own cut step')
L_AHASH = re.compile(r'cut check \(V400-1\): round (\d+): player (\d+) answered with hash')
L_F1LIST = re.compile(r'cut check \(F1\): round (\d+) step \d+: our list .*?(we are the authority|compared with)')
L_F1SAME = re.compile(r'cut check \(F1\): round (\d+): same list as the authority')
L_F1MISS = re.compile(r'CUT MISMATCH \(F1\) round (\d+)')
L_BOUND = re.compile(r'review3 F1 bound')
L_OUT = re.compile(r'final: player (\d+) is out of the final for good')


def match_lines(w):
    """(seconds, text) of the last match in that game's dusk_lan.txt (from its last 'map: new match')."""
    try:
        text = open(lan_log(w), encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return []
    out, day, last = [], 0, None
    for line in text:
        m = L_TIME.match(line)
        if not m:
            continue
        sec = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
        if last is not None and sec + 43200 < last:
            day += 86400
        last = sec
        if 'map: new match' in m[4]:
            out = []
        out.append((sec + day, m[4]))
    return out


def cutlog(rnd, games, hold_max, teams):
    """After the cut of ROUND on every game: CUTAUTH lines (wait, mailbox in + hold, cut here / by the authority),
    V400-1 answers / resends, the F1 verdict, the mailbox (key + rank bytes) and how much later each guest ended
    the phase than the authority (F1 snapshot times, 1-s resolution). 4+ games, rounds 2 / 3 only."""
    import regress_small as RS
    nos = {w: RS.local_no(w) for w in games}
    info, auth = {}, []
    for w in games:
        d = {'wait': False, 'in': None, 'held': None, 'raises': 0, 'same': None, 'timeout': False, 'missing': False,
             'ack': None, 'early': False, 'ahash': 0, 'role': None, 'f1t': None, 'f1': None}
        for sec, s in match_lines(w):
            if L_MISSING.search(s):
                d['missing'] = True
            m = L_F1LIST.search(s)
            if m and int(m[1]) == rnd and d['f1t'] is None:
                d['f1t'], d['role'] = sec, 'authority' if m[2].startswith('we are') else 'guest'
                continue
            for rx, key in ((L_WAIT, 'wait'), (L_TIMEOUT, 'timeout'), (L_EARLY, 'early')):
                m = rx.search(s)
                if m and int(m[1]) == rnd:
                    d[key] = True
            m = L_IN.search(s)
            if m and int(m[1]) == rnd:
                d['in'] = (int(m[2]), m[3])
                d['held'] = float(m[4]) if m[4] else 0.0
                d['raises'] = int(m[5]) if m[5] else 0
            m = L_SAME.search(s)
            if m and int(m[1]) == rnd:
                d['same'] = (m[2].strip(), m[3].strip(), m[4])
            m = L_ACK.search(s)
            if m and int(m[1]) == rnd:
                d['ack'] = (m[2].startswith('every'), int(m[3]), float(m[4]), m[5].strip())
            m = L_AHASH.search(s)
            if m and int(m[1]) == rnd:
                d['ahash'] += 1
            m = L_F1SAME.search(s) or L_F1MISS.search(s)
            if m and int(m[1]) == rnd:
                d['f1'] = 'same' if 'same list' in s else 'MISMATCH'
        x = RS.gw(w)
        try:
            d['key'] = x.d(x.base + CUTAUTH_BOX)
            rb = x.rd(x.base + CUTAUTH_BOX + 8, 16) or b''
            d['ranks'] = {i: rb[i] for i in range(1, min(len(rb), 16)) if rb[i]}
        except Exception as ex:                      # a game gone from the match: report, judge without it
            d['key'], d['ranks'] = None, 'unreadable (%s)' % ex
        d['step'] = RS.step_round(w)
        info[w] = d
        if d['role'] == 'authority':
            auth.append(w)
    a = auth[0] if auth else None
    vals = []
    for w in games:
        d = info[w]
        lag = (d['f1t'] - info[a]['f1t']) if a and d['f1t'] is not None and info[a]['f1t'] is not None else None
        d['lag'] = lag
        vals.append('%s(no %s, %s) step %s | wait %s in %s held %s s x%s | %s | ack %s | early %s | F1 %s | box key %s '
                    'ranks %s | end lag %s s' % (
                        w, nos[w], d['role'] or '?', d['step'], d['wait'], d['in'], d['held'], d['raises'],
                        'cut here %s / authority %s: %s' % d['same'] if d['same'] else 'no cut-here line',
                        d['ack'], d['early'], d['f1'], '%#x' % d['key'] if d['key'] is not None else '?', d['ranks'],
                        lag))
    bad = []
    if any(info[w]['missing'] for w in games):
        bad.append('CUTAUTH group missing on %s' % ''.join(w for w in games if info[w]['missing']))
    if len(auth) != 1:
        bad.append('authorities by F1 line: %s (want exactly one)' % (auth or 'none'))
    if a:
        da = info[a]
        if not da['ack']:
            bad.append('authority %s: no V400-1 answer line for round %d' % (a, rnd))
        elif not da['ack'][0]:
            bad.append('authority %s: not every listed player answered in 10 s (%s)' % (a, da['ack']))
        if da['ahash']:
            bad.append('authority %s: %d answer(s) with another hash' % (a, da['ahash']))
        if da['in'] or da['wait']:
            bad.append('authority %s filled / held its own mailbox' % a)
        if da['key'] not in (0, None):
            bad.append('authority %s mailbox key %#x (want 0)' % (a, da['key']))
    guests = [w for w in games if w != a]
    sets = set()
    for w in guests:
        d = info[w]
        if d['timeout']:
            bad.append('%s: "no list from the authority in 10 s" (cut by its own ranks)' % w)
        if not d['in']:
            bad.append('%s: no "list is in the mailbox" line' % w)
        if not d['same']:
            bad.append('%s: no "cut here / by the authority" line' % w)
        else:
            sets.add(d['same'][0])
            if d['same'][2] != 'same':
                bad.append('%s: cut here %s, by the authority %s: DIFFERENT' % (w, d['same'][0], d['same'][1]))
        if d['held'] is not None and d['held'] > hold_max:
            bad.append('%s: phase end held %.1f s (> %.1f)' % (w, d['held'], hold_max))
        if d['lag'] is not None and d['lag'] > hold_max + 1.0:
            bad.append('%s: its cut came %d s after the authority\'s (> %.1f + 1 s log resolution)' % (
                w, d['lag'], hold_max))
        if d['key'] not in (0, None, CUTAUTH_KEY | rnd):
            bad.append('%s mailbox key %#x (want 0 after the round change, or %#x)' % (w, d['key'], CUTAUTH_KEY | rnd))
    if len(sets) > 1:
        bad.append('guests cut different players: %s' % sorted(sets))
    held = [info[w]['held'] for w in guests if info[w]['held'] is not None]
    sends = info[a]['ack'][1] if a and info[a]['ack'] else None
    summ = 'round %d: authority %s, cut %s on every guest, longest hold %s s, list sends %s%s' % (
        rnd, a, next(iter(sets)) if len(sets) == 1 else sorted(sets), max(held) if held else '-', sends,
        ' (Bloodbound: team ranks)' if teams else '')
    print('AUTH %s %s | %s' % ('FAIL' if bad else 'PASS', '; '.join(bad)[:600] if bad else summ, ' ;; '.join(vals)))


def finalstate(games, victim):
    """After VICTIM's last death in a 3+ player Standard final (spectate_notes 9): VICTIM at its result screen
    (step 29..36), every other finalist still in step 6 of round 4, the others logged it out, no 'review3 F1 bound'
    run-down in this match."""
    import regress_small as RS
    nos = {w: RS.local_no(w) for w in games}
    steps = {w: RS.step_round(w) for w in games}
    told, bound = {}, {}
    for w in games:
        lines = match_lines(w)
        told[w] = sorted({int(m[1]) for _, s in lines for m in [L_OUT.search(s)] if m})
        bound[w] = sum(1 for _, s in lines if L_BOUND.search(s))
    vals = '; '.join('%s(no %s) step %s out-lines %s bound %d' % (w, nos[w], steps[w], told[w], bound[w])
                     for w in games)
    bad = []
    vs = steps.get(victim)
    if not (vs and 29 <= (vs[0] or 0) <= 36):
        bad.append('%s (eliminated) at step %s, not at its result screen (29..36)' % (victim, vs))
    for w in games:
        if w == victim:
            continue
        if steps[w] != (6, 4):
            bad.append('%s at %s, not playing the final (6, 4)' % (w, steps[w]))
        if nos[victim] not in told[w]:
            bad.append('%s has no "player %s is out of the final" line' % (w, nos[victim]))
        if bound[w]:
            bad.append('%s ran the final down early ("review3 F1 bound" x%d)' % (w, bound[w]))
    print('OUT %s %s | %s' % ('FAIL' if bad else 'PASS', '; '.join(bad) if bad else
                              '%s (player %s) at its result screen, %s play on' % (
                                  victim, nos[victim], ''.join(w for w in games if w != victim)), vals))


def finalon(games):
    """The final still runs: every game of GAMES in step 6 of round 4 (Bloodbound, a pair member down)."""
    import regress_small as RS
    steps = {w: RS.step_round(w) for w in games}
    off = [w for w in games if steps[w] != (6, 4)]
    print('ON %s %s | %s' % ('FAIL' if off else 'PASS', ('%s left the final early' % ''.join(off)) if off else
                             'the final goes on on %s' % games, steps))


def netsim(games):
    """The simulator arrived where it was asked for: twin4's line and the emulator log's start line per game."""
    try:
        tw = (TWIN / 'twin_console.log').read_text(encoding='utf-8', errors='replace')
    except OSError:
        tw = ''
    bad, vals = [], []
    for w in games:
        given = re.search(r'^twin4: game %s LICHII_NET_SIM=(\S+)' % w, tw, re.M)
        start = errors = stalls = 0
        try:
            for line in open(eden_log(w), encoding='utf-8', errors='replace'):
                if 'NET SIM (TEST ONLY)' in line:
                    start += 1
                elif 'NET SIM: stall #' in line:
                    stalls += 1
                elif 'NET SIM: LICHII_NET_SIM=' in line and 'not understood' in line:
                    errors += 1
        except OSError:
            pass
        vals.append('%s given %s, start lines %d, stalls %d, errors %d' % (w, given[1] if given else '-', start,
                                                                           stalls, errors))
        if not given or not start or errors:
            bad.append(w)
    print('NETSIM %s %s | %s' % ('FAIL' if bad else 'PASS', ('not active on %s' % ''.join(bad)) if bad else
                                 'active on %s' % games, '; '.join(vals)))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 1
    k = a[0]
    if k == 'commit':
        commit(float(a[1]))
    elif k == 'prereq':
        prereq()
    elif k == 'vram':
        vram(a[1])
    elif k == 'lazy':
        lazy(a[1])
    elif k == 'nos':
        nos(a[1])
    elif k == 'cuts' and len(a) >= 5:
        cuts(int(a[1]), int(a[2]), int(a[3]), a[4], 'teams' in a)
    elif k == 'final':
        final(a[1], *a[2:])
    elif k == 'cutlog' and len(a) >= 3:
        hm = next((float(x.split('=', 1)[1]) for x in a[3:] if x.startswith('hold_max=')), 1.5)
        cutlog(int(a[1]), a[2], hm, 'teams' in a)
    elif k == 'finalstate' and len(a) >= 3:
        finalstate(a[1], a[2])
    elif k == 'finalon':
        finalon(a[1])
    elif k == 'netsim':
        netsim(a[1])
    elif k == 'bbfinal':
        bbfinal(a[1])
    elif k == 'pairs':
        pairs(a[1])
    elif k == 'kill2' and len(a) >= 3:
        kill2(a[1], a[2])
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
