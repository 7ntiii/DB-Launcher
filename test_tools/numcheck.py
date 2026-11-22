"""numcheck.py LOG  -- READ ONLY: the numbering facts of the LAST join in one dusk_lan.txt (for runnum.sh, 2026-11-16).
Prints one line of key=value:
  no=<number armed last> deliv=<number in the last "message 4 delivered" or -> s2=<time of the last "session state 2"
  or 3 before the arming> armed=<time of the last "message 4 armed"> delta=<armed - s2 in s, or ->
  v413=<lines with "(v413)"> yield=<"taking N instead (v413)" lines> wait=<"waiting before message 4 (v413)" lines>
  dup=<"DUPLICATE PLAYER NUMBER" lines> force=<"DUSK_NUMBER_FORCE_B:" lines>
Counts cover the whole file (the log is new at every game start)."""
import re
import sys


def secs(t):
    h, m, s = (int(x) for x in t.split(':'))
    return h * 3600 + m * 60 + s


def main():
    try:
        lines = open(sys.argv[1], encoding='utf-8', errors='replace').read().splitlines()
    except OSError as e:
        print('error=%s' % e)
        return 1
    ts = re.compile(r'^(\d\d:\d\d:\d\d) ')
    armed_i, no = None, None
    for i, ln in enumerate(lines):
        m = re.search(r'player no (\d+) team \d+ \(\d+ players\): message 4 armed', ln)
        if m:
            armed_i, no = i, m.group(1)
    deliv = None
    for ln in lines:
        m = re.search(r'message 4 delivered: player no is now (-?\d+)', ln)
        if m:
            deliv = m.group(1)
    s2 = armed = delta = None
    if armed_i is not None:
        m = ts.match(lines[armed_i])
        armed = m.group(1) if m else None
        for ln in reversed(lines[:armed_i]):
            if re.search(r'session state [23],', ln):
                m2 = ts.match(ln)
                s2 = m2.group(1) if m2 else None
                break
        if armed and s2:
            delta = (secs(armed) - secs(s2)) % 86400
    cnt = lambda pat: sum(1 for ln in lines if re.search(pat, ln))  # noqa: E731
    print('no=%s deliv=%s s2=%s armed=%s delta=%s v413=%d yield=%d wait=%d dup=%d force=%d' % (
        no or '-', deliv or '-', s2 or '-', armed or '-', '-' if delta is None else delta,
        cnt(r'\(v413\)'), cnt(r'taking \d+ instead \(v413\)'), cnt(r'waiting before message 4 \(v413\)'),
        cnt(r'DUPLICATE PLAYER NUMBER'), cnt(r'DUSK_NUMBER_FORCE_B:')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
