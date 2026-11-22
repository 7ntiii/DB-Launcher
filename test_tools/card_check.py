r"""card_check.py: grade the test card rows (handoffs/12-TEST_2026-11-18.md) from one match's logs (read only).

Usage (workspace root):
    python diag/twin/card_check.py M LOG [LOG ...] [--build 3.9.16] [--rows 1,3,9] [--cutcheck] [-v]
    python diag/twin/card_check.py --selftest

M is the card's match number: 1 = match 1 (rows 1-6, v3.9.16), 2 = match 2 (rows 1, 7-12; on v3.9.20 also the
must-not lines), and a match with 4+ players (M=3 on the card) = rows 13-18 + the must-not list, with cutcheck.
LOG is [LABEL:]path[#K]. The path can be:
  - a run_night.sh `logs` folder (diag/net/user3p_<date>_m<M>/): games A and B (A_/B_dusk_lan.txt with
    A_/B_eden_log.txt), night_fps_m*.log, and a build.txt if present. diag/net/blink_site_night_m<M>.txt and
    diag/net/fx_probe_night_m<M>.txt are read too when they exist;
  - a DuskLogs_... folder or zip (Collect logs.cmd): one game per gameN folder, the build from SUMMARY.txt;
  - a game's log folder (dusk_lan.txt, dusk_lan.N.txt, eden_log.txt, eden_log.txt.old.txt);
  - one dusk_lan file, or an fx_probe / blink_site / fps_watch / eden_log output (told apart by its lines; an
    eden_log is attached to the game with the same LABEL).
Each game uses the last match of its logs ("map: new match"); #K picks the K-th (1 = first, -1 = last).
The build: --build, else SUMMARY.txt / build.txt, else a lower bound from version-only log lines. (The eden_log
version string is the emulator base, dc1b3203a5, on every package: it says nothing.)
Output: one line per row: row, PASS / FAIL / NOT SEEN / ASK (the user judges it on screen), and the deciding log
line as `label hh:mm:ss text`. -v adds the other lines found. Nothing is written except a temp copy of each
game's match for cutcheck (deleted after)."""
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parent.parent
TIME = re.compile(r'^(\d\d):(\d\d):(\d\d) (.*)$')
EDEN_T = re.compile(r'^\[\s*(\d+\.\d+)\]')
SUMMARY = re.compile(r'package v([\d.]+) \(commit (\w+)\)')
def vkey(v):
    return tuple(int(x) for x in v.split('.') if x.isdigit())


FINGERPRINT = [  # newest first: a line only that build (or later) can log
    ('3.9.20', re.compile(r'v4\.33|v4\.34|stall guard is off \(\d')),
    ('3.9.18', re.compile(r'FIREKEEP')),
    ('3.9.17', re.compile(r'\(CUTSCENE_VOTE\)|\(POWER_CHOICE\)|v429 stall guard')),
    ('3.9.16', re.compile(r'is emptied \(no list|LISTBUF let go')),
    ('3.9.15', re.compile(r'area icons: round|map trend: round|\(CLOCKADD')),
]
CRASH_LR = 0x3FFA0DC


class Line:
    __slots__ = ('t', 'sec', 'text', 'src')

    def __init__(self, t, sec, text, src):
        self.t, self.sec, self.text, self.src = t, sec, text, src


class Game:
    def __init__(self, label):
        self.label = label
        self.files = []        # [(name, [Line], eden (name, text) or None)] oldest first
        self.build = None
        self.build_src = ''
        self.pick = -1
        self.no = None
        self.players = None
        self.match = []        # the chosen match's lines
        self.base = None       # main base of the file holding the match
        self.eden = None       # (name, text) paired with that file
        self.t0 = None         # first line of that file (assist start), seconds
        self.chosen = None     # the file that holds the match
        self.note = ''


def parse_dusk(text, src):
    out, day, last = [], 0, None
    for raw in text.splitlines():
        m = TIME.match(raw)
        if not m:
            continue
        h, mi, s, rest = m.groups()
        sec = int(h) * 3600 + int(mi) * 60 + int(s)
        if last is not None and sec + 43200 < last:
            day += 86400
        last = sec
        out.append(Line(f'{h}:{mi}:{s}', sec + day, rest, src))
    return out


def kind_of(text):
    head = text[:20000]
    if re.search(r'^\s*\d+\.\d+ [A-Z] p\d+: ', head, re.M):
        return 'fx'
    if re.search(r'SpEffect \d+ w5=|site main\+0x', head):
        return 'blink'
    if re.search(r'^\d\d:\d\d:\d\d (storm_watch|[A-Z]: storm (step|entries|summary))', head, re.M):
        return 'storm'
    if re.search(r'^\d\d:\d\d:\d\d (fps_watch|[A-Z]: (BLACK\?|drawing again|no status))', head, re.M):
        return 'fps'
    if EDEN_T.search(head) and 'Lichii Version' in head or re.search(r'^\[\s*\d+\.\d+\] \w', head, re.M):
        return 'eden'
    return 'dusk'


def rot_key(name):
    m = re.search(r'dusk_lan\.(\d+)\.txt$', name)
    return -int(m[1]) if m else 0          # dusk_lan.5 (oldest) first, dusk_lan.txt last


class Logs:
    def __init__(self):
        self.games = []
        self.fx, self.blink, self.fps, self.storm = [], [], [], []
        self.folders = []

    def game(self, label):
        for g in self.games:
            if g.label == label:
                return g
        g = Game(label)
        self.games.append(g)
        return g

    def add_game_files(self, label, entries, build=None, build_src=''):
        """entries: {name: text} of one game's folder (dusk_lan*.txt, eden_log*)."""
        g = self.game(label)
        dusk = sorted((n for n in entries if re.search(r'dusk_lan(\.\d+)?\.txt$', n)), key=rot_key)
        if not dusk and len(entries) == 1:
            dusk = list(entries)          # one file given by path, any name
        for n in dusk:
            eden = None
            if n.endswith('dusk_lan.txt'):
                e = n[:-len('dusk_lan.txt')] + 'eden_log.txt'
                eden = (e, entries[e]) if e in entries else None
            elif n.endswith('dusk_lan.1.txt'):
                e = n[:-len('dusk_lan.1.txt')] + 'eden_log.txt.old.txt'
                eden = (e, entries[e]) if e in entries else None
            g.files.append((n, parse_dusk(entries[n], n), eden))
        if build:
            g.build, g.build_src = build, build_src
        return g

    def add(self, spec):
        label, path, pick = None, spec, -1
        m = re.match(r'^([^:\\/]+):(?![\\/])(.*)$', spec)
        if m and not Path(spec).exists():
            label, path = m[1], m[2]
        m = re.match(r'^(.*)#(-?\d+)$', path)
        if m and not Path(path).exists():
            path, pick = m[1], int(m[2])
        p = Path(path)
        if not p.exists():
            sys.exit(f'card_check: {path} not found')
        before = len(self.games)
        if p.is_dir():
            self.add_dir(label, p)
        elif zipfile.is_zipfile(p):
            self.add_zip(label, p)
        else:
            text = p.read_text(encoding='utf-8', errors='replace')
            kind = kind_of(text)
            lab = label or p.stem
            if kind == 'fx':
                self.fx.append((lab, str(p), text.splitlines()))
            elif kind == 'blink':
                self.blink.append((lab, str(p), text.splitlines()))
            elif kind == 'fps':
                self.fps.append((lab, str(p), text.splitlines()))
            elif kind == 'storm':
                self.storm.append((lab, str(p), text.splitlines()))
            elif kind == 'eden':
                g = self.game(lab)
                if g.files:
                    n, lines, _ = g.files[-1]
                    g.files[-1] = (n, lines, (str(p), text))
                else:
                    g.note = 'eden_log given before its dusk_lan'
            else:
                self.add_game_files(lab, {str(p): text})
        for g in self.games[before:]:
            g.pick = pick

    def add_dir(self, label, p):
        names = {f.name for f in p.iterdir()}
        summary = p / 'SUMMARY.txt'
        build, src = None, ''
        if summary.exists():
            m = SUMMARY.search(summary.read_text(encoding='utf-8', errors='replace'))
            if m:
                build, src = m[1], f'SUMMARY.txt (commit {m[2]})'
        if (p / 'build.txt').exists():
            build, src = (p / 'build.txt').read_text().strip().lstrip('v'), 'build.txt'
        games = sorted(f for f in p.iterdir() if f.is_dir() and re.match(r'game\d+$', f.name))
        if games:      # DuskLogs folder
            for gd in games:
                lab = (label or p.name[:20]) + ('' if len(games) == 1 else '-' + gd.name)
                self.add_game_files(lab, {str(f): f.read_text(encoding='utf-8', errors='replace')
                                          for f in gd.iterdir() if f.is_file()}, build, src)
            return
        prefixed = sorted(n for n in names if re.match(r'.+_dusk_lan\.txt$', n))
        if prefixed:   # run_night.sh logs folder (A_/B_) or older (P1_/P2_)
            self.folders.append(p)
            for n in prefixed:
                pre = n[:-len('_dusk_lan.txt')]
                entries = {'dusk_lan.txt': (p / n).read_text(encoding='utf-8', errors='replace')}
                if f'{pre}_eden_log.txt' in names:
                    entries['eden_log.txt'] = (p / f'{pre}_eden_log.txt').read_text(encoding='utf-8',
                                                                                      errors='replace')
                self.add_game_files(pre if not label else f'{label}-{pre}', entries, build, src)
            for n in sorted(names):
                f = p / n
                if n.endswith('_dusk_lan.txt') or n.endswith('_eden_log.txt') or not n.endswith(('.txt', '.log')):
                    continue
                text = f.read_text(encoding='utf-8', errors='replace')
                kind = kind_of(text)
                if kind in ('fx', 'blink', 'fps', 'storm'):
                    getattr(self, kind).append((n, str(f), text.splitlines()))
            return
        entries = {str(f): f.read_text(encoding='utf-8', errors='replace')
                   for f in p.iterdir() if f.is_file() and (f.name.startswith('dusk_lan') or
                                                            f.name.startswith('eden_log'))}
        self.add_game_files(label or p.name, entries, build, src)

    def add_zip(self, label, p):
        z = zipfile.ZipFile(p)
        names = z.namelist()
        build, src = None, ''
        for n in names:
            if n.endswith('SUMMARY.txt'):
                m = SUMMARY.search(z.read(n).decode('utf-8', 'replace'))
                if m:
                    build, src = m[1], f'SUMMARY.txt (commit {m[2]})'
        dirs =sorted({re.search(r'(game\d+)/', n)[1] for n in names if re.search(r'(game\d+)/', n)}) or ['']
        for d in dirs:
            entries = {}
            for n in names:
                if (not d or f'{d}/' in n) and re.search(r'(dusk_lan(\.\d+)?\.txt|eden_log\.txt(\.old\.txt)?)$', n):
                    entries[n] = z.read(n).decode('utf-8', 'replace')
            lab = (label or p.stem[:20]) + ('' if len(dirs) == 1 else '-' + d)
            self.add_game_files(lab, entries, build, src)


def choose(g):
    """The chosen match of a game, its file's main base and eden log."""
    matches = []
    for name, lines, eden in g.files:
        starts = [i for i, ln in enumerate(lines) if ln.text.startswith('map: new match')]
        for k, i in enumerate(starts):
            end = starts[k + 1] if k + 1 < len(starts) else len(lines)
            matches.append((name, lines, eden, i, end))
    if not matches:
        if not g.files:
            return
        name, lines, eden = g.files[-1]
        matches = [(name, lines, eden, 0, len(lines))]
        g.note = (g.note + '; ' if g.note else '') + 'no "map: new match" line: the whole file is used'
    if g.pick == -1:   # the last real match: a "new match" line just before leaving is no match
        real = [mt for mt in matches if mt[1][mt[4] - 1].sec - mt[1][mt[3]].sec >= 120]
        matches = real or matches
    try:
        name, lines, eden, i, end = matches[g.pick if g.pick < 0 else g.pick - 1]
    except IndexError:
        sys.exit(f'card_check: {g.label} has {len(matches)} match(es), #{g.pick} asked')
    g.match = lines[i:end]
    g.eden = eden
    g.chosen = name
    if g.build_src.startswith('SUMMARY') and not name.endswith('dusk_lan.txt'):
        g.build, g.build_src = None, ''   # SUMMARY names the package of the newest run only
        g.note = (g.note + '; ' if g.note else '') + 'an older run: its build is not the SUMMARY one'
    g.t0 = lines[0].sec if lines else 0
    for ln in lines[:end]:
        m = re.search(r'player no is now (\d+)', ln.text) or re.search(r'player no (\d+) team \d+', ln.text)
        if m:
            g.no = int(m[1])
        m = re.search(r'\((\d+) players\)', ln.text)
        if m:
            g.players = int(m[1])
        m = re.search(r'main base (0x[0-9a-f]+)', ln.text)
        if m:
            g.base = int(m[1], 16)
    if not g.build:
        text = '\n'.join(ln.text for ln in lines)   # only the file that holds the match
        for ver, rx in FINGERPRINT:
            if rx.search(text):
                g.build, g.build_src = ver, 'at least (version-only log lines)'
                break


# ---- helpers ----------------------------------------------------------------------------------------------

def find(g, rx, lines=None):
    rx = re.compile(rx) if isinstance(rx, str) else rx
    return [ln for ln in (g.match if lines is None else lines) if rx.search(ln.text)]


def show(g, ln, width=170):
    return f'{g.label} {ln.t} {ln.text[:width]}'


def round4(g):
    """Lines of the final (from the first line naming round 4)."""
    for i, ln in enumerate(g.match):
        if re.search(r'\bround 4\b|is in the final with us', ln.text):
            return g.match[i:]
    return []


def hms(sec):
    sec = int(sec) % 86400
    return f'{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}'


def crashes(g):
    """eden Backtrace blocks inside the match: [(approx hh:mm:ss, LR offset or None, text)]."""
    if not g.eden or not g.match:
        return []
    out = []
    lines = g.eden[1].splitlines()
    for i, raw in enumerate(lines):
        if 'Backtrace @ PC=' not in raw:
            continue
        m = EDEN_T.search(raw)
        t = float(m[1]) if m else 0.0
        wall = g.t0 + t
        if wall < g.match[0].sec - 60 or wall > g.match[-1].sec + 600:
            continue
        lr = None
        for nxt in lines[i + 1:i + 12]:
            mm = re.search(r'R30=([0-9A-F]{16})', nxt)
            if mm:
                lr = int(mm[1], 16)
                break
        off = lr - g.base if lr is not None and g.base else None
        pc = raw.split('Backtrace @ ')[1][:22]
        out.append((hms(wall), off, f'eden +{t:.1f} s Backtrace @ {pc}, LR = '
                    + (f'main+0x{off:X}' if off is not None and 0 <= off < 0x10000000 else f'0x{lr:X}' if lr else '?')))
    return out


def finalists_and_winner(g):
    fin = round4(g)
    if not fin:
        return set(), None
    nos = {int(m[1]) for ln in fin for m in [re.search(r'final: player (\d+) is in the final with us', ln.text)] if m}
    if g.no:
        nos.add(g.no)
    out = set()
    for ln in fin:
        m = re.search(r'final: player (\d+) is out of the final for good.*\(step 6,', ln.text)
        if m:
            out.add(int(m[1]))
        m = re.search(r'final: player (\d+) is heard again in UpdatePhase; its silence mark is dropped', ln.text)
        if m:
            out.discard(int(m[1]))
        m = re.search(r'final: our player \(no (\d+)\) is out', ln.text)
        if m:
            out.add(int(m[1]))
    left = nos - out
    return nos, (next(iter(left)) if len(left) == 1 else None)


def cut_set(g):
    cut = set()
    for ln in g.match:
        m = re.search(r'H1: player (\d+) is cut', ln.text) or re.search(r'H1: our player \(no (\d+)\) is cut', ln.text)
        if m:
            cut.add(int(m[1]))
        m = re.search(r'H1: player (\d+) is in a match step again', ln.text) or \
            re.search(r'H1: our player \(no (\d+)\) is no longer', ln.text)
        if m:
            cut.discard(int(m[1]))
    return cut


def extra_lines(logs, kind, m_no, names):
    out = list(getattr(logs, kind))
    for n in names:
        f = WS / 'diag' / 'net' / n.format(m=m_no)
        if f.exists() and logs.folders and not any(src == str(f) for _, src, _ in out):
            out.append((f.name, str(f), f.read_text(encoding='utf-8', errors='replace').splitlines()))
    return out


# ---- rows -------------------------------------------------------------------------------------------------

def row1(ctx):
    games, logs = ctx['games'], ctx['logs']
    guests = [g for g in games if g.no != 1]
    for g in games:
        for when, off, text in crashes(g):
            sig = ' (the final-load crash signature)' if off == CRASH_LR else ' (another crash)'
            return 'FAIL', f'{g.label} ~{when} {text}{sig}'
    for lab, src, lines in ctx['fps']:
        for raw in lines:
            if 'BLACK?' in raw:
                return 'FAIL', f'{lab} {raw.strip()[:150]}'
    missing = [g.label for g in guests if not find(g, r'is in the final with us')]
    if not guests or len(missing) == len(guests):
        return 'NOT SEEN', 'no guest reached the final (no "final: player N is in the final with us")'
    if missing:
        return 'FAIL', f'{", ".join(missing)}: no "is in the final with us" while another guest has one (hang or crash)'
    notes = []
    no_eden = [g.label for g in guests if not g.eden]
    if no_eden:
        notes.append(f'no eden_log for {", ".join(no_eden)}: crash not checked there')
    if not ctx['fps']:
        notes.append('no fps_watch log: BLACK? not checked')
    ev = None
    for g in guests:
        e = find(g, r'area icons: round 4: the list handed in round \d+ is emptied')
        if e:
            ev = show(g, e[0])
            break
        elif not find(g, r'area icons: round \d+ \d+ entries handed'):
            pass
    if ev is None:
        g = guests[0]
        ev = show(g, find(g, r'is in the final with us')[0])
        notes.append('no "is emptied" line (no list was handed to a guest in round 3)')
    return 'PASS', ev + (f'  [{"; ".join(notes)}]' if notes else '') + '  (the user confirms a picture)'


def row2(ctx):
    guests = [g for g in ctx['games'] if g.no != 1]
    ev = [(g, find(g, r"area icons: round \d+ \d+ entries handed to the game from player \d+'s list")) for g in guests]
    got = [(g, e) for g, e in ev if e]
    if not got:
        return 'NOT SEEN', 'no guest logged "area icons: round N n entries handed to the game"'
    g, e = got[0]
    return 'ASK', show(g, e[-1]) + '  (log: icons handed; the user checks the icons on the laptop map)'


def row3(ctx):
    fx = ctx['fx']
    games = ctx['games']
    lag = []
    for g in games:
        if g.no == 1:
            continue
        for ln in find(g, r'peer player 1: its moves show (\d+\.\d+) s late', round4(g)):
            if float(re.search(r'show (\d+\.\d+)', ln.text)[1]) >= 0.65:
                lag.append(show(g, ln))
    stacked, dies, gone = [], None, None
    for lab, src, lines in fx:
        for raw in lines:
            m = re.match(r'^\s*(\d+\.\d+) B p1: (.*)$', raw)
            if 'STACKED' in raw:
                stacked.append(f'{lab} {raw.strip()[:150]}')
            if m and 'DIES' in m[2] and dies is None:
                dies = (float(m[1]), f'{lab} {raw.strip()[:150]}')
            if m and m[2].startswith('GONE') and dies is not None and gone is None:
                gone = (float(m[1]), f'{lab} {raw.strip()[:150]}')
    if stacked:
        return 'FAIL', stacked[0] + '  (fire stacks: plan B)'
    if lag:
        return 'FAIL', lag[0] + '  (the lag line: plan B)'
    if dies and gone:
        d = gone[0] - dies[0]
        if d < 4:
            return 'FAIL', f'{gone[1]}  (GONE {d:.1f} s after DIES: finalhold missing, check the build)'
        return 'ASK', f'{gone[1]}  (GONE {d:.1f} s after DIES, no STACKED, no lag line: plan A holds; the user confirms one death effect, no FPS drop)'
    hand = []
    for g in games:
        hand += [show(g, ln) for ln in find(g, r'final: player 1 is handed to the elimination block in 6 s')]
    if hand:
        return 'ASK', hand[0] + '  (no fx_probe DIES/GONE output: the user judges the fire)'
    return 'NOT SEEN', 'no fx_probe output and no hand-over of player 1' + ('' if fx else ' (give fx:<file>)')


def ask(what):
    return lambda ctx: ('ASK', what)


def row6(ctx):
    seen = []
    for lab, src, lines in ctx['blink']:
        for raw in lines:
            m = re.search(r'SpEffect (\d+) w5=(\d+) chr=\S+ lr=main\+(0x[0-9a-f]+)', raw)
            if m and 1401000 <= int(m[1]) < 1401100:
                seen.append((int(m[2]), int(m[3], 16), f'{lab} {raw.strip()[:150]}'))
    if not seen:
        return 'NOT SEEN', 'no SpEffect 14010xx line in a blink_site output' + ('' if ctx['blink'] else ' (none given)')
    good = [s for s in seen if s[1] == 0x194B8E0 and s[0] == 1]
    bad = [s for s in seen if s[1] != 0x194B8E0]
    if bad:
        return 'FAIL', bad[0][2] + '  (another site)'
    if good:
        return 'PASS', good[0][2]
    return 'FAIL', seen[0][2] + '  (site right, w5 not 1)'


def row9(ctx):
    found, fails, ends = None, [], {}
    for g in ctx['games']:
        tally = {}
        for ln in find(g, r'cutscene vote: cutscene (\S+): (\d+) / (\d+) players voted to skip'):
            m = re.search(r'cutscene (\S+): (\d+) / (\d+) players', ln.text)
            if int(m[3]) >= 2 and int(m[2]) >= int(m[3]):
                tally.setdefault(m[1], ln)
        for cid, ln in tally.items():
            sk = [x for x in find(g, rf'cutscene vote: all \d+ players voted; cutscene {re.escape(cid)} skipped here')]
            if sk:
                found = found or show(g, sk[0])
                ends.setdefault(cid, []).append((g, sk[0]))
            else:
                fails.append(show(g, ln) + '  (all voted, no "skipped here" line)')
    if fails:
        return 'FAIL', fails[0]
    if not found:
        return 'NOT SEEN', 'no shared cutscene reached n / n votes'
    spread = ''
    for cid, lst in ends.items():
        rig = [ln.sec for g, ln in lst if g.label.startswith(('A', 'B'))]
        if len(rig) >= 2:
            spread = f'; A/B ended {max(rig) - min(rig)} s apart'
    return 'PASS', found + f'  (on {max(len(v) for v in ends.values())} game(s){spread}; the user confirms all ended)'


def row10(ctx):
    games = ctx['games']
    for g in games:
        e = find(g, r'award came first, this choice cannot count')
        if e:
            return 'FAIL', show(g, e[0])
    chosen = [(g, ln) for g in games for ln in find(g, r'power choice: chosen Power 0x[0-9a-f]+ stored')]
    if chosen:
        g, ln = chosen[0]
        more = ', '.join(f'{x.label}: {re.search(r"chosen Power (0x[0-9a-f]+)", y.text)[1]}'
                         f' ({"same" if "the same entry" in y.text else "another"} entry)' for x, y in chosen)
        return 'ASK', show(g, ln) + f'  [{more}]  (the user confirms each got the picked Power)'
    held = [(g, ln) for g in games for ln in find(g, r'power choice: (Power dialog opened|award of Power)')]
    if held:
        return 'NOT SEEN', show(*held[0]) + '  (dialog / held award, but no choice stored)'
    return 'NOT SEEN', 'no Power choice lines'


def row11(ctx):
    games = ctx['games']
    hit = [(g, ln) for g in games for ln in find(g, r'this game is the one cut off')]
    if not hit:
        return 'NOT SEEN', 'no game froze ("this game is the one cut off" not logged)'
    wins = {g.label: finalists_and_winner(g)[1] for g in games}
    known = {w for w in wins.values() if w}
    if len(known) > 1:
        return 'FAIL', show(*hit[0]) + f'  (winners differ: {wins})'
    return 'PASS', show(*hit[0]) + f'  (winner per game: {wins})'


def row12(ctx):
    games, build = ctx['games'], ctx['build']
    if build and vkey(build) < vkey('3.9.18') and 'at least' not in ctx['build_src']:
        return 'NOT SEEN', f'n/a on v{build} (FIREKEEP is in v3.9.18 / v3.9.20)'
    for g in games:
        for ln in find(g, r'FIREKEEP did not skip|FIREKEEP not in this build'):
            return 'FAIL', show(g, ln)
    for lab, src, lines in ctx['fx']:
        for raw in lines:
            if re.match(r'^\s*\d+\.\d+ B p1: GONE', raw):
                return 'FAIL', f'{lab} {raw.strip()[:150]}  (the copy was taken out)'
    ok = [(g, ln) for g in games for ln in
          find(g, r"the game took player 1's elimination .*its copy stays here as a dead body \(FIREKEEP skip \d+, player 1\)")]
    if ok:
        return 'ASK', show(*ok[0]) + f'  (on {len(ok)} game(s); the user confirms no fire, final ends normally)'
    return 'NOT SEEN', 'no "took player 1\'s elimination" line (host A not out in the final?)'


def row13(ctx):
    games, cc = ctx['games'], ctx['cutcheck']
    if len(games) < 4:
        return 'NOT SEEN', f'{len(games)} game log(s) given; row 13 needs all 4'
    bad = []
    for g in games:
        if not round4(g) and not find(g, r'H1: our player \(no \d+\) is cut'):
            bad.append(f'{g.label} (last line {g.match[-1].t if g.match else "?"})')
    if cc is None:
        return 'NOT SEEN', 'cutcheck did not run'
    if bad:
        return 'FAIL', 'no final and no own cut on ' + ', '.join(bad)
    if cc['flags'] != 0 or cc['bang']:
        return 'FAIL', f'cutcheck: {cc["flags"]} disagreement(s) flagged; first: {(cc["bang"] or ["?"])[0].strip()[:150]}'
    wins = {g.label: finalists_and_winner(g)[1] for g in games}
    if len({w for w in wins.values() if w}) > 1:
        return 'FAIL', f'winners differ: {wins}'
    note = '' if any(wins.values()) else '  (no winner read from the logs: the user confirms the result screens)'
    return 'PASS', f'cutcheck: 0 disagreement(s) flagged; winner per game {wins}{note}'


def row14(ctx):
    games, cc = ctx['games'], ctx['cutcheck']
    for g in games:
        for ln in find(g, r'!!! cut \(CUTAUTH\): round 3: no list from the authority'):
            return 'FAIL', show(g, ln)
        per = {}
        for ln in find(g, r'authority: taken after \d+ s without a lower-numbered player'):
            r = [x for x in g.match if x.sec <= ln.sec and re.search(r'\bround (\d)\b', x.text)]
            rd = re.search(r'\bround (\d)\b', r[-1].text)[1] if r else '?'
            per.setdefault(rd, []).append(ln)
        for rd, lst in per.items():
            if len(lst) > 1:
                return 'FAIL', show(g, lst[1]) + f'  (second "authority: taken" in round {rd})'
    if cc and any('took different players as cut' in b for b in cc['bang']):
        return 'FAIL', 'cutcheck: !! the games took different players as cut'
    auth = [(g, ln) for g in games for ln in
            find(g, r'cut check \(F1\): round 3 step \d+: .*we are the authority: sent to the others')]
    mail = [(g, ln) for g in games for ln in
            find(g, r"cut \(CUTAUTH\): round 3: the authority's list \(player \d+, hash [0-9a-f]+\) is in the mailbox")]
    sets = {g.label: tuple(sorted(cut_set(g))) for g in games}
    if not auth:
        return 'NOT SEEN', 'no round-3 F1 authority line'
    cuts = {s for s in sets.values() if s}
    if len(cuts) > 1:
        return 'FAIL', f'cut per game differs: {sets}'
    if not cuts:
        return 'NOT SEEN', show(*auth[0]) + '  (nobody logged an H1 cut)'
    return 'PASS', show(*auth[0]) + f'  ({len(mail)} mailbox line(s); cut per game {sets}' + \
        (f'; cutcheck {cc["taken"]}' if cc and cc['taken'] else '') + ')'


def row15(ctx):
    games = ctx['games']
    w2 = [(g, ln) for g in games for ln in find(g, r'!!! cut \(CUTAUTH, W2\): round 3')]
    if not w2:
        return 'NOT SEEN', 'no W2 line (no leaver at the cut): not judged'
    sets = {s for s in (tuple(sorted(cut_set(g))) for g in games) if s}
    return ('PASS' if len(sets) == 1 else 'FAIL'), show(*w2[0]) + f'  (cut sets {sets})'


def row16(ctx):
    games = ctx['games']
    cut = set().union(*(cut_set(g) for g in games)) if games else set()
    added = [(g, ln) for g in games for ln in find(g, r'final: start slots added for player\(s\) ([\d, ]+) \(\d+ -> \d+ slots\)')]
    for g in games:
        if g.no == 1 or any(x is g for x, _ in added):
            continue
        for ln in find(g, r'start point: player \d+ had none|shares a start point', round4(g)):
            return 'FAIL', show(g, ln)
    for g, ln in added:
        nos = {int(x) for x in re.search(r'player\(s\) ([\d, ]+) \(', ln.text)[1].replace(' ', '').split(',') if x}
        if nos & cut:
            return 'FAIL', show(g, ln) + f'  (cut player {sorted(nos & cut)} got a slot)'
    for g in games:
        for ln in find(g, r'final: start list rebuilt, (\d+) entries'):
            n = int(re.search(r'rebuilt, (\d+) entries', ln.text)[1])
            pts = re.findall(r'at \((-?[\d.]+), (-?[\d.]+)\)', ln.text)
            if n >= 4 or len(set(pts)) < len(pts):
                return 'FAIL', show(g, ln)
    if not added:
        return 'NOT SEEN', 'no "final: start slots added" line'
    g, ln = added[0]
    return 'PASS', show(g, ln) + f'  (cut {sorted(cut) or "none"})'


def row17(ctx):
    games = ctx['games']
    cut = set().union(*(cut_set(g) for g in games)) if games else set()
    if 1 not in cut:
        return 'NOT SEEN', f'player 1 was not cut (cut: {sorted(cut) or "none"})'
    for g in games:
        for ln in find(g, r'final: our player \d+ has no start slot here'):
            return 'FAIL', show(g, ln)
    for g in games:
        t = find(g, r'authority: taken after \d+ s without a lower-numbered player \(every lower-numbered player is cut')
        if t:
            h = [x for x in find(g, r'map: round 4 seen here as the host') if x.sec >= t[0].sec]
            return ('PASS' if h else 'FAIL'), show(g, t[0]) + ('' if h else '  (no "map: round 4 seen here as the host" after it)')
    return 'FAIL', 'player 1 cut, but no game logged "authority: taken ... every lower-numbered player is cut"'


def row18(ctx):
    games = ctx['games']
    hit = [(g, ln) for g in games for ln in find(g, r'v4\.33 majority guard|v4\.34 quorum')]
    if not hit:
        return 'NOT SEEN', 'no link loss in the final (no majority guard / quorum line)'
    wins = {g.label: finalists_and_winner(g)[1] for g in games}
    known = {w for w in wins.values() if w}
    return ('FAIL' if len(known) > 1 else 'PASS'), show(*hit[0]) + f'  (winner per game {wins})'


def must_not(ctx, extra):
    games = ctx['games']
    rows = []
    pats = [('v4.33 majority guard', r'v4\.33 majority guard'), ('v4.34 quorum', r'\(v4\.34 quorum\)')]
    if extra:
        pats += [('v4.34b relay', r'v4\.34b relay'), ('no start slot for cut player(s)', r'no start slot for cut player\(s\)')]
    for name, rx in pats:
        hits = [(g, ln) for g in games for ln in find(g, rx)]
        rows.append((f'not: {name}', 'FAIL' if hits else 'PASS', show(*hits[0]) if hits else 'absent'))
    cut = set().union(*(cut_set(g) for g in games)) if games else set()
    drops = [(g, ln) for g in games for ln in find(g, r'side: type 24 from game 0x[0-9a-f]+ dropped')]
    if not extra:
        rows.append(('not: type 24 dropped', 'PASS' if not drops else 'ASK',
                     'absent' if not drops else show(*drops[0]) + f'  (must be the cut game {sorted(cut)}\'s id)'))
    off = []
    for g in games:
        on = False
        for ln in g.match:
            if re.search(r'\(v429 stall guard\)|\(v4\.33 majority guard\)', ln.text):
                on = True
            elif 'stall guard is off' in ln.text:
                if not on:
                    off.append((g, ln))
                on = False
    rows.append(('not: off w/o on', 'FAIL' if off else 'PASS', show(*off[0]) if off else 'absent'))
    relay = [(g, ln) for g in games for ln in find(g, r'v4\.34b relay')]
    if not extra and relay:
        rows.append(('v434b relay', 'ASK', show(*relay[0]) + '  (note who wins on each screen)'))
    return rows


def row39(ctx):
    """Storm (env 1140, row 39 P baked v3.3; STORM_CAVE + STORM): a re-check whenever it is drawn."""
    drawn = [(g, ln) for g in ctx['games'] for ln in find(g, r'environment event 1140 (drawn here|from player)')]
    summ = {}
    for lab, src, lines in ctx['storm']:
        for raw in lines:
            m = re.search(r'([A-Z]): storm summary: highest step (\d+), entries (\d+), moved (yes|no)', raw)
            if m:
                summ[m[1]] = (int(m[2]), int(m[3]), m[4] == 'yes', raw.strip()[:160])
    if summ:
        steps = [v[0] for v in summ.values()]
        if min(steps) <= 3 < max(steps):
            bad = next(v for v in summ.values() if v[0] <= 3)
            return 'FAIL', bad[3] + '  (no 0xC8 record arrived on this game)'
        if len({v[1] for v in summ.values()}) > 1:
            return 'FAIL', '; '.join(v[3] for v in summ.values()) + '  (entry counts differ)'
        if max(steps) >= 6:
            unmoved = [v for v in summ.values() if not v[2]]
            if unmoved:
                return 'FAIL', unmoved[0][3] + '  (Execute reached, our player not moved)'
            return 'PASS', next(iter(summ.values()))[3] + f'  ({len(summ)} rig game(s) moved; the user confirms the laptop moved)'
    if drawn:
        return 'ASK', (show(*drawn[0]) + '  (storm drawn: the user confirms the warning and the teleport'
                       + ('' if ctx['storm'] else '; no storm_watch output') + ')')
    return 'NOT SEEN', 'no storm (1140) drawn in this match'


def row39l(ctx):
    """Storm late record (storm_teleport_notes 'late'): the stock reader 0xF03EEC keeps a kind-0 0xC8 only at step 3.
    Whenever one game goes 3 -> 4 (the record arrived), every other watched game must go 3 -> 4 within 3 s; one that
    was at another step then dropped the record (and misses that warp)."""
    steps = {}   # game -> [(t, old, new)]
    for lab, src, lines in ctx['storm']:
        for raw in lines:
            m = re.match(r'(\d\d):(\d\d):(\d\d) ([A-Z]): storm step (\d+) -> (\d+)', raw.strip())
            if m:
                t = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
                steps.setdefault(m[4], []).append((t, int(m[5]), int(m[6]), raw.strip()[:140]))
    arrivals = [(g, t, raw) for g, ch in steps.items() for t, a, b, raw in ch if (a, b) == (3, 4)]
    if not arrivals or len(steps) < 2:
        drawn = [(g, ln) for g in ctx['games'] for ln in find(g, r'environment event 1140 (drawn here|from player)')]
        if drawn:
            return 'ASK', show(*drawn[0]) + '  (storm drawn; no storm_watch step lines from two games)'
        return 'NOT SEEN', 'no storm step lines (storm_watch) in this match'
    for g, t, raw in arrivals:
        for h, ch in steps.items():
            if h == g:
                continue
            if any((a, b) == (3, 4) and abs(u - t) <= 3 for u, a, b, _ in ch):
                continue
            before = [b for u, a, b, _ in ch if u <= t]
            at = before[-1] if before else None
            why = ('it was at step %s: the record came outside step 3 and was dropped (late 0xC8)' % at
                   if at not in (None, 3) else 'it was at step 3 but no record arrived')
            return 'FAIL', raw + '  (%s did not follow: %s)' % (h, why)
    return 'PASS', arrivals[0][2] + '  (%d arrival(s), every watched game went 3 -> 4 within 3 s)' % len(arrivals)


def row42g(ctx):
    """Bloodsac Gala (env 1220, row 42-gala P v3.9.1; MapSystem lists kind 9 / 0xA via MAPSIM_HOST + MAP_INBOX):
    a re-check whenever it is drawn. Log part: every guest took the host's round set with the same record count."""
    games = ctx['games']
    drawn = [(g, ln, int(m[1])) for g in games for ln in find(g, r'environment event 1220 (drawn here|from player \d+) \(round \d+\)')
             for m in [re.search(r'\(round (\d+)\)', ln.text)]]
    if not drawn:
        return 'NOT SEEN', 'no Bloodsac Gala (1220) drawn in this match'
    r = drawn[0][2]
    # only the games whose own match has the Gala in this round (a folder may hold other matches' logs)
    games = [g for g in games if any(d[0] is g and d[2] == r for d in drawn)]
    hosts = [(g, ln, int(re.search(r'(\d+) records', ln.text)[1])) for g in games
             for ln in find(g, rf'map: round {r} lists drawn here \(\d+ bytes, (\d+) records\)')]
    guests = [g for g in games if not any(h[0] is g for h in hosts)]

    def secs(t):
        h, m, s = (int(x) for x in t.split(':'))
        return h * 3600 + m * 60 + s
    for g in guests:
        bad = find(g, rf'map: (no lists from the host for round {r}\b|the game took only \d+ of \d+ records of round {r}\b|'
                      rf'round {r} set dropped)')
        if bad:
            return 'FAIL', show(g, bad[0]) + '  (the Gala round set did not land on this game)'
    got = {}
    for g in guests:
        e = find(g, rf'map: round {r} lists from the host are in \((\d+) records')
        if e:
            got[g.label] = (g, e[-1], int(re.search(r'\((\d+) records', e[-1].text)[1]))
    if not got:
        return 'ASK', show(*drawn[0][:2]) + '  (no guest "lists from the host are in" line for this round; the user checks the swarm)'
    paired = 0
    for g, ln, n in got.values():
        # one host: that is it (the laptop's clock differs by hours); several (a folder of several matches): by time
        near = hosts if len(hosts) == 1 else [h for h in hosts if abs(secs(h[1].t) - secs(ln.t)) <= 120]
        if near:
            h = min(near, key=lambda h: abs(secs(h[1].t) - secs(ln.t)))
            paired += 1
            if h[2] != n:
                return 'FAIL', show(g, ln, 90) + '; ' + show(h[0], h[1], 90) + '  (record counts differ)'
    if not hosts and len({v[2] for v in got.values()}) > 1:
        return 'FAIL', '; '.join(show(v[0], v[1], 90) for v in got.values()) + '  (guest record counts differ)'
    g, ln, n = next(iter(got.values()))
    return 'ASK', (show(g, ln) + f'  (Gala round {r}: {len(got)} guest(s) took the {n}-record set'
                   + (f', {paired} matched to the host\'s line' if paired else ', host log absent')
                   + '; the user confirms red sac swarms and breaks one)')


def row8t(ctx):
    """Flame corpses / kin circles 'taken' state (row 8 P v3.6; TakenShare type 12 on top of ACTION_SEND) and the
    regional layout (MapSystem lists, row 42g's path): per round the same shared-object count on every game, and
    every change one game sends is applied on the others."""
    games = ctx['games']

    def secs(t):
        h, m, s = (int(x) for x in t.split(':'))
        return h * 3600 + m * 60 + s
    scans = {}
    for g in games:
        for ln in find(g, r'taken: round (\d+): (\d+) shared objects found \((.*?)\)'):
            m = re.search(r'taken: round (\d+): (\d+) shared objects found \((.*?)\)', ln.text)
            scans.setdefault(int(m[1]), []).append((g, ln, m[2] + ' (' + m[3].strip() + ')'))
    if not scans:
        return 'NOT SEEN', 'no "taken: round N: ... shared objects found" line'

    def offset(g, o):
        """o's clock minus g's, from the round scans (the PCs' clocks differ, e.g. the laptop by ~13 h); the scans
        of one round happen within seconds on every game. None = no common round (other match)."""
        d = []
        for lst in scans.values():
            a = [x for x in lst if x[0] is g]
            b = [x for x in lst if x[0] is o]
            if a and b:
                d.append((secs(b[0][1].t) - secs(a[0][1].t) + 43200) % 86400 - 43200)
        d.sort()
        return d[len(d) // 2] if d and d[-1] - d[0] <= 60 else None
    for r, lst in sorted(scans.items()):
        for g, ln, what in lst:
            bad = [x for x in lst if x[0] is not g and offset(g, x[0]) is not None and x[2] != what]
            if bad:
                return 'FAIL', show(g, ln, 110) + '; ' + show(bad[0][0], bad[0][1], 110) + '  (round layouts differ)'
    sent = [(g, ln, re.search(r'h=([0-9a-f]+) round (\d+)', ln.text)) for g in games
            for ln in find(g, r'taken: \S+ \d+ h=[0-9a-f]+ round \d+: .*sent to the others')]
    sent = [(g, ln, m[1], int(m[2])) for g, ln, m in sent if m]
    missing, matched = [], 0
    for g, ln, h, r in sent:
        for o in games:
            off = offset(g, o) if o is not g else None
            if off is None or not any(x[0] is o for x in scans.get(r, [])):
                continue  # that game has no scan for this round in its chosen match
            hit = [x for x in find(o, rf'taken: \S+ \d+ h={h} (from player \d+ \(round {r}\)|round {r}:)')
                   if abs((secs(x.t) - secs(ln.t) - off + 43200) % 86400 - 43200) <= 30]
            if hit:
                matched += 1
            else:
                missing.append((g, ln, o))
    n_games = max(len(v) for v in scans.values())
    head = f'{len(scans)} round(s), the same layout on all {n_games} game(s) with a scan'
    if missing:
        g, ln, o = missing[0]
        return 'ASK', (show(g, ln, 120) + f'  ({head}; {o.label} logged nothing for this h within 30 s: no change '
                       'there, a dropped packet, or the 200-line cap; the user checks the prompt is gone there)')
    if matched:
        return 'PASS', f'{head}; {matched} sent change(s) seen on the other game(s), e.g. ' + show(*sent[0][:2], 110)
    if sent:
        return 'ASK', f'{head}; {len(sent)} sent change(s), but no other game has a scan for that round (logs of another match)'
    return 'ASK', f'{head}; no taken change sent (nobody lit a large Flame corpse or used a kin circle)'


def row8r(ctx):
    """v3.9.21 option TAKERACE (diag/net/takerace_live.py + assist_v436, layout_notes 2.5): two players press the
    same large Flame corpse or kin circle together; the authority grants the first and refuses the second, so the
    refused game never takes it (no 'gained here' for that h there) and no 'first-taker race' line appears."""
    games = ctx['games']

    def secs(t):
        h, m, s = (int(x) for x in t.split(':'))
        return h * 3600 + m * 60 + s
    if not any(find(g, r'^takerace: ') for g in games):
        return 'NOT SEEN', 'no "takerace:" line (TAKERACE is not in this build: v3.9.21 option)'
    refused = []
    for g in games:
        for ln in find(g, r'^takerace: (\S+ \d+ h=[0-9a-f]+ round \d+ park #\d+: the authority refused|own press on '
                          r'\S+ \d+ h=[0-9a-f]+ round \d+ refused)'):
            m = re.search(r'h=([0-9a-f]+) round (\d+)', ln.text)
            refused.append((g, ln, m[1], int(m[2])))
    timeouts = [(g, ln) for g in games for ln in find(g, r'^takerace: .*no answer from the authority')]
    races = [(g, ln) for g in games for ln in find(g, r'first-taker race|holder race')]
    for g, ln, h, r in refused:
        took = [x for x in find(g, rf'^taken: \S+ \d+ h={h} round {r}: .*\(gained here\)')
                if 0 <= (secs(x.t) - secs(ln.t)) % 86400 <= 10]
        if took:
            return 'FAIL', show(g, ln, 120) + '; ' + show(g, took[0], 110) + '  (refused, but taken here anyway)'
    if races and not timeouts:
        g, ln = races[0]
        return 'FAIL', show(g, ln, 130) + '  (two takers with TAKERACE on and no timeout: the authority did not decide)'
    if refused:
        g, ln, h, r = refused[0]
        return 'PASS', (f'{len(refused)} second press(es) refused by the authority and not taken there, e.g. '
                        + show(g, ln, 120))
    if timeouts:
        g, ln = timeouts[0]
        return 'ASK', show(g, ln, 130) + '  (no answer in 1.5 s: taken the old way; check the FlameL counters)'
    return 'ASK', ('takerace is on, but no second press was refused in these logs (one presser only): '
                   'run diag/twin/flamerace.py N same strict=1')


def rowLH(ctx):
    """Loading hang, v4.37 NEEDDATA (diag/net/b_loadhang_notes.md, assist_v437_needdata.diff): a game that still has
    no chr for a member 8 s into the match asks it again every 5 s, and through the side channel too; the other game
    puts the requester's id in its game's NEEDDATA box (needdata_live.py). PASS: every waiting game logs 'its character is here now'.
    FAIL: a game keeps asking (6+ requests) and its wait never ends in that match."""
    games = ctx['games']
    waits = {}
    for g in games:
        asks = find(g, r'has no character here yet: player data asked for again')
        if asks:
            waits[g.label] = (g, asks)
    if not waits:
        return 'NOT SEEN', 'no game waited for a player\'s data (no "has no character here yet" line)'
    side = [(g, ln) for g in games for ln in find(g, r'asked through the side channel too \(v4\.37 NEEDDATA')]
    queued = [(g, ln) for g in games for ln in find(g, r"its id is queued in our game's NEEDDATA box")]
    refused = [(g, ln) for g in games for ln in find(g, r'waits for our player data, not queued: ')]
    stuck = []
    for lab, (g, asks) in waits.items():
        here = [ln for ln in find(g, r'its character is here now \(after \d+ request') if ln.sec >= asks[-1].sec]
        if here:
            continue
        if len(asks) >= 6:
            stuck.append((g, asks[-1]))
    if stuck:
        g, ln = stuck[0]
        why = ('; ' + show(*refused[0], 120)) if refused else ('' if side else '  (NEEDDATA is not in this build)')
        return 'FAIL', show(g, ln, 120) + why
    if not side:
        g, asks = next(iter(waits.values()))
        return 'NOT SEEN', show(g, asks[0], 110) + '  (a short wait that ended; NEEDDATA is not in this build)'
    g, ln = (queued or side)[0]
    note = '' if queued else '  (ended without a queued answer: the plain re-request did it)'
    return 'PASS', show(g, ln, 140) + note + f'  ({len(waits)} waiting game(s), every wait ended)'


MATCH1 = [('1', row1), ('2', row2), ('3', row3), ('4', ask('fall kill: the user says (no log line)')),
          ('5', ask('Moon Phase Watch: the user says (no log line)')), ('6', row6), ('39', row39), ('39L', row39l), ('42g', row42g), ('8t', row8t), ('8r', row8r),
          ('LH', rowLH)]
MATCH2 = [('1', row1), ('7', ask('Blink vanish on the laptop: ask the user (no log line)')),
          ('8', ask('solo hub cutscene skip: ask the user (no log line)')), ('9', row9), ('10', row10),
          ('11', row11), ('12', row12), ('39', row39), ('39L', row39l), ('42g', row42g), ('8t', row8t), ('8r', row8r),
          ('LH', rowLH)]
FOUR = [('1', row1), ('13', row13), ('14', row14), ('15', row15), ('16', row16), ('17', row17), ('18', row18), ('39', row39), ('39L', row39l),
        ('42g', row42g), ('8t', row8t), ('8r', row8r), ('LH', rowLH)]


def run_cutcheck(games):
    with tempfile.TemporaryDirectory() as td:
        args = []
        for g in games:
            f = Path(td) / f'{re.sub(r"[^A-Za-z0-9_-]", "_", g.label)}.txt'
            f.write_text('\n'.join(f'{ln.t} {ln.text}' for ln in g.match) + '\n', encoding='utf-8')
            args.append(f'{re.sub(r"[:]", "_", g.label)}:{f}')
        r = subprocess.run([sys.executable, str(HERE / 'cutcheck.py')] + args, capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
    out = r.stdout.splitlines()
    flags = next((int(m[1]) for ln in out for m in [re.search(r'^(\d+) disagreement\(s\) flagged', ln)] if m), None)
    return {'flags': flags if flags is not None else -1, 'bang': [ln for ln in out if '!!' in ln],
            'taken': [ln.strip() for ln in out if ln.strip().startswith('taken as cut:')], 'out': out}


def grade(m_no, specs, build=None, rows=None, force_cc=False, verbose=False, quiet_header=False):
    logs = Logs()
    for s in specs:
        logs.add(s)
    games = [g for g in logs.games if g.files]
    for g in games:
        choose(g)
        if build:
            g.build, g.build_src = build, '--build'
    players = max([g.players or 0 for g in games] + [0])
    four = players >= 4
    exact = [g for g in games if g.build and 'at least' not in g.build_src]
    pool = exact or [g for g in games if g.build]
    b = max((g.build for g in pool), key=vkey) if pool else None
    bsrc = next((g.build_src for g in pool if g.build == b), '')
    want = {'1': ['3.9.16'], '2': ['3.9.17', '3.9.18', '3.9.20']}.get(str(m_no), ['3.9.20'])
    if four:
        want = ['3.9.20']
    out = []
    if not quiet_header:
        out.append(f'card_check: match {m_no}, {len(games)} game(s), {players or "?"} players'
                   + (' (4-player rows)' if four else ''))
        for g in games:
            rng = f'{g.match[0].t}-{g.match[-1].t}' if g.match else 'no lines'
            out.append(f'  {g.label}: player {g.no}, build {("v" + g.build) if g.build else "?"} '
                       f'{("(" + g.build_src + ")") if g.build_src else ""}, match {rng} in '
                       f'{Path(g.chosen).name if g.chosen else "?"}, eden {"yes" if g.eden else "no"}'
                       + (f'; {g.note}' if g.note else ''))
        for kind in ('fx', 'blink', 'fps', 'storm'):
            for lab, src, _ in getattr(logs, kind):
                out.append(f'  {kind}: {src}')
        if b and b not in want and not ('at least' in bsrc and vkey(b) <= vkey(want[0])):
            out.append(f'  !! build v{b} ({bsrc}); the card\'s match {m_no} uses v{" / v".join(want)}')
    ctx = {'games': games, 'logs': logs, 'build': b, 'build_src': bsrc,
           'fx': extra_lines(logs, 'fx', m_no, ['fx_probe_night_m{m}.txt']),
           'blink': extra_lines(logs, 'blink', m_no, ['blink_site_night_m{m}.txt']),
           'fps': logs.fps, 'cutcheck': None,
           'storm': extra_lines(logs, 'storm', m_no, ['storm_watch_night_m{m}.txt'])}
    if four or force_cc:
        ctx['cutcheck'] = run_cutcheck(games)
        cc = ctx['cutcheck']
        out.append(f'  cutcheck: {cc["flags"]} disagreement(s) flagged, {len(cc["bang"])} "!!" line(s)'
                   + (f'; {cc["taken"][0]}' if cc['taken'] else ''))
    table = FOUR if four else MATCH1 if str(m_no) == '1' else MATCH2
    for name, fn in table:
        if rows and name not in rows:
            continue
        status, ev = fn(ctx)
        out.append(f'row {name:<4} {status:<8} {ev}')
    if four or b == '3.9.20':
        for name, status, ev in must_not(ctx, extra=not four):
            if not rows or 'not' in rows:
                out.append(f'{name:<9} {status:<8} {ev}')
    if verbose and ctx['cutcheck']:
        out += ['  | ' + ln for ln in ctx['cutcheck']['out']]
    return out


# ---- self-test --------------------------------------------------------------------------------------------

def selftest():
    import io
    base = 0x80000000
    def log(no, extra):
        head = [f'00:00:01 Duskbloods LAN assist started', f'00:00:02 main base {base:#x}; built-in LAN patch active',
                f'00:00:10 player no {no} team {no} (3 players): message 4 armed',
                f'00:00:11 message 4 delivered: player no is now {no}',
                '00:01:00 map: new match (session 0x1, stage 0x2, round 1 after 0, match load #1); map sharing state reset']
        return '\n'.join(head + extra) + '\n'
    guest = ["00:20:00 area icons: round 3 9 entries handed to the game from player 1's list (pass 1, 9 here before)",
             '00:30:00 area icons: round 4: the list handed in round 3 is emptied (no list from the host for this round yet)',
             '00:30:05 final: player 1 is in the final with us',
             '00:31:00 cutscene vote: cutscene 77: 3 / 3 players voted to skip',
             '00:31:00 cutscene vote: all 3 players voted; cutscene 77 skipped here (CUTSCENE_VOTE)',
             '00:31:10 power choice: chosen Power 0x00001234 stored (held award 0x00001111, another entry) (POWER_CHOICE)',
             "00:32:00 final: the game took player 1's elimination (stage 04 05 01 01; its copy stays here as a dead body (FIREKEEP skip 1, player 1))"]
    global WS
    ws_real = WS
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        WS = td   # the night's real diag/net/*_night_m<M>.txt probe files must not reach the self-test
        try:
            return _selftest_body(td, log, guest, base)
        finally:
            WS = ws_real


def _selftest_body(td, log, guest, base):
    if True:
        rig = td / 'user3p_1118_m2'
        rig.mkdir()
        (rig / 'A_dusk_lan.txt').write_text(log(1, ['00:30:00 map: round 4 seen here as the host; lists-ready flag 0 (phase 18)']))
        (rig / 'B_dusk_lan.txt').write_text(log(3, guest))
        (rig / 'build.txt').write_text('3.9.18\n')
        (rig / 'night_fps_m2.log').write_text('00:00:05 fps_watch AB for 3600 s\n')
        zp = td / 'DuskLogs_LAPTOP.zip'
        with zipfile.ZipFile(zp, 'w') as z:
            z.writestr('DuskLogs_LAPTOP/SUMMARY.txt', '3 file(s) from this PC (X), package v3.9.18 (commit 3d5156cb4e), collected')
            z.writestr('DuskLogs_LAPTOP/game1/dusk_lan.txt', log(2, guest[:3]))
            z.writestr('DuskLogs_LAPTOP/game1/eden_log.txt',
                       '[   0.001] Frontend <Info> x: Lichii Version: test\n'
                       '[1805.000] Core.ARM <Error> core\\arm\\arm_interface.cpp:43:LogBacktrace: Backtrace @ PC=0000000000000004\n'
                       f'R28=0000000000000001 R29=0000000000000000 R30={base + CRASH_LR:016X} R31=0000000000000000\n')
        blink = td / 'blink.txt'
        blink.write_text('00:10:00 SpEffect 1401010 w5=1 chr=0x2100 lr=main+0x194b8e0 (site main+0x194b8dc)\n')
        fx = td / 'fx.txt'
        fx.write_text('  10.0 B p1: DIES (HP 100 -> 0) (pos (1, 2, 3), 12 SpEffects)\n'
                      '  17.0 B p1: GONE (no entry, old chr no longer names it)\n')
        res = grade(2, [str(rig), f'laptop:{zp}'])
        txt = '\n'.join(res)
        checks = [('row 1    FAIL', 'the laptop crash (R30 - main base = 0x3FFA0DC) fails row 1'),
                  ('row 9    PASS', 'the 3 / 3 vote with its skip line passes row 9'),
                  ('row 10   ASK', 'a stored choice is shown for the user'),
                  ('row 12   ASK', 'the FIREKEEP took line is found'),
                  ('build v3.9.18 (build.txt)', 'build.txt is read'),
                  ('(SUMMARY.txt (commit 3d5156cb4e))', 'SUMMARY.txt in a zip is read')]
        storm_ok = td / 'storm_ok.txt'
        storm_ok.write_text('00:19:00 storm_watch AB for 3600 s\n'
                            '00:20:00 A: storm summary: highest step 9, entries 3, moved yes, our entry (1.0, 2.0, 3.0)\n'
                            '00:20:00 B: storm summary: highest step 9, entries 3, moved yes, our entry (4.0, 5.0, 6.0)\n')
        storm_bad = td / 'storm_bad.txt'
        storm_bad.write_text('00:19:00 storm_watch AB for 3600 s\n'
                             '00:20:00 A: storm summary: highest step 9, entries 3, moved yes, our entry (1.0, 2.0, 3.0)\n'
                             '00:20:00 B: storm summary: highest step 3, entries 0, moved no, our entry ?\n')
        txt_s = '\n'.join(grade(1, [str(rig), f'storm:{storm_ok}'], build='3.9.16', rows=['39'], quiet_header=True))
        txt_b = '\n'.join(grade(1, [str(rig), f'storm:{storm_bad}'], build='3.9.16', rows=['39'], quiet_header=True))
        res1 = grade(1, [str(rig), f'blink:{blink}', f'fx:{fx}'], build='3.9.16')
        txt1 = '\n'.join(res1) + '\n' + txt_s + '\n' + txt_b.replace('row 39   FAIL', 'row 39b  FAIL')
        storm_l_ok = td / 'storm_l_ok.txt'
        storm_l_ok.write_text('00:19:00 storm_watch AB for 3600 s\n'
                              '00:19:10 A: storm step 2 -> 3 WaitIndication (entries 0)\n'
                              '00:19:11 B: storm step 2 -> 3 WaitIndication (entries 0)\n'
                              '00:20:00 A: storm step 3 -> 4 Indication (entries 2)\n'
                              '00:20:01 B: storm step 3 -> 4 Indication (entries 2)\n')
        storm_l_bad = td / 'storm_l_bad.txt'
        storm_l_bad.write_text('00:19:00 storm_watch AB for 3600 s\n'
                               '00:20:00 A: storm step 3 -> 4 Indication (entries 2)\n'
                               '00:20:01 B: storm step 3 -> 4 Indication (entries 2)\n'
                               '00:20:20 A: storm step 8 -> 3 WaitIndication (entries 2)\n'
                               '00:20:30 A: storm step 3 -> 4 Indication (entries 2)\n'
                               '00:20:31 B: storm step 7 -> 8 FinishProcess (entries 2)\n'
                               '00:20:32 B: storm step 8 -> 3 WaitIndication (entries 2)\n')
        txt_l = '\n'.join(grade(1, [str(rig), f'storm:{storm_l_ok}'], build='3.9.16', rows=['39L'], quiet_header=True))
        txt_lb = '\n'.join(grade(1, [str(rig), f'storm:{storm_l_bad}'], build='3.9.16', rows=['39L'], quiet_header=True))
        txt1 += '\n' + txt_l + '\n' + txt_lb.replace('row 39L  FAIL', 'row 39Lb FAIL')
        checks1 = [('row 39   PASS', 'two storm summaries at step 9, moved: row 39 PASS'),
                   ('row 39b  FAIL', 'B stuck at step 3 while A reached 9: row 39 FAIL'),
                   ('row 39L  PASS', 'storm: both games went 3 -> 4 in the same second: row 39L PASS'),
                   ('row 39Lb FAIL', 'storm: B was at step 7 when the second record came: row 39L FAIL'),('row 1    PASS', 'B alone reaches the final with no crash: PASS with notes'),
                   ('row 6    PASS', 'the blink line at lr 0x194b8e0, w5=1 passes row 6'),
                   ('row 3    ASK', 'GONE 7 s after DIES: plan A'),
                   ('row 2    ASK', 'the icon hand-over is shown')]
        four = td / 'four'
        four.mkdir()
        fin = ['00:40:00 final: player {a} is in the final with us', '00:40:00 final: player {b} is in the final with us']
        cut = ['00:30:00 cut check (F1): round 3 step 10: our list (no:rank) 1:1 2:2 3:3 4:4 hash 0000abcd; state words; '
               'ranked totals 1=9 2=6 3=3 4=0; compared with the authority\'s list',
               "00:30:02 cut (CUTAUTH): round 3: the authority's list (player 1, hash 0000abcd) is in the mailbox "
               "(no:rank 1:1 2:2 3:3 4:4); our cut will use it",
               '00:30:20 H1: player 4 is cut (its game is at result step 14 while the match goes on); it is no longer '
               'taken as the host or waited for, for the rest of this match (latched: review5 A)']
        for no, others in ((1, (2, 3)), (2, (1, 3)), (3, (1, 2))):
            lines = [ln.replace('compared with the authority\'s list', 'we are the authority: sent to the others')
                     if no == 1 else ln for ln in cut if not (no == 1 and 'mailbox' in ln)]
            lines += [x.format(a=others[0], b=others[1]) for x in fin]
            if no == 1:
                lines.append('00:40:05 final: start slots added for player(s) 2, 3 (1 -> 3 slots); the start list is built again')
                lines.append('00:40:06 final: start list rebuilt, 3 entries: player 1 area 4 at (-9.1, 8.7), '
                             'player 2 area 3 at (4.9, -0.4), player 3 area 2 at (4.0, 14.5)')
            (four / f'P{no}.txt').write_text(log(no, lines).replace('(3 players)', '(4 players)'))
        (four / 'P4.txt').write_text(log(4, ['00:30:15 H1: our player (no 4) is cut (step 14, round 3); this game is '
                                             'not the authority any more and sends no host messages']).replace('(3 players)', '(4 players)'))
        res4 = grade(3, [f'P{n}:{four / f"P{n}.txt"}' for n in (1, 2, 3, 4)], build='3.9.20')
        txt4 = '\n'.join(res4)
        checks4 = [('row 14   PASS', 'the authority F1 line and one cut player pass row 14'),
                   ('row 16   PASS', 'start slots for 2, 3 (4 cut) pass row 16'),
                   ('row 17   NOT SEEN', 'player 1 not cut: row 17 not seen'),
                   ('not: v4.33 majority guard PASS', 'no majority guard line'),
                   ('cutcheck:', 'cutcheck runs for 4 players')]
        gala = td / 'gala'
        gala.mkdir()
        g_host = ['00:10:00 environment event 1220 drawn here (round 2)',
                  '00:10:01 map: round 2 lists drawn here (6064 bytes, 40 records) and sent to the other players (x)']
        (gala / 'A_dusk_lan.txt').write_text(log(1, g_host))
        (gala / 'B_dusk_lan.txt').write_text(log(3, ['00:10:01 map: round 2 lists are coming from player 1 (40 records)',
                                                     '00:10:02 environment event 1220 from player 1 (round 2)',
                                                     '00:10:03 map: round 2 lists from the host are in (40 records, match step 21)']))
        txt_g = '\n'.join(grade(2, [str(gala)], build='3.9.20', rows=['42g'], quiet_header=True))
        (gala / 'B_dusk_lan.txt').write_text(log(3, ['00:10:02 environment event 1220 from player 1 (round 2)',
                                                     '00:10:30 map: no lists from the host for round 2 after 30 s (x); going on']))
        txt_gb = '\n'.join(grade(2, [str(gala)], build='3.9.20', rows=['42g'], quiet_header=True))
        tk = td / 'taken'
        tk.mkdir()
        scan = '00:05:00 taken: round 2: 205 shared objects found ( flame 111 flameL 25 flameL* 3 kin 3 small 63 ); their taken state is shared'
        (tk / 'A_dusk_lan.txt').write_text(log(1, [scan, '00:06:00 taken: flameL 99281 h=6000013e from player 3 (round 2): slots 000 -> 004, used 0 -> 1, holder -1 -> -1; applied']))
        (tk / 'B_dusk_lan.txt').write_text(log(3, [scan, '00:06:00 taken: flameL 99281 h=6000013e round 2: players 0x4 (slots 004) used 1 holder -1 taker 3 (gained here); sent to the others (x3)']))
        txt_t = '\n'.join(grade(2, [str(tk)], build='3.9.20', rows=['8t'], quiet_header=True))
        (tk / 'A_dusk_lan.txt').write_text(log(1, [scan.replace('kin 3', 'kin 6').replace('205', '208')]))
        txt_tb = '\n'.join(grade(2, [str(tk)], build='3.9.20', rows=['8t'], quiet_header=True))
        txt4 += '\n' + txt_t + '\n' + txt_tb.replace('row 8t   FAIL', 'row 8tb  FAIL')
        checks4 += [('row 8t   PASS', 'taken: same layout, B\'s change applied on A: row 8t PASS'),
                    ('row 8tb  FAIL', 'taken: round layouts differ (205 vs 208): row 8t FAIL')]
        tr = td / 'takerace'
        tr.mkdir()
        hl = ['00:05:30 takerace: mode authority (this game is the authority: it decides shared pay-once takes) (TAKERACE)',
              '00:06:00 taken: flameL 99281 h=6000013e round 2: players 0x1 (slots 001) used 1 holder -1 taker 1 (gained here); sent to the others (x7 in about 16 s)',
              '00:06:00 takerace: player 3 asks for flameL 99281 h=6000013e round 2 (game 0x12345678, ask #1): refused (player 1 was granted it first)']
        gl = ['00:05:31 takerace: the authority (player 1, game 0x0badf00d) is ready: a shared pay-once take here waits for its answer (TAKERACE)',
              '00:06:00 takerace: flameL 99281 h=6000013e round 2 (player 3): pressed here; the grant waits for the authority (park #1, asked player 1)',
              '00:06:00 takerace: flameL 99281 h=6000013e round 2 park #1: the authority refused it (player 1 was granted it first) after 140 ms; not taken here',
              '00:06:00 taken: flameL 99281 h=6000013e from player 1 (round 2): slots 000 -> 001, used 0 -> 1, holder -1 -> -1; applied']
        (tr / 'A_dusk_lan.txt').write_text(log(1, hl))
        (tr / 'B_dusk_lan.txt').write_text(log(3, gl))
        txt_r = '\n'.join(grade(2, [str(tr)], build='3.9.20', rows=['8r'], quiet_header=True))
        (tr / 'B_dusk_lan.txt').write_text(log(3, gl + ['00:06:01 taken: flameL 99281 h=6000013e round 2: players 0x5 (slots 005) used 1 holder -1 taker 1 (gained here); sent to the others (x7 in about 16 s)']))
        txt_rb = '\n'.join(grade(2, [str(tr)], build='3.9.20', rows=['8r'], quiet_header=True))
        txt4 += '\n' + txt_r + '\n' + txt_rb.replace('row 8r   FAIL', 'row 8rb  FAIL')
        checks4 += [('row 8r   PASS', 'takerace: the second press refused and not taken there: row 8r PASS'),
                    ('row 8rb  FAIL', 'takerace: refused but gained here anyway: row 8r FAIL')]
        lh = td / 'loadhang'
        lh.mkdir()
        ask_l = '00:03:{:02d} player 0xd48394cf86 has no character here yet: player data asked for again (#{})'
        b_wait = [ask_l.format(29, 1),
                  '00:03:29 player data: player 0xd48394cf86 asked through the side channel too (v4.37 NEEDDATA #1, our member id 0xd495550863)']
        (lh / 'A_dusk_lan.txt').write_text(log(2, ["00:03:29 player data: player 3 (0xd495550863) still waits for ours (its request #1); its id is queued in our game's NEEDDATA box, answered on its next tick that can answer (0 answered so far, state 8) (v4.37 NEEDDATA)"]))
        (lh / 'B_dusk_lan.txt').write_text(log(3, b_wait + ['00:03:30 player 0xd48394cf86: its character is here now (after 1 request(s) in this wait; v4.37 NEEDDATA)']))
        txt_h = '\n'.join(grade(2, [str(lh)], build='3.9.20', rows=['LH'], quiet_header=True))
        (lh / 'A_dusk_lan.txt').write_text(log(2, ["00:03:29 player data: player 3 (0xd495550863) waits for our player data, not queued: the NEEDDATA box is still full: our game cannot answer yet (state 7) (v4.37 NEEDDATA)"]))
        (lh / 'B_dusk_lan.txt').write_text(log(3, b_wait + [ask_l.format(30 + 5 * k, k + 2) for k in range(6)]))
        txt_hb = '\n'.join(grade(2, [str(lh)], build='3.9.20', rows=['LH'], quiet_header=True))
        txt4 += '\n' + txt_h + '\n' + txt_hb.replace('row LH   FAIL', 'row LHb  FAIL')
        checks4 += [('row LH   PASS', 'loadhang: the answer queued on A, B logs its character here: row LH PASS'),
                    ('row LHb  FAIL', 'loadhang: B asks 7 times, A could not queue: row LH FAIL')]
        txt4 += '\n' + txt_g + '\n' + txt_gb.replace('row 42g  FAIL', 'row 42gb FAIL')
        checks4 += [('row 42g  ASK', 'Gala: the guest took the host\'s 40-record set: log part passes, user asked'),
                    ('row 42gb FAIL', 'Gala: no lists from the host for the Gala round: FAIL')]
        bad = [why for s, why in checks if s not in txt] + [why for s, why in checks1 if s not in txt1] + \
              [why for s, why in checks4 if s not in txt4]
        checks1 += checks4
        print(txt)
        print(txt1)
        print(txt4)
        if bad:
            print('selftest FAIL:', bad)
            return 1
        print(f'selftest PASS ({len(checks) + len(checks1)} checks)')
        return 0


def main(argv):
    if '--selftest' in argv:
        return selftest()
    build = rows = None
    args, force_cc, verbose = [], '--cutcheck' in argv, '-v' in argv
    it = iter(argv)
    for a in it:
        if a == '--build':
            build = next(it).lstrip('v')
        elif a == '--rows':
            rows = next(it).split(',')
        elif a in ('--cutcheck', '-v'):
            continue
        else:
            args.append(a)
    if len(args) < 2:
        print(__doc__)
        return 2
    for line in grade(args[0], args[1:], build, rows, force_cc, verbose):
        print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
