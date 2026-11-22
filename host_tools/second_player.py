r"""Start a second player on this PC (2026-11-15), next to the game the launcher started.

Run by "Start second player.cmd". Needs the host to run "Host a match (4 players).cmd"
(host_plus.py), which tells the match server about second games and relays guest PCs' ones.

What it does (the same as the twin rig's game B, diag\twin\twin.py):
- Its own data folder: <package>\SecondPlayer\user (LICHII_USER_DIR). Made once, as a copy of the
  first game's data (keys, config, the test nand and save the launcher uses, shader cache, mods),
  without logs, online identity, crash dumps and old runs; the copy's qt-config.ini then points
  at the copy's own folders. Its own online identity: <data>\online (EDEN_NX2_ONLINE_PROFILES),
  so the server sees another friend code = another player.
- Its own P2P port: LICHII_PORT_MAP=15500=15501 (the first game keeps 15500).
- Its own debug server port 6546 (EDEN_NX2_DEBUG_SERVER; the first game may use 6545).
- Its own sign-in address, because the match server tells players apart by the address a game
  connects from:
    on the host PC:  <this PC's LAN address>:18443 (the first game uses 127.0.0.1);
    on a guest PC:   <host address>:18453, the relay of host_plus.py, which hands the connection
                     on as 127.0.1.<d> (d = last number of this PC's address).
  The room (same password as the first game) is registered the same way, so both land in one room.
- The same emulator switches as the launcher (play_duskbloods.py Session.start).
Nothing in Windows is changed. Log: <package>\SecondPlayer\second_player_log.txt; the game's own
logs in <package>\SecondPlayer\user\log (dusk_lan.txt, eden_log.txt).

Options: --host <address> (else the address the launcher's Join a room uses), --password <text>
(else the launcher's), --setup (only make or refresh the data folder), --no-memory-check.
"""
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent if (HERE.parent / 'Play.Duskbloods.exe').exists() else HERE
EXE = PKG / 'Lichii' / 'lichii.exe'
SETTINGS = PKG / 'launcher_settings.json'
SECOND = PKG / 'SecondPlayer'
DATA = SECOND / 'user'
LOG_FILE = SECOND / 'second_player_log.txt'
GAME_FOLDER = 'THE DUSKBLOODS NETWORK TEST VER'
GAME_PORT, ROOM_PORT, RELAY_GAME, RELAY_ROOM = 18443, 18445, 18453, 18455
P2P_PORT, DEBUG_PORT = 15501, 6546
NEED_COMMIT_GB = 17
NEED_SYSTEM_GB = 40                            # N5: free space on C: (the page file grows ~35 GB)
NEED_PACKAGE_GB = 2                            # N5: the data copy (~1 GB) on the package's drive
SKIP = {'log', 'online', 'online_ca', 'crash_dumps', 'screenshots', 'runs', 'pki', 'frontdoor_pki',
        'dump', 'tas', 'lossless'}


def log(text, error=False):
    line = time.strftime('%H:%M:%S ') + text
    try:
        SECOND.mkdir(exist_ok=True)
        with LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass
    if sys.stdout is not None:
        print(line, flush=True)
    elif error:                                   # no console (the launcher's interpreter)
        try:
            import tkinter
            from tkinter import messagebox
            root = tkinter.Tk(); root.withdraw()
            messagebox.showerror('Second player', text)
            root.destroy()
        except Exception:
            pass


def ask(question):
    if sys.stdin is not None and sys.stdout is not None:
        return input(question + ' [y/N] ').strip().lower().startswith('y')
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk(); root.withdraw()
        answer = messagebox.askyesno('Second player', question)
        root.destroy()
        return answer
    except Exception:
        return False


def settings():
    try:
        data = json.loads(SETTINGS.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def room_id(password):
    """As the launcher (play_duskbloods.py room_id): only this hash leaves the PC."""
    return hashlib.sha256(('duskbloods-room-v1:' + password.strip()).encode('utf-8')).hexdigest()[:32]


def lan_ip():
    """This PC's address on the home network (no packet is sent). N1 (deep_audit_N): it can be
    chosen with DUSK_LAN_IP=<address> or a file lan_fix\\lan_ip.txt holding it. Else the route to
    192.168.0.1 is the first guess. On a PC whose VPN takes that route (a full VPN, a Tailscale
    exit node: 100.64-100.127.x; Hamachi: 25.x) the guess is not a home address, and on a PC
    without a gateway there is no route at all: then this PC's other addresses are used,
    192.168.x first, then 10.x, then 172.16-172.31.x."""
    forced = _override_text()
    if forced.lower() == 'tailscale':
        # Tailscale play (tailscale_support.diff): this PC's Tailscale address, or '' when Tailscale
        # is not signed in / connected (the callers stop with a clear message then).
        return tailscale_ip()
    if forced and _usable_override(forced):
        return forced
    guess = ''
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.168.0.1', 9))
        guess = s.getsockname()[0]
    except OSError:
        pass                                   # no route (no gateway): use the list below
    finally:
        s.close()
    if _home_address(guess):
        return guess
    for prefix in ('192.168.', '10.', '172.'):
        for address in lan_ip_candidates():
            if address.startswith(prefix):
                return address
    return guess or '127.0.0.1'


# what Tailscale hands out (CGNAT shared space); DUSK_VPN_NET=<a.b.c.d/n> names another VPN's network
# (ZeroTier: the launcher sets it from the ZeroTier adapter), and the same mode then works for it
TAILSCALE_NET = os.environ.get('DUSK_VPN_NET', '').strip() or '100.64.0.0/10'
VPN_NAME = os.environ.get('DUSK_VPN_NAME', '').strip() or 'Tailscale'


def _override_text():
    """DUSK_LAN_IP, else the first word of lan_fix\\lan_ip.txt (review R1: utf-8-sig), else ''."""
    forced = os.environ.get('DUSK_LAN_IP', '').strip()
    if not forced:
        try:
            forced = (Path(__file__).resolve().parent / 'lan_ip.txt').read_text(encoding='utf-8-sig')
            forced = (forced.split() or [''])[0]
        except OSError:
            forced = ''
    return forced


def tailscale_mode():
    """Tailscale play is switched on: lan_ip.txt or DUSK_LAN_IP holds the word "tailscale" or a 100.x
    (Tailscale) address (review T1: the same test in every script)
    ("Host a match (Tailscale).cmd" sets DUSK_LAN_IP=tailscale)."""
    text = _override_text()
    return text.lower() == 'tailscale' or in_tailscale(text)


def in_tailscale(ip):
    import ipaddress
    try:
        return ipaddress.IPv4Address(ip) in ipaddress.IPv4Network(TAILSCALE_NET, strict=False)
    except ValueError:
        return False


def tailscale_ip():
    """This PC's Tailscale IPv4 address (100.64-100.127.x), or '' when Tailscale is not connected.
    The adapters first; then `tailscale ip -4` (read only; nothing is signed in or changed)."""
    try:
        found = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        found = []
    for address in found:
        if in_tailscale(address):
            return address
    try:
        out = subprocess.run(['tailscale', 'ip', '-4'], capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except (OSError, subprocess.SubprocessError):
        out = ''
    return next((w for w in out.split() if in_tailscale(w)), '')


def _usable_override(ip):
    """review R1: lan_ip.txt / DUSK_LAN_IP must be a plain IPv4 address, not loopback or 169.254.x."""
    import ipaddress
    try:
        address = ipaddress.IPv4Address(ip)
    except ValueError:
        address = None
    if address is None or address.is_loopback or address.is_link_local or address.is_unspecified:
        sys.stderr.write(f'lan_ip.txt / DUSK_LAN_IP: "{ip}" is not a usable IPv4 address; ignored.\n')
        return False
    return True


def _home_address(ip):
    import ipaddress
    try:
        address = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return address.is_private and not (address.is_loopback or address.is_link_local)


def lan_ip_candidates():
    """Every home-network address of this PC (all adapters: LAN, Wi-Fi, ZeroTier, ...)."""
    try:
        found = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        found = []
    return [a for a in found if _home_address(a)]


def first_data_dir():
    """The first game's data folder, as the launcher finds it (play_duskbloods.py data_dir_for)."""
    portable = EXE.parent / 'user'
    if portable.is_dir():
        return portable
    appdata = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
    for name in ('eden', 'lichii', 'eglantine', 'yuzu'):
        if (appdata / name).is_dir():
            return appdata / name
    return appdata / 'eden'


def game_main(conf):
    """The game to boot: the launcher's choice, else the game folder next to the package."""
    folders = [Path(conf['game'])] if conf.get('game') else []
    folders += [PKG / GAME_FOLDER, PKG.parent / GAME_FOLDER]
    for path in folders:
        if path.suffix.lower() == '.nup' and path.is_file():
            return path
        for candidate in (path / 'base/exefs/main', path / 'exefs/main',
                          path / GAME_FOLDER / 'base/exefs/main'):
            if candidate.is_file():
                return candidate
    return None


def http(host, port, path, data=None, source=None, timeout=8):
    """A small HTTP request with an optional source address (as twin.py register())."""
    body = json.dumps(data).encode() if data is not None else b''
    method = 'POST' if data is not None else 'GET'
    s = socket.create_connection((host, port), timeout=timeout,
                                 source_address=(source, 0) if source else None)
    try:
        head = (f'{method} {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n'
                + (f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n' if data is not None else '')
                + '\r\n')
        s.sendall(head.encode() + body)
        reply = b''
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            reply += chunk
    finally:
        s.close()
    head, _, payload = reply.partition(b'\r\n\r\n')
    status = head.split(b'\r\n', 1)[0].decode(errors='replace')
    if ' 200 ' not in status + ' ':
        raise OSError(f'{path}: {status}')
    return payload


def config_path(data):
    return data / 'config' / 'qt-config.ini'


def config_dir(text, key):
    found = re.search(rf'(?m)^{re.escape(key)}=(.*)$', text)
    return Path(found.group(1).strip()) if found and found.group(1).strip() else None


def set_key(text, key, value):
    """As the launcher's set_key: the value, and its 'default' flag off."""
    pattern = re.compile(rf'(?m)^{re.escape(key)}=.*$')
    if pattern.search(text):
        text = pattern.sub(lambda _: f'{key}={value}', text)
        text = re.sub(rf'(?m)^{re.escape(key)}\\default=(true|false)$',
                      lambda _: f'{key}\\default=false', text)
    return text


def copy_tree(src, dst):
    def ignore(folder, names):
        return [n for n in names if n in SKIP]
    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def make_data():
    """The second game's data folder (once; --setup refreshes it)."""
    source = first_data_dir()
    conf_file = config_path(source)
    if not conf_file.exists():
        log(f'The first game has no settings yet ({conf_file}). Start the game once with the launcher, '
            'then start the second player.', error=True)
        return False
    text = conf_file.read_text(encoding='utf-8')
    log(f'Making the second player\'s data folder {DATA} from {source} (about 1 GB, once)...')
    DATA.mkdir(parents=True, exist_ok=True)
    for name in ('keys', 'config', 'cache', 'load', 'amiibo', 'icons', 'play_time', 'sdmc',
                 'post_presets', 'post_shaders', 'streamline'):
        if (source / name).is_dir():
            copy_tree(source / name, DATA / name)
    if (source / 'nx2_switches.txt').is_file():
        shutil.copy2(source / 'nx2_switches.txt', DATA / 'nx2_switches.txt')
    # The nand and save the first game really uses (the launcher points qt-config.ini at
    # <data>\duskbloods_test\nand and \save).
    test = DATA / 'duskbloods_test'
    nand = config_dir(text, 'nand_directory') or source / 'nand'
    save = config_dir(text, 'save_directory') or source / 'nand' / 'user' / 'save'
    for src, dst in ((nand, test / 'nand'), (save, test / 'save')):
        if src.is_dir():
            # review R4: --setup on an existing copy must not replace the second player's own progress
            # without asking (copy_tree overwrites file by file).
            if dst.is_dir() and any(dst.iterdir()) and not ask(
                    f'{dst} already holds the second player\'s own {dst.name} (its progress). Replace it '
                    'with a copy of the first game\'s?'):
                log(f'{dst} kept as it is.')
                continue
            copy_tree(src, dst)
        else:
            dst.mkdir(parents=True, exist_ok=True)
    point_config()
    (DATA / 'online').mkdir(exist_ok=True)
    log('Data folder ready.')
    return True


def point_config():
    """The copy's qt-config.ini points at the copy's own folders. N6: run at every start too, so a
    package folder that was moved or renamed (or extracted elsewhere) still finds its own nand
    and save; tas and screenshots no longer point into the first game's folder."""
    test = DATA / 'duskbloods_test'
    text = config_path(DATA).read_text(encoding='utf-8')
    for key, value in (('nand_directory', (test / 'nand').as_posix()),
                       ('save_directory', (test / 'save').as_posix()),
                       ('sdmc_directory', (DATA / 'sdmc').as_posix()),
                       ('load_directory', (DATA / 'load').as_posix()),
                       ('dump_directory', (DATA / 'dump').as_posix()),
                       ('tas_directory', (DATA / 'tas').as_posix()),
                       ('Screenshots\\screenshot_path', (DATA / 'screenshots').as_posix()),
                       ('airplane_mode', 'false'), ('use_gdbstub', 'false'),
                       ('check_for_updates', 'false')):
        text = set_key(text, key, value)
    text = re.sub(r'(?m)^network_interface=.*$', 'network_interface=', text)
    text = re.sub(r'(?m)^network_interface\\default=.*$', r'network_interface\\default=true', text)
    config_path(DATA).write_text(text, encoding='utf-8')


def refresh_data():
    """N6: at every start (data folder already made): the first game's current emulator switches
    and keys (a few KB) and the copy's own paths. Its settings (controls), saves and identity stay."""
    source = first_data_dir()
    try:
        if (source / 'nx2_switches.txt').is_file():
            shutil.copy2(source / 'nx2_switches.txt', DATA / 'nx2_switches.txt')
        if (source / 'keys').is_dir():
            copy_tree(source / 'keys', DATA / 'keys')
        if config_path(DATA).exists():
            point_config()
    except OSError as error:
        log(f'Could not refresh the data folder from {source} ({error}); the old copy is used.')


def disk_ok():
    """N5: the readme's rule as a check. Two games make Windows grow its page file on the system
    drive (about 35 GB in our tests; a full disk damaged a save once)."""
    system = Path((os.environ.get('SystemDrive') or 'C:') + '\\')
    checks = [(system, NEED_SYSTEM_GB)]
    if Path(PKG.anchor) != system:
        checks.append((Path(PKG.anchor), NEED_PACKAGE_GB))
    for drive, need in checks:
        try:
            free = shutil.disk_usage(drive).free / 2**30
        except OSError:
            continue
        log(f'Free space on {drive}: {free:.0f} GB (needed: {need} GB).')
        if free < need and not ask(f'Only {free:.0f} GB is free on {drive}; two games need about {need} GB '
                                   'there (a full disk can damage a save). Start anyway?'):
            return False
    return True


def first_game_running():
    """N4: is a game (lichii.exe) already running on this PC? (tasklist; no setting is touched)"""
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq lichii.exe', '/NH'], capture_output=True,
                             text=True, timeout=10, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return True                                # unknown: do not stop anybody
    return 'lichii.exe' in out.lower()


def memory_ok():
    """Free commit (Task Manager > Memory > Committed: second number minus first)."""
    try:
        import ctypes

        class Status(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
        status = Status(); status.dwLength = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        commit = status.ullAvailPageFile / 2**30
        phys = status.ullAvailPhys / 2**30
    except Exception:
        return True
    log(f'Memory now: {commit:.1f} GB commit free, {phys:.1f} GB real memory free '
        f'(a game needs about {NEED_COMMIT_GB} GB commit and 3 to 3.5 GB video memory).')
    if commit >= NEED_COMMIT_GB:
        return True
    return ask(f'Only {commit:.1f} GB commit is free; a second game needs about {NEED_COMMIT_GB} GB. '
               'Windows may still grow it if drive C: has free space, or the game may close. Start anyway?')


def main(argv):
    conf = settings()
    online = conf.get('online') or {}
    if '--host' in argv:
        host = argv[argv.index('--host') + 1]
    else:
        host = (online.get('server') or '').strip().replace('http://', '').split(':')[0].strip('/')
    password = argv[argv.index('--password') + 1] if '--password' in argv else online.get('password') or ''
    if not EXE.exists():
        log(f'lichii.exe not found at {EXE}: put this file in the package\'s lan_fix folder.', error=True)
        return 1
    if '--no-memory-check' not in argv and not disk_ok():
        log('Not started (disk space).')
        return 1
    if not DATA.is_dir() or '--setup' in argv:
        if not make_data():
            return 1
        if '--setup' in argv:
            return 0
    else:
        refresh_data()
    if '--setup' not in argv and not first_game_running() and not ask(
            'The first game is not running. Start it with the launcher first (host or join), so that '
            'the memory check counts it and both games land in the same room. Start the second player anyway?'):
        log('Not started (first game not running).')
        return 1
    main_file = game_main(conf)
    if main_file is None:
        log('The game was not found: start it once with the launcher (it remembers the game folder), '
            f'or put "{GAME_FOLDER}" next to Play.Duskbloods.exe.', error=True)
        return 1
    if not password:
        log('No room password: type it in the launcher\'s Online tab first (the same for every player).',
            error=True)
        return 1
    own = lan_ip()
    # Is this the host PC? host_plus.py's relay listens here only when this PC hosts with it (it
    # refuses connections from this PC itself, so only the connect is tried).
    try:
        socket.create_connection(('127.0.0.1', RELAY_ROOM), timeout=2).close()
        here_hosts = True
    except OSError:
        here_hosts = False
    if not here_hosts:
        # N3: this PC runs the launcher's own servers, but hosts with the plain "Host a match" file
        # (no relay): a guest-PC attempt would go to some old address from the launcher's Join tab.
        try:
            local_room = json.loads(http('127.0.0.1', ROOM_PORT, '/hello', timeout=2))
        except (OSError, ValueError):
            local_room = {}
        if local_room.get('service') == 'duskbloods-online':
            log('This PC hosts the room, but with the plain "Host a match" file. For a second player close '
                'the launcher and host with "Host a match (4 players).cmd" instead.', error=True)
            return 1
    if here_hosts:
        # Tailscale play: host_plus.py names the address this PC's games sign in from
        try:
            own = (HERE / 'host_address.txt').read_text(encoding='utf-8').split()[0] or own
        except (OSError, IndexError):
            pass
        if not own:
            log('Tailscale play is switched on, but this PC has no Tailscale address (100.x): sign in '
                'to Tailscale first.', error=True)
            return 1
        mode = 'host PC'
        server, source, room_port = own, own, ROOM_PORT
        port = GAME_PORT
    else:
        if not host:
            log('Type the host\'s address in the launcher (Online tab, Join a room) and join with the first '
                'game first, or start this with --host <address>.', error=True)
            return 1
        mode = 'guest PC'
        server, source, room_port, port = host, None, RELAY_ROOM, RELAY_GAME
    log(f'Second player on the {mode}: sign-in {server}:{port}, room via {server}:{room_port}, '
        f'P2P port {P2P_PORT}, data {DATA}')
    try:
        hello = json.loads(http(server, room_port, '/hello', source=source))
        if hello.get('service') != 'duskbloods-online':
            raise OSError('that is not a Duskbloods room')
        ca = SECOND / 'host_ca.der'
        ca.write_bytes(http(server, room_port, '/ca.der', source=source))
        http(server, room_port, '/register', {'room': room_id(password)}, source=source)
    except (OSError, ValueError) as error:
        if mode == 'guest PC':
            log(f'The host\'s second-player service did not answer at {server}:{RELAY_ROOM} ({error}). '
                'On the host PC: start the host with "Host a match (4 players).cmd" (not the plain one), '
                'press Start game there first, and if Windows asks whether Python may use the network, '
                'click Allow.', error=True)
        else:
            log(f'The room service of this PC did not answer ({error}): press Start game in the launcher '
                'first (Host a room).', error=True)
        return 1
    log(f'Room joined ({hello.get("name", "")}).')
    if '--no-memory-check' not in argv and not memory_ok():
        log('Not started (memory).')
        return 1
    run = SECOND / 'runs' / time.strftime('%Y%m%d_%H%M%S')
    run.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('EDEN_NX2_', 'EDEN_NATIVE_'))}
    env.update(EDEN_NX2_DIAG_CODEC_CLIENT_REPLY='1', EDEN_NX2_EXPERIMENTAL_CODEC_DECODE='1',
               EDEN_NX2_EXPERIMENTAL_SYSMIX_OUTPUT='1', EDEN_NX2_SYSMIX_DRAIN_MULTIPLIER='1',
               EDEN_NX2_APP_POOL_PROBE='1152', EDEN_NX2_GPU_MAP_FLAG_PROBE='1',
               EDEN_NX2_SILENT_BAD_OPUS='1',
               EDEN_NX2_ONLINE_HOSTS='npln.srv.nintendo.net,npln.nintendo.net,n.n.srv.nintendo.net,'
                                     'p.srv.nintendo.net,fromsoftware-game.net',
               EDEN_NX2_ONLINE_SERVER=f'{server}:{port}',
               EDEN_NX2_ONLINE_CA=str(SECOND / 'host_ca.der'),
               EDEN_NX2_CRASH_DUMP=str(run), EDEN_NX2_TRACE_TERMINATE='1',
               EDEN_NX2_ONLINE_PROFILES=str(DATA / 'online'),
               EDEN_NX2_DEBUG_SERVER=f'127.0.0.1:{DEBUG_PORT}',
               LICHII_USER_DIR=str(DATA),
               LICHII_PORT_MAP=f'15500={P2P_PORT}')
    env.pop('SDL_AUDIODRIVER', None)
    env.pop('LICHII_GDBSTUB', None)
    with (run / 'console.log').open('w') as console:
        game = subprocess.Popen([str(EXE), '-g', str(main_file)], cwd=str(EXE.parent), env=env,
                                stdout=console, stderr=subprocess.STDOUT)
    log(f'Second player started (process {game.pid}). Its logs: {DATA / "log"}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
