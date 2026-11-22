r"""cutcheck.py: compare several games' dusk_lan.txt logs phase by phase (read only).

Usage (workspace):
    python diag\twin\cutcheck.py LOG1 LOG2 [LOG3 ...] [--quiet]

Each LOG is one game's dusk_lan.txt (from %APPDATA%\eden\log on a PC, or the rig's userX\log).
A name like PC2-game1:path labels it; otherwise the folder + file name is used.

Per match (counted in each log from "map: new match") and per round (1-3 = Phases I-III,
4 = final) it prints every game's view of:
  - each player's Virtue (own total sent, and the copies written for the others), and each
    game's FULL rank list with the game's own key (Virtue high first, a tie -> the lower player
    number first; ties named). Exact when the v3.9.7 F1 line carries "ranked totals"; otherwise
    filled from the owners' own totals (marked ~), because a copy is logged at its first write
    only. Also who the cut would remove (top 6 kept after Phase II, top 3 after Phase III);
  - v3.9.4 "cut check (F1)" lists (no:rank, hash) and their verdicts, when present;
  - H1 / F4 cut lines (who each game took as cut);
  - enemy owners ("this game drives X of Y (Z other player(s) here)"): the median of the
    samples logged while the phase is played (match phase 6), and the sum over the games
    (too high = driven twice, too low = driven by nobody);
  - the environment event id; the rule set; F2 / F3 Bloodbound lines; final placement lines.
Every disagreement between games is marked "!!".
At the end a "health" section per game (realnet_notes.md 3, link values over the whole log): ping range
and timer gap while a phase is played, "no side message" / Virtue "not heard for 3 s" counts, timer
corrections, network-clock moves, player-data re-requests, map waits, taken sends, v400 cut-list answers
and out-of-order drops; "HEALTH <game>: ok" or "BAD: ...". It never counts as a disagreement (the exit
code is unchanged); --no-health leaves it out. A LOG may be given as LABEL:path (A:C:/x.txt, B:diag/..).
Nothing is written; only the logs are read.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TIME = re.compile(r'^(\d\d:\d\d:\d\d) (.*)$')
ROUND = re.compile(r'\bround (\d+)')

R_ARMED = re.compile(r'player no (\d+) team (\d+) \((\d+) players\)')
R_NO = re.compile(r'player no is now (\d+)')
R_OWN_SENT = re.compile(r'virtue: our total (-?\d+) \(player (\d+), round (\d+)\)')
R_OWN_CHG = re.compile(r'virtue: our total changed (-?\d+) -> (-?\d+)')
R_COPY = re.compile(r"virtue: player (\d+)'s copy set to its game's total: banked (-?\d+) -> (-?\d+)")
R_NOTHEARD = re.compile(r"virtue: player (\d+)'s total (-?\d+) not heard")
R_COMMEND = re.compile(r"commend: player (\d+)'s (\w+) set (-?\d+) -> (-?\d+)")
R_CUTLIST = re.compile(r'cut check \(F1\): round (\d+) step (\d+): our list \(no:rank(:team)?\)(.*?) hash ([0-9a-f]{8});.*?(we are the authority|compared with)')
R_CUTSAME = re.compile(r'cut check \(F1\): round (\d+): same list as the authority \(player (\d+)\)')
R_CUTMISS = re.compile(r'CUT MISMATCH \(F1\) round (\d+)')
R_CUTNONE = re.compile(r'cut check \(F1\): round (\d+): no authority list heard')
R_CUTRULE = re.compile(r'cut check \(F1\): round (\d+): player (\d+) plays rule')
R_H1CUT = re.compile(r'H1: player (\d+) is cut')
R_H1OWN = re.compile(r'H1: our player \(no (\d+)\) is cut')
R_H1BACK = re.compile(r'H1: player (\d+) is in a match step again')
R_H1OWNBACK = re.compile(r'H1: our player \(no (\d+)\) is no longer')
R_F4CHR = re.compile(r'enemies: player (\d+) is cut: its (chr|enemy claims)')
R_F4OWN = re.compile(r'enemies: our player is cut')
R_DRIVES = re.compile(r'enemies: this game drives (\d+) of (\d+) \((\d+) other player')
R_ENV_HERE = re.compile(r'environment event (\d+) drawn here \(round (\d+)\)')
R_ENV_FROM = re.compile(r'environment event (\d+) from player (\d+) \(round (\d+)\)')
R_RULE = re.compile(r'rule set: this match reaches MatchPreprocess with (.+?)\s*$')
R_FINAL = re.compile(r'final placement')
R_BB = re.compile(r'bloodbound \(F[23]')
R_NEWMATCH = re.compile(r'map: new match')
R_PHASE = re.compile(r'match phase (\d+)')
R_RANKED = re.compile(r'ranked totals((?: \d+=(?:\d+|\?))+)')
PHASE_UPDATE = 6          # UpdatePhase: the phase is being played
R_SESSION = re.compile(r'joined a LAN session')


class Round:
    def __init__(self):
        self.virtue = {}          # player -> last Virtue total seen on this game
        self.own = {}             # this game's own player -> its total (its own report)
        self.ranked = {}          # v3.9.7 F1 line: player -> total the game ranked with (None = ?)
        self.commend = {}         # (player, part) -> value
        self.cutlists = []        # (step, entries [(no, rank, team)], hash, role)
        self.verdicts = []        # text
        self.cut = set()          # players this game took as cut (H1 / F4)
        self.cut_lines = []
        self.drives = []          # (owned, total, others, match phase when logged)
        self.env = None           # (id, source)
        self.final = []
        self.bb = []


class Game:
    def __init__(self, label, path):
        self.label, self.path = label, path
        self.no = None
        self.players = None
        self.matches = []          # list of dict: round -> Round, plus meta
        self.meta = []             # per match: start time, rule

    def rnd(self, match, r):
        while len(self.matches) <= match:
            self.matches.append(defaultdict(Round))
            self.meta.append({'start': '?', 'rule': None, 'no': self.no, 'players': self.players})
        return self.matches[match][r]


def parse(label, path):
    g = Game(label, path)
    match, cur, rule, phase = -1, 0, None, None
    day, last_sec = 0, None
    text = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    for line in text:
        m = TIME.match(line)
        if not m:
            continue
        t, s = m.groups()
        hh, mm, ss = (int(x) for x in t.split(':'))
        sec = hh * 3600 + mm * 60 + ss
        if last_sec is not None and sec + 43200 < last_sec:
            day += 86400             # the log went past midnight
        last_sec = sec
        sec += day
        m = R_PHASE.search(s)
        if m:
            phase = int(m[1])
        if R_SESSION.search(s):
            pass
        m = R_ARMED.search(s)
        if m:
            g.no, g.players = int(m[1]), int(m[3])
        m = R_NO.search(s)
        if m:
            g.no = int(m[1])
        if R_NEWMATCH.search(s):
            match += 1
            cur = 1
            g.rnd(match, 1)
            g.meta[match].update(start=t, no=g.no, players=g.players, rule=rule)
            rule = None
            continue
        m = R_RULE.search(s)
        if m:
            if match >= 0 and g.meta[match]['rule'] is None:
                g.meta[match]['rule'] = m[1]
            else:
                rule = m[1]          # logged before the match's "new match" line
        if match < 0:
            continue
        rm = ROUND.search(s)
        if rm and 1 <= int(rm[1]) <= 4:
            cur = int(rm[1])
        rd = g.rnd(match, cur)
        if g.meta[match]['no'] is None:
            g.meta[match]['no'] = g.no
        m = R_OWN_SENT.search(s)
        if m:
            own_rd = g.rnd(match, int(m[3]))
            own_rd.virtue[int(m[2])] = int(m[1])
            own_rd.own[int(m[2])] = int(m[1])
            continue
        m = R_OWN_CHG.search(s)
        if m and g.no is not None:
            rd.virtue[g.no] = int(m[2])
            rd.own[g.no] = int(m[2])
            continue
        m = R_COPY.search(s)
        if m:
            rd.virtue[int(m[1])] = int(m[3])
            continue
        m = R_NOTHEARD.search(s)
        if m:
            rd.virtue.setdefault(int(m[1]), int(m[2]))
            continue
        m = R_COMMEND.search(s)
        if m:
            rd.commend[(int(m[1]), m[2])] = int(m[4])
            continue
        m = R_CUTLIST.search(s)
        if m:
            entries = []
            for tok in m[4].split():
                parts = tok.split(':')
                if len(parts) >= 2 and parts[0].isdigit():
                    team = int(parts[2][1:]) if len(parts) > 2 and parts[2][1:].isdigit() else None
                    entries.append((int(parts[0]), int(parts[1]), team))
            role = 'authority' if m[6].startswith('we are') else 'follower'
            g.rnd(match, int(m[1])).cutlists.append((int(m[2]), entries, m[5], role))
            mr = R_RANKED.search(s)
            if mr:
                for tok in mr[1].split():
                    no, val = tok.split('=')
                    g.rnd(match, int(m[1])).ranked[int(no)] = None if val == '?' else int(val)
            continue
        for rx, word in ((R_CUTSAME, 'same as authority'), (R_CUTMISS, '!! CUT MISMATCH'),
                         (R_CUTNONE, 'no authority list heard'), (R_CUTRULE, '!! rule differs')):
            m = rx.search(s)
            if m:
                g.rnd(match, int(m[1])).verdicts.append(f'{t} {word}')
                break
        else:
            m = R_H1CUT.search(s) or R_H1OWN.search(s)
            if m:
                rd.cut.add(int(m[1]))
                rd.cut_lines.append(f'{t} H1 cut {m[1]}')
                continue
            m = R_H1BACK.search(s) or R_H1OWNBACK.search(s)
            if m:
                rd.cut.discard(int(m[1]))
                rd.cut_lines.append(f'{t} H1 back {m[1]}')
                continue
            m = R_F4CHR.search(s)
            if m:
                rd.cut.add(int(m[1]))
                rd.cut_lines.append(f'{t} F4 {m[1]} ({m[2]})')
                continue
            if R_F4OWN.search(s):
                if g.no is not None:
                    rd.cut.add(g.no)
                rd.cut_lines.append(f'{t} F4 our player cut')
                continue
            m = R_DRIVES.search(s)
            if m:
                rd.drives.append((int(m[1]), int(m[2]), int(m[3]), phase, sec))
                continue
            m = R_ENV_HERE.search(s)
            if m:
                g.rnd(match, int(m[2])).env = (int(m[1]), 'drawn here')
                continue
            m = R_ENV_FROM.search(s)
            if m:
                g.rnd(match, int(m[3])).env = (int(m[1]), f'from player {m[2]}')
                continue
            if R_FINAL.search(s):
                rd.final.append(f'{t} {s[:150]}')
            elif R_BB.search(s):
                rd.bb.append(f'{t} {s[:150]}')
    return g


def ranks(virtue):
    """The game's own key (rank record 0xF88D60 with VIRTUE_TIEBREAK, tiebreak_notes.md 1):
    Virtue high first, equal Virtue -> lower player number first. Every rank is unique."""
    order = sorted(virtue.items(), key=lambda kv: (-kv[1], kv[0]))
    return {no: i for i, (no, _) in enumerate(order, 1)}


def ties(virtue):
    """[(total, [players])] for every total held by two or more players."""
    by = defaultdict(list)
    for no, v in virtue.items():
        by[v].append(no)
    return sorted(((v, sorted(nos)) for v, nos in by.items() if len(nos) > 1), key=lambda x: -x[0])


def rank_text(virtue, filled=()):
    """'1:1(6) 2:2(0) 3:3(~0)': no:rank(Virtue); ~ = not logged on this game, its owner's total."""
    rk = ranks(virtue)
    return ' '.join(f'{no}:{r}({"~" if no in filled else ""}{virtue[no]})'
                    for no, r in sorted(rk.items(), key=lambda kv: kv[1]))


def expected_cut(virtue, rnd, players):
    """Who the cut after this round removes, from this Virtue view (None = no cut here), and
    whether the cut line falls inside a tie (then the player number decides)."""
    keep = {2: 6, 3: 3}.get(rnd)
    n = players or len(virtue)
    if keep is None or n <= keep or n <= 2 or len(virtue) < n:
        return None, False
    rk = ranks(virtue)
    cut = sorted(no for no, r in rk.items() if r > keep)
    by_rank = {r: no for no, r in rk.items()}
    tie = keep + 1 in by_rank and virtue[by_rank[keep]] == virtue[by_rank[keep + 1]]
    return cut, tie


def fmt_map(d):
    return ' '.join(f'{k}={v}' for k, v in sorted(d.items())) or '-'


def main(argv):
    quiet = '--quiet' in argv
    args = [a for a in argv if not a.startswith('--')]
    if len(args) < 1:
        print(__doc__)
        return 2
    games = []
    for a in args:
        # LABEL:path; a drive path (C:/x, C:\\x) has a slash right after its colon (C:diag/.. = label C)
        if re.match(r'^[^:\\/]+:(?![\\/])', a) or (':' in a and not re.match(r'^[A-Za-z]:[\\/]', a)
                                                       and not Path(a).exists()):
            label, path = a.split(':', 1)
        else:
            p = Path(a)
            label, path = f'{p.parent.name}/{p.name}', a
        games.append(parse(label, path))
    flags = 0
    print('games:')
    for g in games:
        print(f'  {g.label}: player {g.no}, {g.players} players, {len(g.matches)} match(es) '
              f'(starts {", ".join(m["start"] for m in g.meta) or "-"})')
    counts = {len(g.matches) for g in games}
    if len(counts) > 1:
        print('!! the logs hold different numbers of matches: matches are paired by order; '
              'check the start times above')
        flags += 1
    for mi in range(max(len(g.matches) for g in games)):
        here = [g for g in games if mi < len(g.matches)]
        print(f'\n=== match {mi + 1} ===')
        rules = {g.label: g.meta[mi]['rule'] for g in here}
        print('  rule set: ' + ', '.join(f'{k} {v}' for k, v in rules.items()))
        if len({v for v in rules.values() if v}) > 1:
            print('  !! the games play different rule sets')
            flags += 1
        nos = Counter(g.meta[mi]['no'] for g in here)
        dup = [no for no, c in nos.items() if no is not None and c > 1]
        if dup:
            print(f'  !! the same player number on several games: {dup} (F5)')
            flags += 1
        players = max((g.meta[mi]['players'] or 0) for g in here) or None
        rounds = sorted({r for g in here for r in g.matches[mi]})
        for g in here:              # Virtue is banked over the match: a round starts from the last
            prev, prev_own = {}, {}
            for r in range(1, max(rounds) + 1):
                rd = g.matches[mi][r]
                rd.virtue = {**prev, **rd.virtue}
                rd.own = {**prev_own, **rd.own}
                prev, prev_own = rd.virtue, rd.own
        # The owners' own totals (each game's report of its own player) are the truth a full
        # list is filled from: a game logs a copy only at its FIRST write of the match, and never
        # when the copy already held the total (a player at 0 is never logged on the others).
        all_nos = sorted({g.meta[mi]['no'] for g in here if g.meta[mi]['no'] is not None})
        for r in rounds:
            name = {1: 'Phase I', 2: 'Phase II', 3: 'Phase III', 4: 'final'}.get(r, f'round {r}')
            print(f'\n  --- round {r} ({name}) ---')
            views = {}
            truth = {}
            for g in here:
                truth.update(g.matches[mi][r].own)
            exact = {}                  # label -> the totals the game itself ranked with (v3.9.7)
            for g in here:
                rd = g.matches[mi][r]
                views[g.label] = rd
                nos = sorted(set(all_nos) | set(rd.virtue) | set(truth))
                if rd.ranked and all(v is not None for v in rd.ranked.values()):
                    full, filled, src = dict(rd.ranked), (), 'as ranked by the game (F1 line)'
                    exact[g.label] = full
                else:
                    full, filled = {}, set()
                    for p in nos:
                        if p in truth:
                            full[p] = truth[p]
                            if rd.virtue.get(p) != truth[p]:
                                filled.add(p)
                        elif p in rd.virtue:
                            full[p] = rd.virtue[p]
                    src = 'from the logs (~ = its owner\'s own total, not logged here)'
                cut, tie = expected_cut(full, r, players)
                line = f'    {g.label:<24} Virtue logged here {fmt_map(rd.virtue)}'
                if cut is not None:
                    line += f'   cut by Virtue: {cut or "nobody"}' + \
                            ('  (tie at the cut line: the lower player number stays)' if tie else '')
                print(line)
                if full:
                    tie_txt = '; '.join(f'tie at {v}: {",".join(map(str, p))} (lower number first)'
                                        for v, p in ties(full))
                    print(f'      rank list {src}: {rank_text(full, filled)}'
                          + (f'   [{tie_txt}]' if tie_txt else ''))
                for step, entries, h, role in rd.cutlists:
                    lst = ' '.join(f'{n}:{k}' + (f':t{t}' if t is not None else '') for n, k, t in entries)
                    print(f'      F1 list step {step} ({role}): {lst or "none"}  hash {h}')
                for v in rd.verdicts:
                    print(f'      F1 {v}')
                    if '!!' in v:
                        flags += 1
                if rd.cut_lines and not quiet:
                    print('      cut lines: ' + '; '.join(rd.cut_lines))
                if rd.commend and not quiet:
                    print('      commend: ' + ' '.join(f'{p}.{k}={v}' for (p, k), v in sorted(rd.commend.items())))
                for x in (rd.bb + rd.final)[: (3 if quiet else 12)]:
                    print(f'      {x}')
            # Virtue agreement. Logged copy values are only first writes (stale later), so a
            # difference there is a note; the totals the games ranked with (v3.9.7 F1 line) and the
            # F1 rank lists are what count.
            allp = sorted({p for rd in views.values() for p in rd.virtue})
            for p in allp:
                vals = {lab: rd.virtue[p] for lab, rd in views.items() if p in rd.virtue}
                if len(set(vals.values())) > 1:
                    print(f'    (note) player {p} Virtue as last logged: ' +
                          ', '.join(f'{k} {v}' for k, v in vals.items()) +
                          ' (a copy is logged at its first write only)')
            if len(exact) > 1:
                shapes = {lab: tuple(sorted(v.items())) for lab, v in exact.items()}
                if len(set(shapes.values())) > 1:
                    print('    !! the games ranked with different Virtue totals: ' +
                          ', '.join(f'{k} {fmt_map(v)}' for k, v in exact.items()))
                    flags += 1
                rks = {lab: tuple(sorted(ranks(v).items())) for lab, v in exact.items()}
                if len(set(rks.values())) > 1:
                    print('    !! the games rank the players differently (from the totals they ranked with)')
                    flags += 1
                cuts = {lab: tuple(expected_cut(v, r, players)[0] or ()) for lab, v in exact.items()
                        if expected_cut(v, r, players)[0] is not None}
                if len(set(cuts.values())) > 1:
                    print('    !! the games would cut different players: ' +
                          ', '.join(f'{k} {list(v)}' for k, v in cuts.items()))
                    flags += 1
            # F1 lists: compare the last list of every game that logged one.
            lists = {lab: rd.cutlists[-1] for lab, rd in views.items() if rd.cutlists}
            if len(lists) > 1:
                shapes = {lab: tuple(sorted((n, k, t) for n, k, t in e)) for lab, (_, e, _, _) in lists.items()}
                if len(set(shapes.values())) > 1:
                    print('    !! F1 lists differ between games: ' +
                          ', '.join(f'{k} {lists[k][2]}' for k in lists))
                    flags += 1
                else:
                    print(f'    F1 lists agree on {len(lists)} games (hash {next(iter(lists.values()))[2]})')
            # H1 / F4: who was taken as cut.
            seen_cut = {lab: tuple(sorted(rd.cut)) for lab, rd in views.items()}
            if any(seen_cut.values()):
                print('    taken as cut: ' + ', '.join(f'{k} {list(v)}' for k, v in seen_cut.items()))
                if len(set(seen_cut.values())) > 1:
                    print('    !! the games took different players as cut (a cut game may stop logging: '
                          'check its own line)')
                    flags += 1
            # Enemy owners: per game the most common total and "others" count of the round, and
            # the median owned count of the samples with that total (the games log at different
            # moments, so single samples do not line up).
            # Only samples logged while the phase is played (UpdatePhase, match phase 6) count:
            # between phases (results, loading the next map) the players' chrs jump and stop
            # sending, and the line is written only when the count changes (10 s apart at most).
            summ = {}
            skipped = {}
            for lab, rd in views.items():
                play = [x for x in rd.drives if x[3] == PHASE_UPDATE]
                if len(play) < len(rd.drives):
                    skipped[lab] = len(rd.drives) - len(play)
                if not play:
                    continue
                t = Counter(x[1] for x in play).most_common(1)[0][0]
                z = Counter(x[2] for x in play).most_common(1)[0][0]
                owned = sorted(x[0] for x in play if x[1] == t)
                summ[lab] = (owned[len(owned) // 2], t, z, len(play), owned[0], owned[-1])
            if skipped:
                print('    enemies: samples outside play left out: ' +
                      ', '.join(f'{k} {n}' for k, n in skipped.items()))
            if not summ and skipped:
                print('    enemies: no sample while this phase was played (the line is logged only when '
                      'the count changes): no owner sum')
            if summ:
                parts = ', '.join(f'{k} {o}/{t} (range {lo}-{hi}, {z} others, {n} samples)'
                                  for k, (o, t, z, n, lo, hi) in summ.items())
                print(f'    enemies in play (median owned / usual total): {parts}')
                tots = {v[1] for v in summ.values()}
                owned = sum(v[0] for v in summ.values())
                # Every player's game must be here (each game sees `others` other players).
                complete = len(summ) == len(here) and all(v[2] == len(here) - 1 for v in summ.values())
                if not complete:
                    print(f'    (enemy owners: not every player\'s log is given here; no sum)')
                # Sums at the same moments: a game's count holds from its line to its next one
                # (lines come only on a change, 10 s apart at most), so at each sample time take
                # every game's last in-play sample of this round with the same total.
                if complete and len(tots) == 1:
                    total = next(iter(tots))
                    series = {lab: sorted((x[4], x[0]) for x in rd.drives
                                          if x[3] == PHASE_UPDATE and x[1] == total)
                              for lab, rd in views.items()}
                    moments = sorted({ts for ser in series.values() for ts, _ in ser})
                    sums = []
                    for ts in moments:
                        now_vals = [next((o for t2, o in reversed(ser) if t2 <= ts), None)
                                    for ser in series.values()]
                        if all(v is not None for v in now_vals):
                            sums.append(sum(now_vals))
                    if sums:
                        sums.sort()
                        owned = sums[len(sums) // 2]
                        print(f'    owner sum at the same moments: {sums[0]}-{sums[-1]}, median {owned} '
                              f'of {total} ({len(sums)} moments)')
                if len(tots) > 1:
                    print(f'    !! the games count different enemy totals: {sorted(tots)}')
                    flags += 1
                elif complete and owned > next(iter(tots)) * 1.05 + 2:
                    print(f'    !! about {owned} owners for {next(iter(tots))} enemies: some enemies are driven twice')
                    flags += 1
                elif complete and owned < next(iter(tots)) * 0.9 - 2:
                    print(f'    !! owner sum {owned} of {next(iter(tots))}: about '
                          f'{next(iter(tots)) - owned} enemies driven by nobody (they stand still)')
                    flags += 1
                elif complete:
                    print(f'    owner sum {owned} of {next(iter(tots))}: every enemy driven once')
                zs = {v[2] for v in summ.values()}
                if len(zs) > 1:
                    print(f'    !! the games usually see different numbers of other players: {sorted(zs)} (cut, gone, or a missing chr)')
                    flags += 1
            # Environment event.
            envs = {lab: rd.env for lab, rd in views.items() if rd.env}
            if envs:
                print('    environment event: ' + ', '.join(f'{k} {v[0]} ({v[1]})' for k, v in envs.items()))
                if len({v[0] for v in envs.values()}) > 1:
                    print('    !! the games run different environment events')
                    flags += 1
                missing = [lab for lab in views if lab not in envs]
                if missing and r in (2, 3):
                    print(f'    (no event line on: {", ".join(missing)})')
    if '--no-health' not in argv:
        print_health(games)
    print(f'\n{flags} disagreement(s) flagged.')
    return 1 if flags else 0


# ------------------------------------------------------------------ link health (realnet_notes.md 3)
# Read only, per game, over the whole log. Never counted in "disagreement(s) flagged" (the exit code
# stays the cut / rank verdict); a value past a realnet_notes.md 3 limit is marked BAD.
H_PING = re.compile(r'peer player (\d+): ping (\d+|\?) ms, match timer gap ([+-]?\d+\.\d+) s')
H_SILENT = re.compile(r'peer player (\d+): no side message for (\d+) s')
H_TIMER = re.compile(r"match timer set to player (\d+)'s: (-?[\d.]+) -> (-?[\d.]+) s \(correction #(\d+)\)")
H_NETCLK = re.compile(r'network clock moved ([+-]?[\d.]+) s forward')
H_NOTHEARD = re.compile(r"virtue: player (\d+)'s total -?\d+ not heard")
H_REREQ = re.compile(r'player data asked for again \(#(\d+)\)')
H_MAPWAIT = re.compile(r'map: no lists from the host for round (\d+)')
H_MAPIN = re.compile(r'map: round (\d+) lists from the host are in')
H_TAKEN_OUT = re.compile(r'^taken: .*; sent to the others \(x(\d+)')
H_TAKEN_IN = re.compile(r'^taken: .* from player \d+ \(round \d+\)')
H_V400_ACK = re.compile(r'cut check \(V400-1\): round (\d+): (every listed player has our list|!!! not every listed player answered in 10 s) after (\d+) send\(s\), ([\d.]+) s')
H_V400_EARLY = re.compile(r'cut check \(V400-1\): round \d+: the authority.s list .* came before our own cut step')
H_V400_HASH = re.compile(r'cut check \(V400-1\): round \d+: player \d+ answered with hash')
H_V400_OLD = re.compile(r'side channel: (\d+) type-1 message\(s\) came out of order')
H_DUP = re.compile(r'DUPLICATE PLAYER NUMBER')
H_CUTMISS = re.compile(r'CUT MISMATCH \(F1\)')
H_CUTNONE = re.compile(r'cut check \(F1\): round \d+: no authority list heard')


def health_of(path):
    """One game's link-health values from its dusk_lan.txt (dict)."""
    h = dict(pings=[], ping_unknown=0, gaps=[], gap_runs=0, silent_play=0, silent_other=0,
             silent_max=0, corr_max=0, corr_big=0, corr_late=0, netclk=[], first=None, last=None,
             notheard_play=0, notheard_other=0, rereq_max=0, map_wait=0, map_in=0, taken_out=0,
             taken_x=Counter(), taken_in=0, acks=[], ack_missing=0, early=0, ack_hash=0,
             old_dropped=0, dup=0, cutmiss=0, cutnone=0, ping_outside=0)
    phase, prev_big = None, {}
    day, last_sec = 0, None
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        m = TIME.match(line)
        if not m:
            continue
        t, s = m.groups()
        hh, mm, ss = (int(x) for x in t.split(':'))
        sec = hh * 3600 + mm * 60 + ss
        if last_sec is not None and sec + 43200 < last_sec:
            day += 86400
        last_sec = sec
        sec += day
        h['first'] = sec if h['first'] is None else h['first']
        h['last'] = sec
        m = R_PHASE.search(s)
        if m:
            phase = int(m[1])
        play = phase == PHASE_UPDATE
        if (m := H_PING.search(s)):
            if not play:
                h['ping_outside'] += 1          # between phases / in the hub the gap means nothing
                continue
            if m[2] == '?':
                h['ping_unknown'] += 1
            else:
                h['pings'].append(int(m[2]))
            gap = abs(float(m[3]))
            h['gaps'].append(gap)
            big = gap >= 0.25
            if big and prev_big.get(m[1]):
                h['gap_runs'] += 1             # |gap| >= 0.25 s twice in a row for one peer
            prev_big[m[1]] = big
        elif (m := H_SILENT.search(s)):
            h['silent_play' if play else 'silent_other'] += 1
            h['silent_max'] = max(h['silent_max'], int(m[2]))
        elif (m := H_TIMER.search(s)):
            n = int(m[4])
            h['corr_max'] = max(h['corr_max'], n)   # only #1-3 and every 20th are logged
            if abs(float(m[2]) - float(m[3])) >= 1.0:
                h['corr_big'] += 1
            if n > 20:
                h['corr_late'] += 1
        elif (m := H_NETCLK.search(s)):
            h['netclk'].append((sec, float(m[1])))
        elif H_NOTHEARD.search(s):
            h['notheard_play' if play else 'notheard_other'] += 1
        elif (m := H_REREQ.search(s)):
            h['rereq_max'] = max(h['rereq_max'], int(m[1]))
        elif H_MAPWAIT.search(s):
            h['map_wait'] += 1
        elif H_MAPIN.search(s):
            h['map_in'] += 1
        elif (m := H_TAKEN_OUT.search(s)):
            h['taken_out'] += 1
            h['taken_x'][int(m[1])] += 1
        elif H_TAKEN_IN.search(s):
            h['taken_in'] += 1
        elif (m := H_V400_ACK.search(s)):
            h['acks'].append((int(m[1]), int(m[3]), float(m[4])))
            if m[2].startswith('!!!'):
                h['ack_missing'] += 1
        elif H_V400_EARLY.search(s):
            h['early'] += 1
        elif H_V400_HASH.search(s):
            h['ack_hash'] += 1
        elif (m := H_V400_OLD.search(s)):
            h['old_dropped'] += int(m[1])
        if H_DUP.search(s):
            h['dup'] += 1
        if H_CUTMISS.search(s):
            h['cutmiss'] += 1
        if H_CUTNONE.search(s):
            h['cutnone'] += 1
    return h


def health_lines(h):
    """(text lines, bad reasons) for one game."""
    lines, bad = [], []
    p = sorted(h['pings'])
    if p:
        unknown = ', %d unknown' % h['ping_unknown'] if h['ping_unknown'] else ''
        lines.append(f'ping {p[0]}-{p[-1]} ms (median {p[len(p) // 2]}, p95 {p[min(len(p) - 1, int(len(p) * 0.95))]}, '
                     f'{len(p)} samples){unknown}')
        # 2026-11-17: a high ping alone is never BAD (with the simulator it is the simulated delay, on a real
        # link it is the link): reported only. BAD = lost-message symptoms (unanswered pings, silences, ...).
        if p[-1] > 60:
            lines.append(f'ping note: up to {p[-1]} ms (> 60): reported only, not a fault (a simulated or real '
                         f'delay)')
    else:
        lines.append(f'ping: no sample ({h["ping_unknown"]} unknown)')
    if h['ping_unknown'] and p:
        bad.append(f'ping "?" {h["ping_unknown"]} time(s)')
    if h['gaps']:
        lines.append(f'match timer gap max {max(h["gaps"]):.2f} s, >= 0.25 s in {sum(g >= 0.25 for g in h["gaps"])} '
                     f'of {len(h["gaps"])} samples, twice in a row {h["gap_runs"]}')
    lines.append(f'"no side message" lines: {h["silent_play"]} while a phase was played, {h["silent_other"]} '
                 f'elsewhere (longest {h["silent_max"]} s)')
    if h['silent_play']:
        bad.append(f'{h["silent_play"]} side-channel silence(s) during play')
    lines.append(f'"not heard for 3 s" (Virtue) lines: {h["notheard_play"]} in play, {h["notheard_other"]} elsewhere')
    if h['notheard_play']:
        bad.append(f'{h["notheard_play"]} Virtue copy(ies) not heard for 3 s in play')
    lines.append(f'match timer corrections: highest #{h["corr_max"]} (only #1-3 and every 20th are logged), '
                 f'{h["corr_big"]} logged with a jump >= 1 s')
    if h['corr_big']:
        bad.append(f'{h["corr_big"]} match timer jump(s) of 1 s or more (stale burst, R6)')
    span = max(1, (h['last'] or 0) - (h['first'] or 0))
    nc = h['netclk']
    lines.append(f'network clock moves: {len(nc)}' +
                 (f' ({", ".join(f"{v:+.3f}" for _, v in nc[:8])}{" ..." if len(nc) > 8 else ""})' if nc else '') +
                 f' in {span / 60:.0f} min of log')
    late = [v for sec, v in nc if sec - (h['first'] or 0) > 300 and v >= 0.25]
    if late:
        bad.append(f'{len(late)} network clock move(s) of 0.25 s or more after the first 5 min')
    lines.append(f'player data asked again: highest #{h["rereq_max"]}; map waits {h["map_wait"]}, '
                 f'map sets in {h["map_in"]}')
    if h['rereq_max'] >= 3:
        bad.append(f'player data asked again #{h["rereq_max"]}')
    if h['map_wait']:
        bad.append(f'{h["map_wait"]} map wait(s) for the host\'s lists')
    xs = ', '.join(f'x{k} {v}' for k, v in sorted(h['taken_x'].items()))
    lines.append(f'taken: {h["taken_out"]} change(s) sent ({xs or "-"}), {h["taken_in"]} applied from others')
    if h['acks'] or h['ack_missing'] or h['early'] or h['old_dropped']:
        a = ', '.join(f'round {r}: {n} send(s) {t:.1f} s' for r, n, t in h['acks'])
        lines.append(f'v400: cut-list answers {a or "-"}; not all answered {h["ack_missing"]}; '
                     f'list before our cut {h["early"]}; answer hash differs {h["ack_hash"]}; '
                     f'type-1 out of order dropped {h["old_dropped"]}')
        if h['ack_missing'] or h['ack_hash']:
            bad.append(f'cut list not answered by all ({h["ack_missing"]}) / damaged ({h["ack_hash"]})')
    else:
        lines.append('v400: no V400 line (an older build, or nothing to report)')
    if h['dup']:
        bad.append(f'DUPLICATE PLAYER NUMBER x{h["dup"]}')
    if h['cutmiss']:
        bad.append(f'CUT MISMATCH x{h["cutmiss"]}')
    if h['cutnone']:
        bad.append(f'no authority cut list heard x{h["cutnone"]}')
    return lines, bad


def print_health(games):
    print('\n=== health (link values, realnet_notes.md 3; not counted as disagreements) ===')
    print('  ping / timer gap: only samples logged while this game played a phase (step 6). Timer')
    print('  corrections and small network-clock moves happen on one PC too: compare with a clean run.')
    for g in games:
        lines, bad = health_lines(health_of(g.path))
        print(f'  {g.label}:')
        for x in lines:
            print(f'    {x}')
        print(f'    HEALTH {g.label}: ' + ('BAD: ' + '; '.join(bad) if bad else 'ok'))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
