"""Folders, fixed numbers and the settings file."""
import json
import os
import sys
import time
from pathlib import Path

FROZEN = getattr(sys, 'frozen', False)
# the folder the player sees: where the program (or, from source, the project) lies
BASE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[1]
if os.environ.get('DUSKLAN_BASE'):        # tests: treat another folder as the package folder
    BASE = Path(os.environ['DUSKLAN_BASE']).resolve()
# files packed into the program itself (PyInstaller unpacks them to a temporary folder)
BUNDLE = Path(getattr(sys, '_MEIPASS', BASE))

SETTINGS_FILE = BASE / 'db_launcher.json'
EARLIER_SETTINGS_FILE = BASE / 'duskbloods_lan.json'      # this launcher's file before it was renamed
OLD_SETTINGS_FILE = BASE / 'launcher_settings.json'      # the earlier launcher's; read once, never written
LOG_FILE = BASE / 'db_launcher_log.txt'               # what the window's message box said

TITLE_ID = '0400D1D02399A000'
GAME_PORT = 18443        # the room's game service (TLS)
ROOM_PORT = 18445        # the room's sign-up service (plain HTTP: /hello, /ca.der, /register)
PANEL_PORT = 18450       # host panel page (this PC only)
PANEL_API_PORT = 18451   # host panel data, served by the match server
TOOLS_PORT = 6545        # the host's own game listens here (this PC only) for the host tools
UPDATE_PORT = 18480      # "update from the host PC" and its log inbox
EMULATOR_NAMES = ('lichii.exe', 'eglantine.exe', 'eden.exe')

# The host names the game asks for; the emulator sends them to the room instead.
ONLINE_HOSTS = ('npln.srv.nintendo.net,npln.nintendo.net,n.n.srv.nintendo.net,'
                'p.srv.nintendo.net,fromsoftware-game.net')

DEFAULTS = {
    'game': '',            # path of the game's "main" file (inside <game>/exefs)
    'emulator': '',        # path of the emulator program; empty = found automatically
    'mode': 'join',        # 'join' | 'host' | 'solo'
    'host_address': '',    # the host PC's address, for joining
    'password': '',        # room password; hosts and joiners must type the same
    'room_name': '',
    'player_name': '',     # the name the game shows for this player
    'network': '',         # the network picked last (its name)
    'host_network': '',    # name of the network to host on; empty = home network
    'update_repo': '',     # GitHub repository "owner/name" that publishes releases
    'installed_release': '',
    'check_updates': True,
}


def load():
    """Settings with defaults; the first run takes the game and emulator from the earlier launcher's file."""
    data = dict(DEFAULTS)
    try:
        source = SETTINGS_FILE if SETTINGS_FILE.is_file() else EARLIER_SETTINGS_FILE
        stored = json.loads(source.read_text(encoding='utf-8'))
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if k in DEFAULTS})
            return data
    except (OSError, ValueError):
        pass
    try:
        old = json.loads(OLD_SETTINGS_FILE.read_text(encoding='utf-8'))
        if isinstance(old, dict):
            data['game'] = str(old.get('game') or '')
            data['emulator'] = str(old.get('emulator') or '')
            online = old.get('online') if isinstance(old.get('online'), dict) else {}
            data['host_address'] = str(online.get('server') or '')
            data['password'] = str(online.get('password') or '')
    except (OSError, ValueError):
        pass
    return data


def save(data):
    try:
        tmp = SETTINGS_FILE.with_suffix('.json.new')
        tmp.write_text(json.dumps({k: data.get(k, v) for k, v in DEFAULTS.items()}, indent=2), encoding='utf-8')
        os.replace(tmp, SETTINGS_FILE)
    except OSError:
        pass


def find_emulator(setting=''):
    """The emulator program: the chosen one, else the newest one found next to this launcher."""
    if setting and Path(setting).is_file():
        return Path(setting)
    found = []
    for folder in (BASE, BASE / 'Lichii', BASE / 'emulator'):
        found += [folder / name for name in EMULATOR_NAMES if (folder / name).is_file()]
    for parent in (BASE / 'emulators',):
        if parent.is_dir():
            for folder in parent.iterdir():
                found += [folder / name for name in EMULATOR_NAMES if (folder / name).is_file()]
    if not found:
        return None
    return max(found, key=lambda p: p.stat().st_mtime)


def find_game(setting=''):
    """The game's main file: the chosen one, else a game folder found next to this launcher."""
    if setting and Path(setting).is_file():
        return Path(setting)
    if setting and Path(setting).is_dir() and game_main_in(setting):
        return game_main_in(setting)
    for root in (BASE, BASE.parent):
        try:
            folders = [root] + [p for p in root.iterdir() if p.is_dir()]
        except OSError:
            continue
        for folder in folders:
            main = game_main_in(folder)
            if main:
                return main
    return None


def game_main_in(folder):
    """<folder>/exefs/main (or one level deeper) when the folder is an unpacked game, else None."""
    folder = Path(folder)
    for candidate in (folder, *(p for p in _subfolders(folder))):
        main = candidate / 'exefs' / 'main'
        if main.is_file() and (candidate / 'romfs').is_dir():
            return main
    return None


def _subfolders(folder):
    try:
        return [p for p in folder.iterdir() if p.is_dir()][:200]
    except OSError:
        return []


def data_dir(emulator):
    """Where the emulator keeps keys, settings and saves: a 'user' folder beside it, else %APPDATA%\\eden."""
    if os.environ.get('LICHII_USER_DIR'):     # the emulator's own switch for a second data folder
        return Path(os.environ['LICHII_USER_DIR'])
    portable = Path(emulator).parent / 'user'
    if portable.is_dir():
        return portable
    return Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / 'eden'


def play_dir(data):
    """The folder this launcher's saves and room files live in (kept from the earlier launcher)."""
    return data / 'test_data' if (data / 'test_data').is_dir() else data / 'duskbloods_test'


def servers_dir():
    """The room servers (needed only to host): a 'servers' folder beside the launcher, else packed in."""
    for folder in (BASE / 'servers', BUNDLE / 'servers'):
        if (folder / 'dusk_server' / 'frontdoor.py').is_file() and (folder / 'npln_server' / 'npln_stub.py').is_file():
            return folder
    return None


def note(text):
    """Append a line to the launcher's own log (kept under about 1 MB), so a problem can be read later."""
    try:
        if LOG_FILE.is_file() and LOG_FILE.stat().st_size > 1_000_000:
            LOG_FILE.write_text(LOG_FILE.read_text(encoding='utf-8', errors='replace')[-300_000:], encoding='utf-8')
        with LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + text.rstrip() + '\n')
    except OSError:
        pass
