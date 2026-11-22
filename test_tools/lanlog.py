"""Where each twin game's logs are: the gdb watcher's (quic_watch.py) and the emulator's native LAN
assist (core/dusk_lan.cpp -> <log dir>/dusk_lan.txt). Works with or without the watcher."""
import os
import re

WATCH = {'A': 'diag/net/quic_watch.log', 'B': 'diag/net/quic_watch_B.log', 'C': 'diag/net/quic_watch_C.log',
         'D': 'diag/net/quic_watch_D.log'}
LAN = {'A': os.path.join(os.environ['APPDATA'], 'eden', 'log', 'dusk_lan.txt'),
       'B': 'diag/twin/userB/log/dusk_lan.txt', 'C': 'diag/twin/userC/log/dusk_lan.txt',
       'D': 'diag/twin/userD/log/dusk_lan.txt'}
# pkgtest.py run (and any other wrapper) points the paths at other games through the environment, so the tools
# it starts as child processes (promptcheck, approach, killchr ...) read the same logs and the same main base.
for _w in 'ABCD':
    if os.environ.get('TWIN_LAN_' + _w):
        LAN[_w] = os.environ['TWIN_LAN_' + _w]
    if os.environ.get('TWIN_WATCH_' + _w):
        WATCH[_w] = os.environ['TWIN_WATCH_' + _w]


def text(path):
    try:
        return open(path, errors='replace').read()
    except OSError:
        return ''


def main_base(who):
    """main's base address, from the newer of the two logs."""
    best = None
    for path in (WATCH[who], LAN[who]):
        found = re.findall(r'main base (0x[0-9a-f]+)', text(path))
        if found:
            t = os.path.getmtime(path)
            if best is None or t > best[0]:
                best = (t, int(found[-1], 16))
    if best is None:
        raise IOError(f'{who}: no main base in {WATCH[who]} or {LAN[who]} yet')
    return best[1]


def joins(who):
    """How many LAN session joins the logs show so far."""
    return text(WATCH[who]).count('mgr3-join:') + text(LAN[who]).count('joined a LAN session')
