r"""pkgtest.py: one-PC test of the v3.9.9 package's "two players on one PC" scripts, from a scratch copy.
Written 2026-11-16 (static; not run yet). Driven by diag/twin/pkgtest.sh; every step is also a subcommand:

  python diag/twin/pkgtest.py precheck | unpack | userdir | serve | game1 | game2 | rows | waitdebug A|B
                               | run [--autostart] SCRIPT [ARGS] | check | untouched | stop | clean

What it starts, and how (the package's own way where a person is not needed):
- Scratch root diag\twin\pkgtest\ (PKGTEST_DIR): the zip unpacked to pkgtest\Duskbloods-Lichii-Online\.
- First game's data: a PORTABLE folder pkgtest\...\Lichii\user, filled by a read-only copy of %APPDATA%\eden
  (as second_player.py make_data does). The launcher's data_dir_for() and second_player.py's first_data_dir()
  both pick a portable Lichii\user first, so nothing of the user's own data folder is used or written.
  %APPDATA%\eden\config is never opened for writing; launcher\launcher_settings.json is only read.
- Host side WITHOUT the GUI: the launcher's match server exists only after a person presses Start game in
  Play.Duskbloods.exe, and lan_fix_host.py opens a browser window. So `serve` does what those do, headless:
  * the server scripts are taken out of Play.Duskbloods.exe itself (its PyInstaller archive is read, nothing
    is run) into pkgtest\mei\tools\, then frontend_api.py and npln_stub.py are replaced by the package's
    lan_fix copies (= lan_fix_host.py's swap);
  * the environment of lan_fix_host.py + host_plus.py (DUSK_MATCH_WAIT, DUSK_TICKET_TTL, DUSK_P2P_FORMAT=self,
    DUSK_HOST_IP, DUSK_MATCH_HOLD=1, DUSK_WAIT_LONGPOLL, DUSK_PANEL_PORT=18451, DUSK_PANEL_HTML,
    DUSK_P2P_PORTS / DUSK_P2P_ADDR) and the launcher's host-mode start_servers() (npln_stub + frontdoor with
    the same arguments, the room registered with the password's room id);
  * host_plus.py's own relay() threads on 18453 / 18455 (the package file is imported, not copied).
- Game 1: lichii.exe -g <main> with the launcher's Session.start() environment (EDEN_NX2_ONLINE_SERVER=
  127.0.0.1:18443 and its CA), plus EDEN_NX2_DEBUG_SERVER=127.0.0.1:6545 (the launcher passes EDEN_NX2_* through)
  and LICHII_USER_DIR=<portable folder> (belt and braces: if this lichii did not honour the portable folder it
  would otherwise fall back to %APPDATA%\eden).
- Game 2: the package's own lan_fix\second_player.py, run as "Start second player.cmd" runs it
  (python second_player.py ...), with --no-memory-check and --password (the cmd passes %* through).
  Its settings come from pkgtest\...\launcher_settings.json, which this script writes inside the scratch copy.
- Drive (rig tools, unchanged): to_hub2b.py / to_match2b.py / treasures.py run through `run`, which points
  lanlog.py and screen.py at the pkgtest log / config folders first. `--autostart` presses the panel's
  Start match (POST /api/start) once both rows are searching, as the host person would.
- Everything started has a command line or exe path inside the scratch root; `stop` kills exactly those
  processes (taskkill /T /F by PID) and nothing else. `clean` (PKGTEST_CLEAN=1 in pkgtest.sh) deletes only the
  scratch root, after a stop.
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # diag/twin
WS = HERE.parents[1]                                    # the workspace
PT = Path(os.environ.get('PKGTEST_DIR') or HERE / 'pkgtest').resolve()
# audit_pkgtest_notes.md F2: `stop` kills every process whose path holds PT and `clean` deletes PT, so a
# wrong PKGTEST_DIR (C:\, the profile, the workspace) must never get that far: PT is a pkgtest* folder
# directly in diag\twin, nothing else.
if PT.parent != HERE or not PT.name.lower().startswith('pkgtest') or PT.suffix.lower() in ('.py', '.sh'):
    sys.exit(f'pkgtest: PKGTEST_DIR must be a pkgtest* folder directly in {HERE} (got {PT}); nothing done')
ZIP = Path(os.environ.get('PKGTEST_ZIP') or WS / 'share' / 'Duskbloods-Lichii-Online v3.9.9.zip')  # was v3.9.5
PKG = PT / 'Duskbloods-Lichii-Online'
LICHII = PKG / 'Lichii' / 'lichii.exe'
USER = PKG / 'Lichii' / 'user'                          # game 1's portable data folder
TEST = USER / 'duskbloods_test'                         # the launcher's test_dir_for(data)
SECOND = PKG / 'SecondPlayer'
MEI = PT / 'mei'                                         # the launcher's unpacked tools (static copy)
STATE = PT / 'state.json'
LOG = PT / 'pkgtest_log.txt'
MANIFEST = PT / 'untouched_before.json'
APPDATA = Path(os.environ.get('APPDATA', Path.home() / 'AppData/Roaming'))
SOURCE = Path(os.environ.get('PKGTEST_SOURCE') or APPDATA / 'eden')   # read only
REAL_SETTINGS = WS / 'launcher' / 'launcher_settings.json'           # read only
PASSWORD = os.environ.get('PKGTEST_PASSWORD', 'pkgtest-one-pc')
GAME_DIR = WS / 'game' / 'THE DUSKBLOODS' / 'THE DUSKBLOODS NETWORK TEST VER'

GAME_PORT, UPSTREAM, ROOM_PORT, WEB_PORT, PANEL_API = 18443, 18444, 18445, 18090, 18451
RELAY_GAME, RELAY_ROOM, DEBUG = 18453, 18455, {'A': 6545, 'B': 6546}
TCP_PORTS = [GAME_PORT, UPSTREAM, ROOM_PORT, PANEL_API, RELAY_GAME, RELAY_ROOM, 6545, 6546, WEB_PORT]
UDP_PORTS = [15500, 15501]
EMULATORS = ('lichii.exe', 'eden.exe', 'yuzu.exe', 'eglantine.exe', 'play.duskbloods.exe')
RIG_WORDS = ('twin.py', 'twin4.py', 'frontdoor.py', 'npln_stub.py', 'lan_fix_host.py', 'host_plus.py',
             'second_player.py', 'go4', 'run4', 'runnet', 'quic_watch',
             'play_duskbloods')                      # F5: the launcher run from its source
# F3: the only programs this test starts (by its own path or with a scratch script on the command line)
OUR_NAMES = ('lichii.exe', 'play.duskbloods.exe', 'python.exe', 'pythonw.exe', 'py.exe')
COPY_DIRS = ('keys', 'config', 'cache', 'load', 'amiibo', 'icons', 'play_time', 'sdmc', 'post_presets',
             'post_shaders', 'streamline')                   # second_player.py make_data's list
GB = 2 ** 30


def log(text):
    line = time.strftime('%H:%M:%S ') + text
    print(line, flush=True)
    try:
        PT.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def state():
    try:
        return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(**kw):
    s = state()
    s.update(kw)
    PT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1), encoding='utf-8')


def lan_ip():
    """lan_fix_host.py / host_plus.py / second_player.py's pick (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.168.0.1', 9))
        return s.getsockname()[0]
    finally:
        s.close()


def rig_tailscale():
    """RIG_NET=tailscale (run_night.sh; tailscale_rig_notes.md): the rig hosts players who join with this
    PC's Tailscale address, as "Host a match (Tailscale).cmd" does. Unset / lan = the home network (as before)."""
    return os.environ.get('RIG_NET', '').strip().lower() == 'tailscale'


def tailscale_ip4():
    """This PC's Tailscale IPv4 (100.64-100.127.x) from `tailscale ip -4`, or ''. Read only: nothing is signed
    in, set or changed (no `tailscale up / login / set`, no firewall)."""
    import ipaddress
    if os.environ.get('RIG_VPN_IP'):   # another VPN (ZeroTier): its address is given, with DUSK_VPN_NET / DUSK_VPN_NAME
        return os.environ['RIG_VPN_IP'].strip()
    for exe in ('tailscale', r'C:\Program Files\Tailscale\tailscale.exe'):
        try:
            out = subprocess.run([exe, 'ip', '-4'], capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for word in out.split():
            try:
                if ipaddress.IPv4Address(word) in ipaddress.IPv4Network('100.64.0.0/10'):
                    return word
            except ValueError:
                pass
    return ''


def rig_ip():
    """The address the other players join with: the LAN one, or (RIG_NET=tailscale) this PC's 100.x."""
    return tailscale_ip4() if rig_tailscale() else lan_ip()


def local_addresses():
    """play_duskbloods.py local_addresses(): private IPv4 addresses, LAN first (copied, unchanged logic)."""
    import ipaddress
    found = []
    try:
        found += [i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(('192.0.2.1', 9))
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    vpn = [ipaddress.IPv4Network(n) for n in ('100.64.0.0/10', '26.0.0.0/8', '25.0.0.0/8')]
    out = []
    for a in found:
        try:
            ip = ipaddress.IPv4Address(a)
        except ValueError:
            continue
        if ip.is_loopback or ip.is_link_local or not (ip.is_private or any(ip in n for n in vpn)):
            continue
        if a not in out:
            out.append(a)
    lan = lan_ip()
    if lan in out:                                       # the address the panel / host_plus use first
        out.remove(lan)
        out.insert(0, lan)
    return out


def room_id(password):
    return hashlib.sha256(('duskbloods-room-v1:' + password.strip()).encode('utf-8')).hexdigest()[:32]


def http(url, data=None, timeout=8):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json'} if data is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- processes / ports
def processes():
    ps = ('Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,'
          'CommandLine | ConvertTo-Json -Compress')
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
                       capture_output=True, text=True, timeout=90)
    try:
        rows = json.loads(r.stdout or '[]')
    except ValueError:
        return []
    return rows if isinstance(rows, list) else [rows]


def ours(p):
    """A process this test started: its exe or command line lies inside the scratch root."""
    root = str(PT).lower() + '\\'                      # inside the folder (not pkgtest.py / pkgtest.sh)
    exe = (p.get('ExecutablePath') or '').lower().replace('/', '\\')
    line = (p.get('CommandLine') or '').lower().replace('/', '\\')
    name = (p.get('Name') or '').lower()
    if p.get('ProcessId') in (os.getpid(), os.getppid()):
        return False
    # F3: an exe inside the scratch root, or one of our interpreters running a scratch script. Not any
    # program that merely has a scratch file open (an editor on pkgtest_log.txt, a tail, Explorer).
    return exe.startswith(root) or (name in OUR_NAMES or name.startswith('python')) and root in line


def listening():
    tcp, udp = set(), set()
    for proto, bag in (('tcp', tcp), ('udp', udp)):
        r = subprocess.run(['netstat', '-ano', '-p', proto], capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].upper() == proto.upper():
                if proto == 'tcp' and (len(parts) < 5 or parts[3] != 'LISTENING'):
                    continue
                port = parts[1].rsplit(':', 1)[-1]
                if port.isdigit():
                    bag.add(int(port))
    return tcp, udp


def memory():
    import ctypes

    class S(ctypes.Structure):
        _fields_ = [('l', ctypes.c_ulong), ('load', ctypes.c_ulong), ('tp', ctypes.c_ulonglong),
                    ('ap', ctypes.c_ulonglong), ('tf', ctypes.c_ulonglong), ('af', ctypes.c_ulonglong),
                    ('tv', ctypes.c_ulonglong), ('av', ctypes.c_ulonglong), ('ae', ctypes.c_ulonglong)]
    s = S()
    s.l = ctypes.sizeof(S)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
    return s.af / GB, s.ap / GB


def cmd_precheck():
    bad = []
    for p in processes():
        name = (p.get('Name') or '').lower()
        line = (p.get('CommandLine') or '').lower()
        if ours(p):
            bad.append(f'an earlier pkgtest process still runs (pid {p["ProcessId"]} {name}): run "pkgtest.sh stop"')
        elif name in EMULATORS:
            bad.append(f'{name} runs (pid {p["ProcessId"]}): the user\'s own game / launcher or the rig')
        elif name.startswith('python') and any(w in line for w in RIG_WORDS):
            bad.append(f'rig / host tool runs (pid {p["ProcessId"]}): {line[:120]}')
    tcp, udp = listening()
    bad += [f'TCP port {x} is in use' for x in TCP_PORTS if x in tcp]
    bad += [f'UDP port {x} is in use' for x in UDP_PORTS if x in udp]
    need_disk = 0 if (PKG / 'Lichii' / 'lichii.exe').exists() else 0.4
    need_disk += 0 if USER.is_dir() else 0.7
    need_disk += 0 if (SECOND / 'user').is_dir() else 0.7
    need_disk += 2.0                                     # logs, shader caches, crash dumps
    free = shutil.disk_usage(str(WS)).free / GB
    if free < need_disk:
        bad.append(f'only {free:.1f} GB free on the workspace drive, {need_disk:.1f} GB needed')
    # F6 (handoff 1 line 1314, the disk-full incident that cut game A's save short): two games make
    # Windows grow pagefile.sys on the system drive; keep a margin there too.
    sys_free = shutil.disk_usage(os.environ.get('SystemDrive', 'C:') + '\\').free / GB
    if sys_free < 20:
        bad.append(f'only {sys_free:.1f} GB free on the system drive; two games can grow the paging file '
                   'by 15+ GB (20 GB wanted)')
    try:
        commit, phys = memory()
        if commit < 34 and os.environ.get('PKGTEST_LOW_MEMORY') != '1':
            bad.append(f'only {commit:.1f} GB commit free; two games need about 34 GB (PKGTEST_LOW_MEMORY=1 = try anyway)')
    except Exception:
        commit = phys = -1
    if not ZIP.exists():
        bad.append(f'zip not found: {ZIP}')
    if not (SOURCE / 'config' / 'qt-config.ini').exists():
        bad.append(f'no {SOURCE}\\config\\qt-config.ini to copy the first game\'s settings from')
    log(f'precheck: disk free {free:.1f} GB (need {need_disk:.1f}), commit free {commit:.1f} GB, '
        f'RAM free {phys:.1f} GB, LAN {lan_ip()}')
    for b in bad:
        log('  REFUSED: ' + b)
    if not bad:
        log('precheck OK')
    return 2 if bad else 0


# ---------------------------------------------------------------- unpack / data / settings
def cmd_unpack():
    PT.mkdir(parents=True, exist_ok=True)
    marker = PT / 'unpacked.ok'
    # review (pkgtest_runnet_review 1): the marker names the zip, so an older unpack is never tested by mistake
    if marker.exists() and LICHII.exists() and ZIP.name in marker.read_text(encoding='utf-8', errors='replace'):
        log(f'already unpacked: {PKG}')
    else:
        log(f'unpacking {ZIP.name} into {PT} ...')
        with zipfile.ZipFile(ZIP) as z:
            for info in z.infolist():
                target = (PT / info.filename).resolve()
                if PT not in target.parents and target != PT:
                    raise SystemExit(f'zip entry outside the scratch root: {info.filename}')
            z.extractall(PT)
            for info in z.infolist():
                if not info.is_dir() and (PT / info.filename).stat().st_size != info.file_size:
                    raise SystemExit(f'size mismatch after unpack: {info.filename}')
        marker.write_text(time.strftime('%F %T') + ' ' + ZIP.name, encoding='utf-8')
        log('unpacked')
    extract_launcher_tools()
    return 0


def extract_launcher_tools():
    """tools\\dusk_server and tools\\npln_server out of Play.Duskbloods.exe's PyInstaller archive (read only,
    nothing runs), then lan_fix_host.py's swap of frontend_api.py / npln_stub.py."""
    exe = PKG / 'Play.Duskbloods.exe'
    data = exe.read_bytes()
    cookie = data.rfind(b'MEI\x0c\x0b\x0a\x0b\x0e')
    if cookie < 0:
        raise SystemExit('Play.Duskbloods.exe: no PyInstaller archive found')
    _, length, toc, toc_len, _ = struct.unpack('!8sIIII', data[cookie:cookie + 24])
    start = len(data) - length
    table, o, n = data[start + toc:start + toc + toc_len], 0, 0
    while o < len(table):
        size, off, clen, ulen, flag, _ = struct.unpack('!IIIIBc', table[o:o + 18])
        name = table[o + 18:o + size].rstrip(b'\0').decode('utf-8', 'replace')
        o += size
        norm = name.replace('/', '\\')
        if not norm.startswith(('tools\\dusk_server\\', 'tools\\npln_server\\')) or '__pycache__' in norm:
            continue
        blob = data[start + off:start + off + clen]
        blob = zlib.decompress(blob) if flag else blob
        if len(blob) != ulen:
            raise SystemExit(f'bad archive entry {name}')
        out = MEI / Path(*norm.split('\\'))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
        n += 1
    for src, dst in (('frontend_api.py', 'dusk_server'), ('npln_stub.py', 'npln_server')):
        if not (MEI / 'tools' / dst).is_dir():
            raise SystemExit(f'launcher archive has no tools\\{dst}')
        shutil.copyfile(PKG / 'lan_fix' / src, MEI / 'tools' / dst / src)
    log(f'launcher tools: {n} files from Play.Duskbloods.exe into {MEI}; lan_fix frontend_api.py / npln_stub.py swapped in')


def files_state(folder):
    out = {}
    if folder.is_dir():
        for root, _dirs, names in os.walk(folder):
            for nm in names:
                p = Path(root) / nm
                try:
                    st = p.stat()
                    out[str(p)] = [st.st_size, st.st_mtime_ns]
                except OSError:
                    pass
    return out


def watched():
    """What must stay untouched: the user's eden config / log / save / nand folders, the launcher settings."""
    text = (SOURCE / 'config' / 'qt-config.ini').read_text(encoding='utf-8', errors='replace')
    nand, save = config_dir(text, 'nand_directory'), config_dir(text, 'save_directory')
    snap = {}
    for folder in [SOURCE / 'config', SOURCE / 'log', nand, save]:
        if folder:
            snap.update(files_state(folder))
    for f in [REAL_SETTINGS, SOURCE / 'nx2_switches.txt']:
        if f.exists():
            snap[str(f)] = [f.stat().st_size, f.stat().st_mtime_ns,
                            hashlib.sha1(f.read_bytes()).hexdigest()]
    snap['_exists'] = {n: (APPDATA / n).is_dir() for n in ('eden', 'lichii', 'eglantine', 'yuzu')}
    return snap


def config_dir(text, key):
    m = re.search(r'(?m)^' + re.escape(key) + r'=(.+)$', text)
    return Path(m.group(1).strip()) if m and m.group(1).strip() else None


def cmd_userdir():
    # Every full run takes a FRESH snapshot here (step 3, before any game starts): an old one (e.g. 14:57,
    # before the user played) made the untouched check fail wrongly at 17:28.
    MANIFEST.write_text(json.dumps(watched()), encoding='utf-8')
    log(f'snapshot of the user\'s data taken ({MANIFEST.name}, fresh for this run)')
    done = PT / 'userdir.ok'                            # F4: written only after a complete copy
    if USER.is_dir() and (USER / 'config' / 'qt-config.ini').exists() and done.exists():
        log(f'portable data folder already there: {USER}')
    else:
        if USER.exists():                                # a copy that stopped half way: start again
            shutil.rmtree(USER)                          # (inside the scratch root: PT guard above)
        sp = second_player_module()                     # its copy_tree (skip list) and set_key, unchanged
        copy_tree, set_key = sp.copy_tree, sp.set_key
        text = (SOURCE / 'config' / 'qt-config.ini').read_text(encoding='utf-8')
        log(f'copying {SOURCE} (read only) into the portable folder {USER} ...')
        USER.mkdir(parents=True, exist_ok=True)
        for name in COPY_DIRS:
            if (SOURCE / name).is_dir():
                copy_tree(SOURCE / name, USER / name)
        if (SOURCE / 'nx2_switches.txt').is_file():
            shutil.copy2(SOURCE / 'nx2_switches.txt', USER / 'nx2_switches.txt')
        nand = config_dir(text, 'nand_directory') or SOURCE / 'nand'
        save = config_dir(text, 'save_directory') or SOURCE / 'nand' / 'user' / 'save'
        for src, dst in ((nand, TEST / 'nand'), (save, TEST / 'save')):
            if src.is_dir():
                copy_tree(src, dst)
            else:
                dst.mkdir(parents=True, exist_ok=True)
        conf = USER / 'config' / 'qt-config.ini'
        text = conf.read_text(encoding='utf-8')
        # the launcher's prepare_config() keys, plus the folders second_player.py also re-points
        for key, value in (('nand_directory', (TEST / 'nand').as_posix()), ('save_directory', (TEST / 'save').as_posix()),
                           ('sdmc_directory', (USER / 'sdmc').as_posix()), ('load_directory', (USER / 'load').as_posix()),
                           ('dump_directory', (USER / 'dump').as_posix()),
                           ('airplane_mode', 'false'), ('use_gdbstub', 'false'), ('check_for_updates', 'false')):
            text = set_key(text, key, value)
        text = re.sub(r'(?m)^network_interface=.*$', 'network_interface=', text)
        text = re.sub(r'(?m)^network_interface\\default=.*$', r'network_interface\\default=true', text)
        conf.write_text(text, encoding='utf-8')
        done.write_text(time.strftime('%F %T'), encoding='utf-8')
        log('portable data folder ready')
    leak = [ln for ln in (USER / 'config' / 'qt-config.ini').read_text(encoding='utf-8').splitlines()
            if str(SOURCE).replace('\\', '/').lower() in ln.replace('\\', '/').lower()
            and re.match(r'^(nand|save|sdmc|load|dump)_directory=', ln)]
    if leak:
        log('  REFUSED: the copy still points into the user\'s folder: ' + '; '.join(leak))
        return 2
    # the scratch package's launcher_settings.json (second_player.py reads PKG\launcher_settings.json)
    try:
        real = json.loads(REAL_SETTINGS.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        real = {}
    shipped = PKG / 'launcher_settings.json'
    try:
        conf = json.loads(shipped.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        conf = {}
    conf['game'] = str(real.get('game') or GAME_DIR).replace('\\', '/')
    online = dict(conf.get('online') or {})
    online.update(mode='host', server=rig_ip(), password=PASSWORD)
    conf['online'] = online
    shipped.write_text(json.dumps(conf, indent=2), encoding='utf-8')
    log(f'scratch launcher_settings.json: game {conf["game"]}, room password set, host {rig_ip()}')
    return 0


def second_player_module():
    spec = importlib.util.spec_from_file_location('pkg_second_player', PKG / 'lan_fix' / 'second_player.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                        # definitions only; main() is not called
    return mod


def host_plus_module():
    spec = importlib.util.spec_from_file_location('pkg_host_plus', PKG / 'lan_fix' / 'host_plus.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- host side (headless)
def server_python():
    """System python (as the rig) or, PKGTEST_FROZEN=1, the launcher's own interpreter (--run-script)."""
    if os.environ.get('PKGTEST_FROZEN') == '1':
        return [str(PKG / 'Play.Duskbloods.exe'), '--run-script']
    return [sys.executable, '-u']


def cmd_serve():
    """Runs in the foreground until killed. pkgtest.sh starts it in the background as
    `pkgtest.py serve <scratch root>\\serve`: that argument puts the scratch path into its command line,
    so `stop` finds it by name."""
    hp = host_plus_module()
    ts = rig_tailscale()
    own = tailscale_ip4() if ts else hp.lan_ip()
    if ts and not own:
        log('RIG_NET=tailscale, but `tailscale ip -4` gives no 100.x address: sign in to Tailscale (Connected) '
            'yourself, then start again. Nothing started.')
        return 1
    # host_plus.py main(): 'tailscale' = guests' second games go in as 127.0.2.<k> (p2p_addr_map.txt)
    prefix = 'tailscale' if ts else '.'.join(own.split('.')[:3])
    for stale in (hp.MAP_FILE, hp.ADDRESS_FILE):        # host_plus.py main() clears both at its start too
        try:
            stale.unlink()
        except OSError:
            pass
    run = TEST / 'runs' / time.strftime('%Y%m%d_%H%M%S')
    (run / 'server_data').mkdir(parents=True, exist_ok=True)
    pki = TEST / 'pki'
    server_dir, front_dir = MEI / 'tools' / 'npln_server', MEI / 'tools' / 'dusk_server'
    if not (pki / 'ca.der').exists():
        made = subprocess.run(server_python() + [str(server_dir / 'make_pki.py'), '--out', str(pki)],
                              cwd=str(server_dir), capture_output=True, text=True)
        if made.returncode != 0 or not (pki / 'ca.der').exists():
            log('make_pki failed: ' + (made.stdout + made.stderr)[-400:])
            return 1
        log(f'scratch certificates made: {pki}')
    # lan_fix_host.py's defaults + host_plus.py's two variables
    env = dict(os.environ)
    env.update(DUSK_MATCH_WAIT='0', DUSK_TICKET_TTL='1.6', DUSK_P2P_FORMAT='self', DUSK_HOST_IP=own,
               DUSK_MATCH_HOLD='1', DUSK_WAIT_LONGPOLL='3600', DUSK_PANEL_PORT=str(PANEL_API),
               DUSK_PANEL_HTML=str(PKG / 'lan_fix' / 'panel.html'),
               # F1: frontend_api.py defaults both to %APPDATA%\eden\log (the user's own folder) and
               # v3.9.4 WRITES dusk_lan_match.txt there at every match; game 1's log folder instead
               # (also where its LobbyShare looks: next to its own dusk_lan_status.json).
               DUSK_STATUS_FILE=str(USER / 'log' / 'dusk_lan_status.json'),
               # v3.9.5 (lan_fix_host.py v403): the package's lan_fix folder, where both games read it
               DUSK_MATCH_FILE=str(PKG / 'lan_fix' / 'dusk_lan_match.txt'))
    if ts:
        # host_plus.py main() + lan_fix_host.py with Tailscale play: this PC's second game on 15501, guests'
        # second games 127.0.2.<k> (their 100.x from p2p_addr_map.txt), our 100.x advertised, TURN per address
        env['DUSK_P2P_PORTS'] = ','.join([f'{own}={hp.SECOND_P2P}'] + [f'127.0.2.{k}={hp.SECOND_P2P}' for k in range(1, 255)])
        env['DUSK_P2P_ADDR'] = ''
        env.update(DUSK_ADVERTISE_IP=own, DUSK_TAILSCALE='1', DUSK_P2P_ADDR_FILE=str(hp.MAP_FILE))
        hp.ADDRESS_FILE.write_text(own + '\n', encoding='utf-8')   # second_player.py signs in from it
    else:
        env['DUSK_P2P_PORTS'] = ','.join([f'{own}={hp.SECOND_P2P}'] + [f'127.0.1.{d}={hp.SECOND_P2P}' for d in range(1, 255)])
        env['DUSK_P2P_ADDR'] = ','.join(f'127.0.1.{d}={prefix}.{d}' for d in range(1, 255))
    keep = ('DUSK_MATCH_WAIT', 'DUSK_TICKET_TTL', 'DUSK_P2P_FORMAT', 'DUSK_HOST_IP', 'DUSK_MATCH_HOLD',
            'DUSK_WAIT_LONGPOLL', 'DUSK_PANEL_PORT', 'DUSK_PANEL_HTML', 'DUSK_P2P_PORTS', 'DUSK_P2P_ADDR',
            'DUSK_STATUS_FILE', 'DUSK_MATCH_FILE')
    if ts:
        keep += ('DUSK_ADVERTISE_IP', 'DUSK_TAILSCALE', 'DUSK_P2P_ADDR_FILE', 'DUSK_VPN_NET', 'DUSK_VPN_NAME')
    for k in [k for k in env if k.startswith('DUSK_') and k not in keep]:
        env.pop(k)                                       # no rig leftovers (DUSK_MATCH_MIN, DUSK_DEFAULT_ROOM ...)
    hosts = ['127.0.0.1'] + local_addresses()
    if ts:
        hosts = ['127.0.0.1', own] + [h for h in hosts[1:] if h != own]   # --nat-ip and the frontdoor's host = 100.x
    stub_args = ['--port', str(UPSTREAM), '--host', ','.join(hosts), '--web-port', str(WEB_PORT),
                 '--data', str(run / 'server_data'), '--pki', str(pki), '--log', str(run / 'server.log')]
    if len(hosts) > 1:
        stub_args += ['--nat-ip', hosts[1]]
    server = subprocess.Popen(server_python() + [str(server_dir / 'npln_stub.py')] + stub_args, cwd=str(server_dir),
                              env=env, stdout=(run / 'server_console.log').open('w'), stderr=subprocess.STDOUT)
    fenv = dict(env, DUSK_REDIRECT_VALUE='nochange', DUSK_FRONTEND='1', PYTHONUNBUFFERED='1', DUSK_ONLINE='1',
                DUSK_HOST_IP=hosts[1] if len(hosts) > 1 else '')
    front_args = ['--port', str(GAME_PORT), '--upstream', str(UPSTREAM), '--ca-dir', str(pki),
                  '--cert-dir', str(TEST / 'frontdoor_pki'), '--log', str(run / 'frontdoor.log'),
                  '--bind', '0.0.0.0', '--room-port', str(ROOM_PORT), '--room-name', 'pkgtest room']
    front = subprocess.Popen(server_python() + [str(front_dir / 'frontdoor.py')] + front_args, cwd=str(front_dir),
                             env=fenv, stdout=(run / 'frontdoor_console.log').open('w'), stderr=subprocess.STDOUT)
    save_state(serve_pid=os.getpid(), server_pid=server.pid, front_pid=front.pid, run=str(run), lan=own,
               host_ip=fenv['DUSK_HOST_IP'], rig_net='tailscale' if ts else 'lan')
    time.sleep(3)
    if server.poll() is not None or front.poll() is not None:
        log(f'a server stopped at start; see {run}')
        return 1
    for _ in range(20):
        try:
            http(f'http://127.0.0.1:{ROOM_PORT}/register', {'room': room_id(PASSWORD), 'bots': False})
            break
        except OSError:
            time.sleep(1)
    else:
        log('the room service did not answer')
        return 1
    log(f'servers up (npln_stub {server.pid}, frontdoor {front.pid}); room registered; host address {fenv["DUSK_HOST_IP"]}')
    for listen_port, target_port in ((hp.RELAY_GAME, hp.GAME_PORT), (hp.RELAY_ROOM, hp.ROOM_PORT)):
        threading.Thread(target=hp.relay, args=(listen_port, target_port, prefix, own), daemon=True).start()
    log(f'host_plus relay threads started (log {hp.LOG_FILE})')
    while server.poll() is None and front.poll() is None:
        time.sleep(2)
    log(f'a server ended (npln_stub {server.poll()}, frontdoor {front.poll()}); serve ends')
    return 1


def launcher_env(run, ca):
    """play_duskbloods.py Session.start(), mode host."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(('EDEN_NX2_', 'EDEN_NATIVE_', 'LICHII_'))}
    env.update(EDEN_NX2_DIAG_CODEC_CLIENT_REPLY='1', EDEN_NX2_EXPERIMENTAL_CODEC_DECODE='1',
               EDEN_NX2_EXPERIMENTAL_SYSMIX_OUTPUT='1', EDEN_NX2_SYSMIX_DRAIN_MULTIPLIER='1',
               EDEN_NX2_APP_POOL_PROBE='1152', EDEN_NX2_GPU_MAP_FLAG_PROBE='1', EDEN_NX2_SILENT_BAD_OPUS='1',
               EDEN_NX2_ONLINE_HOSTS='npln.srv.nintendo.net,npln.nintendo.net,n.n.srv.nintendo.net,'
                                     'p.srv.nintendo.net,fromsoftware-game.net',
               EDEN_NX2_ONLINE_SERVER=f'127.0.0.1:{GAME_PORT}', EDEN_NX2_ONLINE_CA=str(ca),
               EDEN_NX2_CRASH_DUMP=str(run), EDEN_NX2_TRACE_TERMINATE='1',
               EDEN_NX2_DEBUG_SERVER=f'127.0.0.1:{DEBUG["A"]}',   # passed through by the launcher
               LICHII_USER_DIR=str(USER))
    env.pop('SDL_AUDIODRIVER', None)
    if os.environ.get('PKGTEST_GDB_A'):   # test only: game A's gdb stub on this port (it then WAITS at boot for
        env['LICHII_GDBSTUB'] = os.environ['PKGTEST_GDB_A']   # a debugger: run diag/twin/gdb_go.py PORT right after)
    return env


def cmd_game1():
    sp = second_player_module()
    conf = json.loads((PKG / 'launcher_settings.json').read_text(encoding='utf-8'))
    main = sp.game_main(conf)
    if main is None:
        log(f'game not found ({conf.get("game")})')
        return 1
    run = TEST / 'runs' / ('game1_' + time.strftime('%Y%m%d_%H%M%S'))
    run.mkdir(parents=True, exist_ok=True)
    console = (run / 'console.log').open('w')
    game = subprocess.Popen([str(LICHII), '-g', str(main)], cwd=str(LICHII.parent), env=launcher_env(run, TEST / 'pki' / 'ca.der'),
                            stdout=console, stderr=subprocess.STDOUT)
    save_state(game1_pid=game.pid, game1_run=str(run))
    log(f'game 1 started (pid {game.pid}, debug 6545, data {USER}, main {main})')
    return 0


def cmd_game2():
    """As "Start second player.cmd": python <package>\\lan_fix\\second_player.py %*"""
    env = {k: v for k, v in os.environ.items() if not k.startswith(('EDEN_NX2_', 'LICHII_', 'TWIN_'))}
    r = subprocess.run([sys.executable, str(PKG / 'lan_fix' / 'second_player.py'), '--no-memory-check',
                        '--password', PASSWORD], cwd=str(PKG / 'lan_fix'), env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    print(out, end='')
    pid = re.findall(r'Second player started \(process (\d+)\)', out)
    if pid:
        save_state(game2_pid=int(pid[-1]))
    text = (SECOND / 'second_player_log.txt').read_text(encoding='utf-8', errors='replace') \
        if (SECOND / 'second_player_log.txt').exists() else ''
    want = ['Second player on the host PC: sign-in ' + rig_ip() + ':18443', 'Room joined', 'Second player started']
    miss = [w for w in want if w not in text]
    log('second_player.py exit %d; log %s' % (r.returncode, 'has all expected lines' if not miss else 'MISSING: ' + ' | '.join(miss)))
    return 0 if r.returncode == 0 and not miss else 1


# ---------------------------------------------------------------- checks
def panel():
    return json.loads(http(f'http://127.0.0.1:{PANEL_API}/api/state', timeout=5))


def rows_ok(st, lan):
    ips = {r['ip'] for r in st.get('players', [])}
    return '127.0.0.1' in ips and lan in ips, ips


def cmd_rows():
    lan = rig_ip()
    deadline = time.time() + float(os.environ.get('PKGTEST_ROWS_WAIT', '180'))
    ips = set()
    while time.time() < deadline:
        try:
            ok, ips = rows_ok(panel(), lan)
            if ok:
                log(f'panel: two rows, 127.0.0.1 and {lan}: PASS ({sorted(ips)})')
                return 0
        except (OSError, ValueError):
            pass
        time.sleep(5)
    log(f'panel rows: FAIL (seen {sorted(ips)}, want 127.0.0.1 and {lan})')
    return 1


def autostart(stop):
    """The host person's Start match, once both games search (hold mode)."""
    while not stop.is_set():
        try:
            st = panel()
            searching = [r for r in st['players'] if r.get('kind') == 'search']
            if len(searching) >= 2 and not st['server'].get('starting'):
                http(f'http://127.0.0.1:{PANEL_API}/api/start', {})
                log('panel: Start match pressed (both rows searching)')
                return
        except (OSError, ValueError, KeyError):
            pass
        stop.wait(2)


def cmd_run(argv):
    """Rig tool with its log / config paths pointed at the pkgtest games (the tools stay unchanged)."""
    auto = '--autostart' in argv
    argv = [a for a in argv if a != '--autostart']
    script = (WS / argv[0]).resolve()
    os.chdir(WS)                                         # the rig tools use workspace-relative paths
    os.environ['TWIN_GAMES'] = 'AB'
    sys.path.insert(0, str(HERE))
    import lanlog
    import screen
    lanlog.LAN.update(A=str(USER / 'log' / 'dusk_lan.txt'), B=str(SECOND / 'user' / 'log' / 'dusk_lan.txt'))
    lanlog.WATCH.update(A=str(PT / 'no_watch_A.log'), B=str(PT / 'no_watch_B.log'))   # no stale rig watcher logs
    screen.config_path = lambda who: str((USER if who == 'A' else SECOND / 'user') / 'config' / 'qt-config.ini')
    # the same paths for every tool the script starts as a child process (RS.tool, subprocess): lanlog / screen
    # read these at import. Without them a child tool took main base from the rig's old logs (deep_audit_K 1).
    for w in 'AB':
        os.environ['TWIN_LAN_' + w] = lanlog.LAN[w]
        os.environ['TWIN_WATCH_' + w] = lanlog.WATCH[w]
        os.environ['TWIN_CONFIG_' + w] = screen.config_path(w)
    stop = threading.Event()
    if auto:
        threading.Thread(target=autostart, args=(stop,), daemon=True).start()
    sys.argv = [str(script)] + argv[1:]
    import runpy
    code = 0
    try:
        runpy.run_path(str(script), run_name='__main__')
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        stop.set()
    return code


def lan_log(who):
    p = USER / 'log' / 'dusk_lan.txt' if who == 'A' else SECOND / 'user' / 'log' / 'dusk_lan.txt'
    try:
        return p.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def cmd_check():
    lan = rig_ip()
    deadline = time.time() + float(os.environ.get('PKGTEST_MATCH_WAIT', '240'))
    result = {}
    while time.time() < deadline:
        result = {}
        for w in 'AB':
            t = lan_log(w)
            nos = re.findall(r'player no (\d+) team', t)
            result[w] = {'joined': 'joined a LAN session' in t, 'no': nos[-1] if nos else None,
                         'peer_ping': bool(re.search(r'peer player \d+: ping', t))}
        if all(r['joined'] and r['no'] and r['peer_ping'] for r in result.values()) \
                and {result['A']['no'], result['B']['no']} == {'1', '2'}:
            break
        time.sleep(10)
    try:
        st = panel()
        ok_rows, ips = rows_ok(st, lan)
        nos = {r['ip']: r.get('player_no') for r in st['players']}
        matches = st.get('matches', [])
    except (OSError, ValueError):
        ok_rows, ips, nos, matches = False, set(), {}, []
    ok_logs = all(r.get('joined') and r.get('peer_ping') for r in result.values()) and \
        {result.get('A', {}).get('no'), result.get('B', {}).get('no')} == {'1', '2'}
    log(f'dusk_lan: A {result.get("A")} | B {result.get("B")}')
    log(f'panel: addresses {sorted(ips)}, player numbers {nos}, matches {[m["players"] for m in matches]}')
    hp = PKG / 'lan_fix' / 'host_plus_log.txt'
    hp_text = hp.read_text(encoding='utf-8', errors='replace') if hp.exists() else ''
    relay_ok = all(f'relay {p} -> 127.0.0.1:{q} ready' in hp_text for p, q in ((RELAY_GAME, GAME_PORT), (RELAY_ROOM, ROOM_PORT)))
    log(f'host_plus relays 18453 / 18455 ready: {"yes" if relay_ok else "NO"}')
    verdict = ok_rows and ok_logs and relay_ok
    log('MATCH CHECK: ' + ('PASS (two rows 127.0.0.1 + %s, players 1 and 2, peer pings)' % lan if verdict else 'FAIL'))
    save_state(match_check='PASS' if verdict else 'FAIL')
    return 0 if verdict else 1


def cmd_untouched():
    try:
        before = json.loads(MANIFEST.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        log('no snapshot to compare with')
        return 1
    now = watched()
    changed = [k for k in before if k != '_exists' and before[k] != now.get(k)]
    added = [k for k in now if k not in before and k != '_exists']
    if before.get('_exists') != now.get('_exists'):
        changed.append(f'APPDATA folders {before.get("_exists")} -> {now.get("_exists")}')
    for k in (changed + added)[:20]:
        log('  CHANGED: ' + k)
    log('user data untouched: ' + ('PASS' if not changed and not added else f'FAIL ({len(changed)} changed, {len(added)} new)'))
    return 0 if not changed and not added else 1


def cmd_waitdebug(who):
    sys.path.insert(0, str(HERE))
    from tctl import call
    deadline = time.time() + float(os.environ.get('PKGTEST_BOOT_WAIT', '420'))
    while time.time() < deadline:
        try:
            r = call(who, {'method': 'status'})
            if r.startswith('{') and 'error' not in r[:40].lower():
                log(f'{who}: debug server answers on {DEBUG[who]}')
                return 0
        except Exception:
            pass
        time.sleep(15)
    log(f'{who}: debug server on {DEBUG[who]} did not answer')
    return 1


def cmd_stop():
    victims = [p for p in processes() if ours(p)]
    for p in victims:
        log(f'stopping pid {p["ProcessId"]} {p.get("Name")}')
        subprocess.run(['taskkill', '/PID', str(p['ProcessId']), '/T', '/F'], capture_output=True)
    time.sleep(2)
    left = [p for p in processes() if ours(p)]
    log('stop: %d stopped, %d left' % (len(victims), len(left)))
    return 0 if not left else 1


def cmd_clean():
    if PT.name != 'pkgtest' or PT.parent != HERE:
        log(f'clean refused: {PT} is not diag\\twin\\pkgtest')
        return 2
    if cmd_stop() != 0:
        log('clean refused: processes still run')
        return 1
    shutil.rmtree(PT, ignore_errors=False)
    print(f'deleted {PT}')
    return 0


def main(argv):
    cmd, rest = (argv[0], argv[1:]) if argv else ('', [])
    table = {'precheck': cmd_precheck, 'unpack': cmd_unpack, 'userdir': cmd_userdir, 'serve': cmd_serve,
             'game1': cmd_game1, 'game2': cmd_game2, 'rows': cmd_rows, 'check': cmd_check,
             'untouched': cmd_untouched, 'stop': cmd_stop, 'clean': cmd_clean}
    if cmd in table:
        return table[cmd]()
    if cmd == 'waitdebug':
        return cmd_waitdebug(rest[0])
    if cmd == 'run':
        return cmd_run(rest)
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
