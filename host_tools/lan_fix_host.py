r"""LAN online host with the battle-connection fix (2026-11-11) and the host panel (2026-11-13).

Starts Play.Duskbloods.exe like 'Play Online Host.cmd' and swaps the launcher's built-in match server
(frontend_api.py, unpacked to %TEMP%\_MEI*\tools\dusk_server\ at launch) for the fixed copy next to
this script, before you press Play, and the NPLN stub (npln_stub.py) for the game session. The fix: MATCHED now carries the 32-byte p2p_host_info record the
game accepts. Since v2.5 every player gets its OWN address as the "game server" (mode 'self'), so the
match can have more than two players; the players reach each other over their direct links.

Host panel: this script opens its own window at once (Edge or Chrome in app mode, else the default
browser) on http://127.0.0.1:18450 and serves the page (panel.html) itself; the data comes from the
match server (frontend_api.py, port 18451), which only exists after Start game is pressed in the
launcher. The script stays open while the launcher runs.
Only the hosting PC runs this; the other PC joins as before."""
import glob, json, os, shutil, socket, subprocess, sys, threading, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXE = HERE.parent / 'Play.Duskbloods.exe'
PANEL_PORT = int(os.environ.get('DUSK_PANEL_WINDOW_PORT', '18450'))   # the page (this script)
API_PORT = PANEL_PORT + 1                                              # the match server's panel API
LOG_FILE = HERE / 'host_log.txt'
_print = print


def print(*args, **kwargs):
    """N7: what this window says also goes to lan_fix\\host_log.txt (Collect logs takes it), so a
    failed server swap ("Could not find the launcher files") is known after the evening."""
    _print(*args, **kwargs)
    try:
        with LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + ' '.join(str(a) for a in args) + '\n')
    except OSError:
        pass


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


class Panel(BaseHTTPRequestHandler):
    """The page, plus /api/* passed on to the match server (503 while it is not running yet)."""

    def log_message(self, *args):
        pass

    def _send(self, code, data, kind='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _forward(self, body=None):
        request = urllib.request.Request('http://127.0.0.1:%d%s' % (API_PORT, self.path), data=body,
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=3) as reply:
                self._send(reply.status, reply.read())
        except (OSError, urllib.error.URLError):
            self._send(503, json.dumps({'error': 'server not running', 'host_ip': HOST_IP}).encode())

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self._forward()
        if self.path in ('/', '/index.html'):
            return self._send(200, (HERE / 'panel.html').read_bytes(), 'text/html; charset=utf-8')
        self._send(404, b'{}')

    def do_POST(self):
        self._forward(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')


def open_window(url):
    """A window of its own without browser buttons (app mode); the default browser if neither
    Edge nor Chrome is installed."""
    roots = [os.environ.get(name, '') for name in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')]
    for tail in (r'Microsoft\Edge\Application\msedge.exe', r'Google\Chrome\Application\chrome.exe'):
        for root in roots:
            path = os.path.join(root, tail)
            if root and os.path.exists(path):
                # Its own small browser profile: always a separate window of this size, also when
                # the browser is already open with other tabs.
                profile = os.path.join(os.environ.get('LOCALAPPDATA', str(HERE)), 'DuskbloodsHostPanel')
                subprocess.Popen([path, '--app=' + url, '--window-size=1180,860', '--user-data-dir=' + profile,
                                  '--no-first-run', '--no-default-browser-check'])
                return
    import webbrowser
    webbrowser.open(url)


env = dict(os.environ)
env.setdefault('DUSK_MATCH_WAIT', '0')
env.setdefault('DUSK_TICKET_TTL', '1.6')
# 'self' (v2.5): every player's "game server" address is its own game, so a match is not limited
# to two players. 'cross' = the old 1v1 pairing (each player gets the other's address).
env.setdefault('DUSK_P2P_FORMAT', 'self')
if not env.get('DUSK_HOST_IP'):                # N2: only worked out when not given
    env['DUSK_HOST_IP'] = lan_ip()
HOST_IP = env['DUSK_HOST_IP']
# tailscale_support.diff: the launcher sets DUSK_HOST_IP for its own match server itself (its
# first private address, play_duskbloods.py start_servers; with Tailscale connected that can be
# the 100.x one even for a home match), so this script's choice goes on as DUSK_ADVERTISE_IP,
# which frontend_api.py and npln_stub.py read first (on this PC today both are 192.168.1.11).
# Tailscale play: every player, home PCs too, joins with this PC's Tailscale address;
# DUSK_TAILSCALE turns on the per-address TURN relay and the panel's "not on Tailscale" warning.
TAILSCALE = tailscale_mode() or in_tailscale(HOST_IP)
if tailscale_mode() and not in_tailscale(HOST_IP):
    print('Tailscale play is switched on, but this PC has no Tailscale address (100.x).')
    print('Open Tailscale, sign in, wait until it says Connected, then start this file again.')
    sys.exit(1)
env['DUSK_ADVERTISE_IP'] = HOST_IP
if TAILSCALE:
    env['DUSK_TAILSCALE'] = '1'
# DUSK_MATCH_HOLD=1: players keep searching until the host presses Start match (0 = automatic).
# DUSK_WAIT_LONGPOLL: seconds the server holds back each "still waiting" answer; the game gives up
# after 4 of them in a row, so this is what keeps a search alive.
env.setdefault('DUSK_MATCH_HOLD', '1')
env.setdefault('DUSK_WAIT_LONGPOLL', '3600')
env.setdefault('DUSK_PANEL_PORT', str(API_PORT))
env.setdefault('DUSK_PANEL_HTML', str(HERE / 'panel.html'))
# v403: the match server writes the lobby size into the package (lan_fix\dusk_lan_match.txt), where
# every game started from this package finds it (assist LobbyShare), whatever its data folder.
env.setdefault('DUSK_MATCH_FILE', str(HERE / 'dusk_lan_match.txt'))
# HOST IS PLAYER 1 (2026-11-21): the game sorts the players by the 12-digit code of the emulator's online
# profile; the lowest is player 1, who owns the match clock and drives the bosses. The host's own game
# signs in with a host profile that has a low code (lan_fix\host_profile, made here once; the player's
# normal profile is not touched), so the hosting PC is always player 1. Proven live on 2026-11-21.
# Off: DUSK_HOST_FIRST=0, or set EDEN_NX2_ONLINE_PROFILES yourself.
if os.environ.get('DUSK_HOST_FIRST', '1') != '0' and 'EDEN_NX2_ONLINE_PROFILES' not in env:
    try:
        import secrets
        _profiles = HERE / 'host_profile'
        _profiles.mkdir(exist_ok=True)
        _profile = _profiles / '127.0.0.1_18443.txt'      # the host's game reaches its own server at this address
        if not _profile.exists():
            _profile.write_text('server=127.0.0.1:18443\ncode=000016777217\nsecret=%s\nfriends=\nremoved=\n'
                                % secrets.token_hex(16), encoding='ascii', newline='\n')
        env['EDEN_NX2_ONLINE_PROFILES'] = str(_profiles)
        print('Host profile in use: this PC is player 1 of its matches (lan_fix\\host_profile).')
    except OSError as error:
        print('Host profile not set up (%s): the player number follows the normal profile.' % error)
# Optional (panel details for a portable first game; read only): the first game's status file.
if (HERE.parent / 'Lichii' / 'user').is_dir():
    env.setdefault('DUSK_STATUS_FILE', str(HERE.parent / 'Lichii' / 'user' / 'log' / 'dusk_lan_status.json'))
print('LAN address of this PC:', HOST_IP, '| p2p format:', env['DUSK_P2P_FORMAT'])
if TAILSCALE:
    print('TAILSCALE PLAY: every player joins with', HOST_IP, '- home PCs too. Each player must be signed in')
    print('to Tailscale and see this PC (tailscale status). Players who join with a home address cannot')
    print('play with the remote players (the panel marks them "NOT on Tailscale").')
_others = [a for a in lan_ip_candidates() if a != HOST_IP]
if _others and not TAILSCALE:
    print('This PC also has the address(es)', ', '.join(_others), '(VPN, ZeroTier, a second adapter).',
          'The others must join with', HOST_IP, '- if that is not the home network address, write the right',
          'one into lan_fix\\lan_ip.txt and start again (READ ME FIRST.txt, "VPN").')
temp = os.environ.get('TEMP') or os.environ.get('TMP') or '.'
before = set(glob.glob(os.path.join(temp, '_MEI*')))
# QUIC P2P diagnostics (2026-11-11): lichii's gdbstub on (LICHII_GDBSTUB) plus the watcher that
# releases the start pause and logs peer matching to diag/net/quic_watch.log. Off by default since
# 2026-11-12: the LAN battle code is in lichii.exe now (twin tests 33-39 ran without it). DUSK_QUIC_WATCH=1 = on.
WATCH = HERE.parents[1] / 'diag' / 'net' / 'quic_watch.py'
if env.get('DUSK_QUIC_WATCH', '0') == '1' and WATCH.exists():
    env['LICHII_GDBSTUB'] = '6543'
    subprocess.Popen([sys.executable, str(WATCH)], cwd=str(HERE.parents[1]),
                     creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
    print('QUIC watcher started (log: diag/net/quic_watch.log)')

try:
    panel = ThreadingHTTPServer(('127.0.0.1', PANEL_PORT), Panel)
    panel.daemon_threads = True
    threading.Thread(target=panel.serve_forever, daemon=True).start()
    open_window('http://127.0.0.1:%d/' % PANEL_PORT)
    print('Host panel: http://127.0.0.1:%d/' % PANEL_PORT)
except OSError as error:
    print('Host panel not started (port %d busy: %s). Is another host launcher still open?' % (PANEL_PORT, error))

# a frozen launcher started from a frozen launcher must unpack its OWN files (PyInstaller would reuse the
# parent's temp folder: 'Failed to remove temporary directory', and the server swap finds no new folder)
launcher = subprocess.Popen([str(EXE)], cwd=str(EXE.parent), env=dict(env, PYINSTALLER_RESET_ENVIRONMENT='1'))
deadline = time.time() + 120
patched = False
while time.time() < deadline and not patched:
    for d in set(glob.glob(os.path.join(temp, '_MEI*'))) - before:
        target = Path(d) / 'tools' / 'dusk_server' / 'frontend_api.py'
        if target.exists():
            time.sleep(0.5)                    # let the unpacker finish the file
            shutil.copyfile(HERE / 'frontend_api.py', target)
            stub = Path(d) / 'tools' / 'npln_server' / 'npln_stub.py'
            if stub.exists():
                shutil.copyfile(HERE / 'npln_stub.py', stub)   # pairs the empty-name JoinGameSession
            print('Fixed match server installed:', target)
            print('Fixed session server installed:', stub)
            print('Now pick Online / host in the launcher and press Start game.')
            patched = True
            break
    time.sleep(0.2)
if not patched:
    print('Could not find the launcher files to patch (no new _MEI folder in %s).' % temp)
print('Keep this window open: it serves the host panel. It closes with the launcher.')
launcher.wait()
