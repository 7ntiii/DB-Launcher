"""DB-Launcher: starts the emulator for a match on a home network or a VPN.

Written from zero in November 2026. One window, three steps (check, pick host or join, play).
Modules:
    config    settings file, folders, fixed numbers (ports, title id)
    network   this PC's networks, room protocol helpers, finding hosts
    checks    the automatic health check shown at the top of the window
    game      preparing the emulator's data and starting the game (join / solo)
    hosting   the room servers, the host profile and the host panel
    updates   updates from a GitHub repository's releases (or from the host PC)
    support   collecting logs
    web       the window: a local page in a window of its own, and the actions behind its buttons
    hosttools the host's match tools (heal, hold a boss, go to a player, freeze the time)
"""
import os
import sys
from pathlib import Path

VERSION = '2.3.0'


def _role():
    """Two launchers from one program: the program's file name decides what it offers.
    '... Host.exe' hosts or plays alone, '... Join.exe' joins or plays alone; any other name offers everything.
    DUSKLAN_ROLE (host / join / all) overrides the name, for running from source."""
    wanted = os.environ.get('DUSKLAN_ROLE', '').lower()
    if wanted in ('host', 'join', 'all'):
        return wanted
    name = Path(sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]).stem.lower()
    return 'host' if 'host' in name else 'join' if 'join' in name else 'all'


ROLE = _role()
ROLE_MODES = {'host': ('host', 'solo'), 'join': ('join', 'solo'), 'all': ('join', 'host', 'solo')}[ROLE]
APP_NAME = 'DB-Launcher' + {'host': ' Host', 'join': ' Join', 'all': ''}[ROLE]
