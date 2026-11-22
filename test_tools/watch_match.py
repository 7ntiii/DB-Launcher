r"""watch_match.py: READ-ONLY live monitor of a 2-8 player match, seen from this PC's two rig games (A, B).
Written 2026-11-17 (static; not run yet). The other players are people on their own PCs: everything about them
here is what OUR two games hold (memory) or log (dusk_lan.txt).

Usage (workspace root):
    python diag/twin/pkgtest.py run diag/twin/watch_match.py [SECONDS=3600] [GAMES=AB] [--every 5]
    python diag/twin/watch_match.py ...       (plain rig: lanlog's default paths)
    python diag/twin/watch_match.py --replay A:LOG1 B:LOG2 [--every 60]
                                              (offline: the log part of the blocks, every 60 s of log time;
                                               no memory, so players = the numbers the log names)

Every 5 s one compact block:
  per game   step / round, clock (phase seconds left), role byte (0 = host), rule byte, own player number,
             authority line of the log, timer corrections (count + last), network clock moves
  players    every player number our game holds (PlayerGameData pool): state word pgd+0x46B0, banked Virtue
             s16 pgd+0x42C8, the live Virtue total of the log (owner's own report or the mirror copy) and
             alive / OUT / CUT / LEFT? (CUT = H1 / F4 line this match; OUT = state word byte 0 >= 4;
             LEFT? = held earlier in this match, gone from our pool now)
  cuts       per round as it is decided: each game's last F1 list (no:rank) + hash + role and the H1 / F4 cut
             set; A vs B: EQUAL / DIFFER (only games that have a list for that round are compared)
  pairs      Bloodbound box main+0xC50F210 (state, pairs) when the rule byte is 2
  enemies    each game's last "this game drives X of Y (Z other players here)"
  !!!        every new "!!!" line of either dusk_lan.txt since the last block
A culled game (Outcome steps, its par gone) or a closed one (debug server down) is shown as such and polled
again next block; the monitor never stops for it. Memory: only read_memory calls (dbg.Dbg); logs: read only.
"""
import os
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lanlog            # noqa: E402  (pkgtest.py run has already pointed lanlog.LAN at the pkgtest games)
import cutcheck          # noqa: E402

PAR = 0x5B3CDF8
GDM = 0x5B57EB8
ROLE = 0x492AFD8
RULE = 0x5B65C70
BB_BOX = 0xC50F210
POOL_SIZE, POOL_N = 0x47F0, 12
NONE = 0xFFFFFFFF
RULES = {0: 'Standard', 1: 'No Alliances', 2: 'Bloodbound'}
OUTCOME = range(29, 37)


def arg(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        val = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return val
    return default


class Game:
    """One rig game: a kept-open debug-server connection (re-opened when it drops) and a log tail."""

    def __init__(self, who):
        self.who = who
        self.dbg = None
        self.offset = 0          # log bytes already scanned for '!!!'
        self.seen = set()        # player numbers held this match (for LEFT?)
        self.match_key = None

    def connect(self):
        if self.dbg is None:
            from dbg import Dbg
            self.dbg = Dbg(self.who)
        return self.dbg

    def drop(self):
        try:
            self.dbg.sock.close()
        except Exception:
            pass
        self.dbg = None

    def u32(self, a):
        return struct.unpack('<I', self.dbg.read(a, 4))[0]

    def u64(self, a):
        return self.dbg.u64(a)

    def snapshot(self):
        """Memory facts; {'err': text} when the game cannot be read."""
        try:
            d = self.connect()
            b = d.base
        except Exception as e:  # game closed / debug server not up / no main base yet
            self.dbg = None
            return {'err': f'not reachable ({str(e)[:60]})'}
        out = {}
        try:
            out['role'] = d.read(b + ROLE, 1)[0]
            out['rule'] = d.read(b + RULE, 1)[0]
            par = self.u64(b + PAR)
            if par:
                out['step'], out['round'] = self.u32(par + 0x50), self.u32(par + 0xB8)
                clk = self.u64(par + 0x120)
                if clk:
                    out['clock'] = struct.unpack('<f', d.read(clk + 8, 4))[0]
            gdm = self.u64(b + GDM)
            players = {}
            if gdm:
                head = d.read(gdm, 0x38)
                local = struct.unpack_from('<Q', head, 0x20)[0]
                pool = struct.unpack_from('<Q', head, 0x30)[0]
                cand = [struct.unpack_from('<Q', head, o)[0] for o in (0x08, 0x10, 0x20, 0x28)]
                if pool:
                    cand += [pool + i * POOL_SIZE for i in range(POOL_N)]
                done = set()
                for p in cand:
                    if not p or p in done:
                        continue
                    done.add(p)
                    try:
                        no = self.u32(p + 0xD0)
                        if no == NONE or no == 0 or no > 16:
                            continue
                        state = d.read(p + 0x46B0, 4)
                        banked = struct.unpack('<h', d.read(p + 0x42C8, 2))[0]
                    except Exception:
                        continue
                    players[no] = (state, banked)
                    if p == local:
                        out['own'] = no
            out['players'] = players
            if out.get('rule') == 2:
                box = d.read(b + BB_BOX, 12)
                k = box[1]
                out['bb'] = (box[0], [(box[2 + 2 * i], box[3 + 2 * i]) for i in range(min(k, 5))])
        except Exception as e:
            self.drop()
            out['err'] = f'read failed ({str(e)[:60]})'
        return out

    def new_bangs(self):
        path = lanlog.LAN[self.who]
        try:
            size = os.path.getsize(path)
            if size < self.offset:            # a new log (the game was restarted)
                self.offset = 0
            with open(path, 'rb') as f:
                f.seek(self.offset)
                data = f.read()
            self.offset = size
        except OSError:
            return []
        return [ln for ln in data.decode('utf-8', 'replace').splitlines() if '!!!' in ln]


def log_facts(who):
    """What the log says, for the last match: authority, corrections, cut lists, drives, live Virtue."""
    path = lanlog.LAN[who]
    facts = {'auth': '?', 'timer': (0, ''), 'netclock': 0, 'game': None, 'match': -1}
    try:
        text = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return facts
    for ln in text:
        s = ln[9:] if len(ln) > 9 else ln
        if s.startswith('authority (spawners, items, levers, events):'):
            facts['auth'] = 'this game' if s.endswith('this game') else 'a player before us'
        elif s.startswith('map: new match'):
            facts['timer'], facts['netclock'] = (0, ''), 0
        elif 'match timer set to player' in s:
            facts['timer'] = (facts['timer'][0] + 1, s[:90])
        elif s.startswith('network clock moved'):
            facts['netclock'] += 1
    try:
        g = cutcheck.parse(who, path)
    except Exception:
        return facts
    facts['game'] = g
    facts['match'] = len(g.matches) - 1
    return facts


def status(no, state, cut, gone):
    if no in cut:
        return 'CUT'
    if gone:
        return 'LEFT?'
    if state and state[0] >= 4:
        return 'OUT'
    if state and state[0] == 1:
        return 'alive'
    return 'state?'


def block(games, t0):
    snaps = {g.who: g.snapshot() for g in games}
    facts = {g.who: log_facts(g.who) for g in games}
    print(f'===== {time.strftime("%H:%M:%S")} (+{int(time.time() - t0)} s) =====')
    rounds_all = set()
    for g in games:
        sn, fc = snaps[g.who], facts[g.who]
        gm, mi = fc['game'], fc['match']
        rd_now = gm.matches[mi] if gm is not None and mi >= 0 else {}
        rounds_all |= set(rd_now.keys())
        if 'err' in sn and 'players' not in sn:
            print(f'{g.who}: {sn["err"]}')
            continue
        key = (mi, gm.meta[mi]['start'] if gm is not None and mi >= 0 else None)
        if key != g.match_key:
            g.match_key, g.seen = key, set()
        step = sn.get('step')
        where = 'no stage' if step is None else f'step {step} round {sn.get("round")}'
        if step in OUTCOME:
            where += ' (Outcome: culled / match over here)'
        clock = f'{sn["clock"]:.0f} s' if 'clock' in sn else '-'
        own = sn.get('own') or (gm.meta[mi].get('no') if gm is not None and mi >= 0 else None) or '?'
        print(f'{g.who}: player {own} | {where} | clock {clock} | role byte {sn.get("role")} '
              f'| rule {RULES.get(sn.get("rule"), sn.get("rule"))} | authority: {fc["auth"]} '
              f'| timer corrections {fc["timer"][0]} | net clock moves {fc["netclock"]}'
              + (f' | {sn["err"]}' if 'err' in sn else ''))
        cut, virtue = set(), {}
        for r in sorted(rd_now):
            cut |= rd_now[r].cut
            virtue.update(rd_now[r].virtue)
        players = sn.get('players', {})
        g.seen |= set(players)
        if sn.get('replay'):          # no memory: the players the log names
            g.seen |= set(virtue) | {n for r in rd_now for _, ent, _, _ in rd_now[r].cutlists for n, _, _ in ent}
        parts = []
        for no in sorted(g.seen):
            state, banked = players.get(no, (None, None))
            live = virtue.get(no, '?')
            st = ('CUT' if no in cut else 'log') if sn.get('replay') else status(no, state, cut, no not in players)
            word = state.hex() if state else '--------'
            parts.append(f'{no}:{st} w{word} V{live}/{banked if banked is not None else "-"}')
        print('   players ' + ('  '.join(parts) if parts else '(none held)'))
        if 'bb' in sn:
            print(f'   bloodbound box state {sn["bb"][0]} pairs {sn["bb"][1]}')
        drives = [d for r in sorted(rd_now) for d in rd_now[r].drives]
        if drives:
            o, tot, oth = drives[-1][:3]
            print(f'   enemies: drives {o} of {tot} ({oth} other player(s) here)')
    # cut lists per round, A vs B
    for r in sorted(rounds_all):
        lists, sets = {}, {}
        for g in games:
            gm, mi = facts[g.who]['game'], facts[g.who]['match']
            if gm is None or mi < 0 or r not in gm.matches[mi]:
                continue
            rd = gm.matches[mi][r]
            if rd.cutlists:
                step, entries, h, role = rd.cutlists[-1]
                lists[g.who] = (tuple((n, k) for n, k, _ in entries), h, role)
            if rd.cut:
                sets[g.who] = tuple(sorted(rd.cut))
        if not lists and not sets:
            continue
        txt = []
        for w in sorted(set(lists) | set(sets)):
            ent = lists.get(w)
            ls = ' '.join(f'{n}:{k}' for n, k in ent[0]) + f' #{ent[1]} ({ent[2]})' if ent else 'no list'
            txt.append(f'{w}[{ls}; cut {list(sets.get(w, ()))}]')
        verdict = ''
        if len(lists) >= 2:
            same = len({(v[0], v[1]) for v in lists.values()}) == 1 and len(set(sets.values())) <= 1
            verdict = ' EQUAL' if same else ' !! DIFFER'
        print(f'   round {r} cut: ' + '  '.join(txt) + verdict)
    for g in games:
        for ln in g.new_bangs():
            print(f'   {g.who} {ln[:200]}')
    sys.stdout.flush()


class ReplayGame(Game):
    """--replay: a game whose log is read offline. Its 'memory' is what the log says (step, round, own number);
    the log is fed to the normal block code through a temporary file holding the lines up to the replay time."""

    def __init__(self, who, lines, tmp):
        super().__init__(who)
        self.all, self.tmp, self.upto = lines, tmp, []

    def feed(self, upto_sec):
        self.upto = [ln for ln, sec in self.all if sec <= upto_sec]
        Path(self.tmp).write_text('\n'.join(self.upto) + '\n', encoding='utf-8')

    def snapshot(self):
        out = {'replay': True, 'players': {}}
        for ln in reversed(self.upto):
            if 'step' not in out:
                m = cutcheck.R_PHASE.search(ln)
                if m:
                    out['step'] = int(m[1])
            if 'round' not in out:
                m = cutcheck.ROUND.search(ln)
                if m and 1 <= int(m[1]) <= 4:
                    out['round'] = int(m[1])
            if 'step' in out and 'round' in out:
                break
        return out


def replay(paths, every):
    """python diag/twin/watch_match.py --replay LABEL:LOG [LABEL:LOG ...] [--every SECONDS_OF_LOG_TIME=60]"""
    import tempfile
    tmpdir = Path(tempfile.mkdtemp(prefix='watch_replay_'))
    games, stamps = [], set()
    for i, spec in enumerate(paths):
        drive = len(spec) > 2 and spec[1] == ':' and spec[2] in '\\/'      # C:\x or C:/x: no label
        label, path = spec.split(':', 1) if ':' in spec and not drive else (chr(ord('A') + i), spec)
        lines, day, last = [], 0, None
        for ln in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
            m = cutcheck.TIME.match(ln)
            if not m:
                continue
            hh, mm, ss = (int(x) for x in m[1].split(':'))
            sec = hh * 3600 + mm * 60 + ss
            if last is not None and sec + 43200 < last:
                day += 86400
            last = sec
            lines.append((ln, sec + day))
            stamps.add(sec + day)
        tmp = tmpdir / f'{label}.txt'
        lanlog.LAN[label] = str(tmp)
        games.append(ReplayGame(label, lines, tmp))
    if not stamps:
        print('replay: no timed lines')
        return 1
    t, end = min(stamps), max(stamps)
    while True:
        for g in games:
            g.feed(t)
        print(f'--- replay log time {t // 3600 % 24:02d}:{t // 60 % 60:02d}:{t % 60:02d}')
        block(games, time.time())
        if t >= end:
            break
        t = min(t + int(every), end)
    for g in games:
        try:
            os.remove(g.tmp)
        except OSError:
            pass
    try:
        tmpdir.rmdir()
    except OSError:
        pass
    return 0


def main():
    if '--replay' in sys.argv:
        every = float(arg('--every', '60'))
        i = sys.argv.index('--replay')
        return replay(sys.argv[i + 1:], every)
    every = float(arg('--every', '5'))
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 3600
    who = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('TWIN_GAMES', 'AB')
    games = [Game(w) for w in who]
    for g in games:                 # only new '!!!' lines from now on
        try:
            g.offset = os.path.getsize(lanlog.LAN[g.who])
        except OSError:
            g.offset = 0
    t0 = time.time()
    while time.time() - t0 < seconds:
        start = time.time()
        try:
            block(games, t0)
        except Exception as e:      # never stop the watch for one bad block
            print(f'watch_match: block failed: {e!r}', flush=True)
        time.sleep(max(0.5, every - (time.time() - start)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
