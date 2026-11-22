r"""after_match.py: READ-ONLY verdict table of one 2-8 player match from every dusk_lan.txt we have.
Written 2026-11-17 (static; not run yet).

Usage (workspace root):
    python diag/twin/pkgtest.py run diag/twin/after_match.py [--at HH:MM] [--guests DIR] [LABEL:path ...]
    python diag/twin/after_match.py [same options]

Logs read (nothing is written):
  - this PC's rig games A and B (lanlog.LAN, which pkgtest.py run points at the pkgtest games);
  - every guest folder dropped into diag/net/guests/<name>/ (the guest's "Collect logs" zip, unpacked): each
    dusk_lan.txt found anywhere below it (rotated dusk_lan.N.txt files are older runs and are skipped);
  - any extra LABEL:path given on the command line.
Match: the LAST match ("map: new match") of each log, or with --at HH:MM the match of each log that started
nearest to that time (a guest PC's clock may differ by minutes: the nearest is taken, and its start is shown).
Parsing reuses cutcheck.parse (cut lists, H1 / F4 cuts, Virtue, drives, final placement, Bloodbound lines).

Rows (PASS / FAIL / CHECK = look at it yourself / n/a), each with the games that reported:
  numbering   every game's own number and player count: numbers 1..N with no duplicate and no gap among the
              games that reported (N = the match's player count); no "DUPLICATE PLAYER NUMBER" line
  cut rN      rounds 2 and 3 (and any other with a list): the last F1 list (no:rank) and hash equal on every
              game that logged one; the H1 / F4 cut sets equal; no "CUT MISMATCH"
  authority   per round at most one game says "we are the authority" in its F1 line
  culled out  v410: a player cut in round r is never "in a match step again" later on any game, and a cut
              game's own log shows no UpdatePhase (step 6) of a later round
  hand-over   when player 1 was cut or left: some game logs a "hand-over:" line and a later F1 authority is not
              player 1 (n/a when player 1 stayed)
  final       the final placement ("player N rank R") equal on every game that logged one
  pairs       Bloodbound (rule 2): the F3 data / placement Bloodbound lines equal; n/a otherwise
  enemies     sum over the reporting games of the median "drives X of Y" in round 1: about Y when every
              game reported (CHECK otherwise: guests that sent no log drive the rest)
  !!!         the number of "!!!" lines per game in that match
Exit code 0 = no FAIL row, 1 = at least one FAIL.
"""
import os
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
sys.path.insert(0, str(HERE))
import cutcheck  # noqa: E402

R_NEWMATCH = re.compile(r'map: new match')
R_TIME = re.compile(r'^(\d\d):(\d\d):(\d\d) ')
R_DUP = re.compile(r'DUPLICATE PLAYER NUMBER')
R_BACK = re.compile(r'H1: player (\d+) is in a match step again')
R_OWNCUT = re.compile(r'H1: our player \(no (\d+)\) is cut')
R_PHASE = re.compile(r'match phase (\d+)')
R_ROUND = re.compile(r'\bround (\d+)')
R_HAND = re.compile(r'hand-over:')
R_PLACE = re.compile(r'player (\d+) rank (\d+)')
R_ENTRIES = re.compile(r'final: (?:our \(host\) final entries are sent|the host\'s \(player \d+\) final entries)')
R_SAME = re.compile(r'cut check \(F1\): round (\d+): same list as the authority \(player (\d+)\)')
R_P1QUIET = re.compile(r"peer player 1: no side message for|player 1 not heard for|player 1's total -?\d+ not heard")


def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        val = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return val
    return default


def logs(guest_dir, rig):
    out = []
    if rig:
        try:
            import lanlog
            for w in 'AB':
                p = Path(lanlog.LAN[w])
                if p.is_file():
                    out.append((w, p))
        except Exception:
            pass
    if guest_dir is not None and guest_dir.is_dir():
        for name in sorted(os.listdir(guest_dir)):
            for p in sorted((guest_dir / name).rglob('dusk_lan.txt')):
                rel = p.relative_to(guest_dir / name).parent.as_posix()
                out.append((name if rel == '.' else f'{name}/{rel}', p))
    for a in sys.argv[1:]:
        if ':' in a and not re.match(r'^[A-Za-z]:[\\/]', a):
            label, path = a.split(':', 1)
        else:
            label, path = Path(a).parent.name, a
        out.append((label, Path(path)))
    # labels must be unique (a dict per label below): a second 'A' becomes 'A#2'
    seen, unique = {}, []
    for label, path in out:
        seen[label] = seen.get(label, 0) + 1
        unique.append((label if seen[label] == 1 else f'{label}#{seen[label]}', path))
    return unique


def secs(hh, mm, ss=0):
    return int(hh) * 3600 + int(mm) * 60 + int(ss)


def pick(g, at):
    """index of the chosen match in cutcheck's Game, or -1"""
    if not g.matches:
        return -1
    if at is None:
        return len(g.matches) - 1
    want = secs(*at.split(':')[:3])
    best = None
    for i, meta in enumerate(g.meta):
        try:
            s = secs(*meta['start'].split(':'))
        except (ValueError, TypeError):
            continue
        d = min(abs(s - want), 86400 - abs(s - want))
        if best is None or d < best[0]:
            best = (d, i)
    return best[1] if best else len(g.matches) - 1


def window(path, index):
    """The log lines of the index-th match (from its 'map: new match' up to the next one)."""
    lines = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    out, n = [], -1
    for ln in lines:
        if R_NEWMATCH.search(ln):
            n += 1
            if n > index:
                break
        if n == index:
            out.append(ln)
    return out


class View:
    def __init__(self, label, path, at):
        self.label, self.path = label, path
        self.g = cutcheck.parse(label, str(path))
        self.mi = pick(self.g, at)
        self.rounds = self.g.matches[self.mi] if self.mi >= 0 else {}
        self.meta = self.g.meta[self.mi] if self.mi >= 0 else {}
        self.lines = window(path, self.mi) if self.mi >= 0 else []


def row(rows, name, verdict, text):
    rows.append((name, verdict, text))


def main():
    at = arg('--at')
    rig = '--rig' in sys.argv
    if rig:
        sys.argv.remove('--rig')
    guests = arg('--guests')
    explicit = any(not a.startswith('--') for a in sys.argv[1:])
    # Explicit LABEL:path logs: only those (plus --guests DIR / --rig when given). No logs named: this PC's rig
    # games A and B plus diag/net/guests/<name>/ (the live-session default).
    guest_dir = Path(guests) if guests else (None if explicit else WS / 'diag' / 'net' / 'guests')
    views = []
    for label, path in logs(guest_dir, rig or not explicit):
        try:
            v = View(label, path, at)
        except OSError as e:
            print(f'{label}: cannot read {path} ({e})')
            continue
        if v.mi < 0:
            print(f'{label}: no match in {path}')
            continue
        views.append(v)
    if not views:
        print('after_match: no log with a match')
        return 1
    print('games:', '; '.join(f'{v.label} = player {v.meta.get("no")} of {v.meta.get("players")}, match start '
                               f'{v.meta.get("start")}, rule {v.meta.get("rule")}' for v in views))
    rows = []

    # numbering
    nos = [v.meta.get('no') for v in views]
    counts = {v.meta.get('players') for v in views if v.meta.get('players')}
    n = max(counts) if counts else None
    dups = sum(1 for v in views for ln in v.lines if R_DUP.search(ln))
    known = [x for x in nos if x is not None]
    bad = len(known) != len(set(known)) or dups or (n and any(x < 1 or x > n for x in known)) or len(counts) > 1
    row(rows, 'numbering', 'FAIL' if bad else 'PASS',
        f'numbers {nos}, player counts {sorted(counts)}, DUPLICATE lines {dups}'
        + ('' if n is None or len(known) == n else f' ({n - len(known)} game(s) sent no log)'))

    # cuts and authority per round
    rounds = sorted({r for v in views for r in v.rounds})
    cut_by_round, authority_by_round = {}, {}
    for r in rounds:
        lists, sets, auth, miss = {}, {}, set(), 0
        for v in views:
            rd = v.rounds.get(r)
            if rd is None:
                continue
            if rd.cutlists:
                _, entries, h, role = rd.cutlists[-1]
                lists[v.label] = (tuple((a, b) for a, b, _ in entries), h)
                if role == 'authority':
                    auth.add(v.label)
            if rd.cut:
                sets[v.label] = tuple(sorted(rd.cut))
            miss += sum(1 for x in rd.verdicts if 'MISMATCH' in x)
        cut_by_round[r] = set().union(*[set(s) for s in sets.values()]) if sets else set()
        if lists or sets:
            same = len({x for x in lists.values()}) <= 1 and len(set(sets.values())) <= 1 and not miss
            # a follower's "same list as the authority (player N)" compares its hash with the authority's game:
            # with one list here that still covers two games (the authority may be a guest without a log)
            confirmed = [v.label for v in views if v.label in lists and any(
                (m := R_SAME.search(ln)) and int(m[1]) == r for ln in v.lines)]
            enough = len(lists) >= 2 or confirmed
            row(rows, f'cut r{r}', 'PASS' if same and enough else ('FAIL' if not same else 'CHECK'),
                '; '.join(f'{k}: ' + (' '.join(f'{a}:{b}' for a, b in lists[k][0]) + f' #{lists[k][1]}'
                                       if k in lists else 'no list') + f' cut {list(sets.get(k, ()))}'
                          for k in sorted(set(lists) | set(sets)))
                + (f'; CUT MISMATCH lines {miss}' if miss else '')
                + ('' if len(lists) >= 2 else (f' (one list; {confirmed} "same list as the authority")' if confirmed
                                                else ' (fewer than 2 games logged a list)')))
        # the authority's player number per round: a game's own number when it says "we are the authority",
        # and the number every follower names in "same list as the authority (player N)"
        named = {}
        for v in views:
            if v.label in auth and v.meta.get('no') is not None:
                named.setdefault(v.meta['no'], set()).add(f'{v.label} (self)')
            for ln in v.lines:
                m = R_SAME.search(ln)
                if m and int(m[1]) == r:
                    named.setdefault(int(m[2]), set()).add(v.label)
        authority_by_round[r] = set(named)
        if named:
            row(rows, f'authority r{r}', 'PASS' if len(named) == 1 else 'FAIL',
                '; '.join(f'player {no}: {sorted(src)}' for no, src in sorted(named.items())))

    # culled players stayed out (v410)
    problems = []
    for v in views:
        cut_round, cur_round = {}, 0
        for ln in v.lines:
            m = R_ROUND.search(ln)
            if m and 1 <= int(m[1]) <= 4:
                cur_round = int(m[1])
            m = R_OWNCUT.search(ln)
            if m:
                cut_round.setdefault('own', cur_round)
            m = R_PHASE.search(ln)
            if m and int(m[1]) == 6 and 'own' in cut_round and cur_round > cut_round['own']:
                problems.append(f'{v.label}: our player was cut in round {cut_round["own"]} but this game '
                                f'plays step 6 of round {cur_round}')
                cut_round['own'] = 99
            m = R_BACK.search(ln)
            if m:
                no = int(m[1])
                early = [r for r, s in cut_by_round.items() if no in s and r < cur_round]
                if early:
                    problems.append(f'{v.label}: player {no} (cut in round {early[0]}) "in a match step again" '
                                    f'in round {cur_round}')
    any_cut = any(cut_by_round.values())
    row(rows, 'culled out', 'FAIL' if problems else ('PASS' if any_cut else 'n/a'),
        '; '.join(problems) if problems else ('no cut player came back' if any_cut else 'nobody was cut'))

    # hand-over (player 1 cut or left). Signs on the games that stayed: player 1 cut (H1), its side messages
    # stop ("peer player 1: no side message", "player 1 not heard"), rank 255 in a cut list, or missing from a
    # later list. The new authority's own "hand-over:" lines are only in ITS log (often a guest's).
    signs = set()
    for v in views:
        for i, ln in enumerate(v.lines):
            # silence counts only while the match goes on (a later cut check): at the match end every game
            # stops sending
            if R_P1QUIET.search(ln) and any('cut check (F1): round' in x for x in v.lines[i + 1:]):
                signs.add(f'{v.label}: {ln[:8]} player 1 silent')
                break
    for r in rounds:
        if 1 in cut_by_round.get(r, ()):
            signs.add(f'player 1 cut in round {r}')
        for v in views:
            rd = v.rounds.get(r)
            if rd and rd.cutlists:
                ent = {a: b for a, b, _ in rd.cutlists[-1][1]}
                if ent.get(1) == 255 or (ent and 1 not in ent):
                    signs.add(f'{v.label}: player 1 {"rank 255" if 1 in ent else "not listed"} in round {r}')
    hand = [v.label for v in views if any(R_HAND.search(ln) for ln in v.lines)]
    later = {r: sorted(nos - {1}) for r, nos in authority_by_round.items() if nos - {1}}
    if signs:
        row(rows, 'hand-over', 'PASS' if later or hand else 'CHECK',
            f'player 1 gone ({"; ".join(sorted(signs))}); later authority '
            + (', '.join(f'r{r}: player {"/".join(map(str, n))}' for r, n in sorted(later.items())) or 'not logged')
            + (f'; "hand-over:" lines on {hand}' if hand else ''))
    else:
        row(rows, 'hand-over', 'n/a', 'player 1 stayed' + (f' (but "hand-over:" on {hand})' if hand else ''))

    # final placement: the ranks of each game's last "final placement (step N): ... player P rank R" line (read
    # in full from the log; a game whose own player went out first may log only "every finalist is out" / "points
    # decide": that is shown, not compared)
    finals, notes = {}, {}
    for v in views:
        places = [ln for ln in v.lines if 'final placement (step' in ln]
        if not places:
            continue
        ranked = [ln for ln in places if R_PLACE.search(ln)]
        if ranked:
            finals[v.label] = tuple(R_PLACE.findall(ranked[-1]))
        else:
            notes[v.label] = re.sub(r'^\d\d:\d\d:\d\d final placement ', '', places[-1])[:70]
    # the host's final entries (sent by the host at step 12, logged by the host and by every game that got them)
    # are a second source: every game's placement must agree with them rank for rank, for the players both name
    entries = {}
    for v in views:
        got = [ln for ln in v.lines if R_ENTRIES.search(ln)]
        if got:
            entries[f'{v.label} host entries'] = dict(R_PLACE.findall(got[-1]))
    sources = {k: dict(val) for k, val in finals.items()}
    sources.update(entries)
    clash = set()
    for no in {p for d in sources.values() for p in d}:
        if len({d[no] for d in sources.values() if no in d}) > 1:
            clash.add(no)
    text = '; '.join([f'{k}: ' + ' '.join(f'{a}->{b}' for a, b in val) for k, val in sorted(finals.items())]
                     + [f'{k}: ' + ' '.join(f'{a}->{b}' for a, b in sorted(d.items())) for k, d in sorted(entries.items())]
                     + [f'{k}: {val}' for k, val in sorted(notes.items())])
    reached = [v.label for v in views if any('is in the final with us' in ln or 'is a finalist' in ln
                                              for ln in v.lines)]
    if clash:
        row(rows, 'final', 'FAIL', text + f' (players {sorted(clash)} ranked differently)')
    elif len(sources) >= 2 and finals:
        row(rows, 'final', 'PASS', text)
    elif finals or notes:
        row(rows, 'final', 'CHECK', text + ' (one source only)')
    elif reached:
        row(rows, 'final', 'CHECK', f'final reached on {reached}, but no placement line (the log ends in the final?)')
    else:
        row(rows, 'final', 'n/a', 'no final in this match')

    # Bloodbound pairs
    bb = {}
    for v in views:
        lines = [x for r in sorted(v.rounds) for x in v.rounds[r].bb if 'F3 data' in x]
        lines += [x for r in sorted(v.rounds) for x in v.rounds[r].final if 'Bloodbound:' in x]
        if lines:
            bb[v.label] = re.sub(r'^\d\d:\d\d:\d\d ', '', lines[-1])
    rule2 = any('Bloodbound' in str(v.meta.get('rule')) for v in views)
    if bb:
        row(rows, 'pairs', 'PASS' if len(set(bb.values())) == 1 and len(bb) >= 2 else 'CHECK',
            '; '.join(f'{k}: {val[:110]}' for k, val in sorted(bb.items())))
    else:
        row(rows, 'pairs', 'CHECK' if rule2 else 'n/a', 'Bloodbound rule but no F3 / placement line' if rule2 else 'not Bloodbound')

    # enemies driven in round 1
    meds, total = {}, None
    for v in views:
        rd = v.rounds.get(1)
        if rd and rd.drives:
            played = [d for d in rd.drives if d[3] == cutcheck.PHASE_UPDATE] or rd.drives
            meds[v.label] = statistics.median(d[0] for d in played)
            total = max(total or 0, statistics.median(d[1] for d in played))
    if meds:
        s = sum(meds.values())
        full = n is not None and len(meds) >= n
        ok = total and abs(s - total) <= max(5, 0.05 * total)
        row(rows, 'enemies r1', ('PASS' if ok else 'FAIL') if full else 'CHECK',
            f'drives {meds} sum {s:g} of {total:g}' + ('' if full else ' (not every game sent a log)'))

    # !!! lines
    bangs = {v.label: sum(1 for ln in v.lines if '!!!' in ln) for v in views}
    row(rows, '!!!', 'CHECK' if any(bangs.values()) else 'PASS', str(bangs))

    width = max(len(r[0]) for r in rows)
    for name, verdict, text in rows:
        print(f'{name:<{width}}  {verdict:<5}  {text}')
    return 1 if any(r[1] == 'FAIL' for r in rows) else 0


if __name__ == '__main__':
    sys.exit(main())
