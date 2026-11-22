"""The window.

The launcher's face is one page (ui/index.html) shown in a window of its own: Edge or Chrome in "app"
mode, which every Windows 10/11 PC has; the default browser otherwise. This module serves that page to
this PC only (127.0.0.1, a random port, a random key in the address) and does what its buttons ask:

    GET  /<key>/              the page
    GET  /<key>/background    a picture the player put beside the launcher (background.jpg / .png), if any
    GET  /<key>/api/state     everything the page shows, as JSON (asked about once a second)
    POST /<key>/api/do        one action: {"action": "...", ...}

The host's match controls (players, Start match, cancel, messages) are handed on to the match server's
panel service on this PC; the host's match tools are in hosttools.py.
"""
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import APP_NAME, ROLE, ROLE_MODES, VERSION, checks, config, game, network, support
from .session import Session

INSTANCE_FILE = config.BASE / 'db_launcher_window.json'     # the open window's address, for a second start
SETTINGS_FROM_PAGE = ('player_name', 'password', 'room_name', 'host_address', 'network')
PAGE_GONE_AFTER = 15         # seconds without a question from the page = the window was closed
BACKGROUNDS = (('background.jpg', 'image/jpeg'), ('background.png', 'image/png'))


class Launcher:
    """What the page shows and what its buttons do. Every public method may be called from any thread."""

    def __init__(self):
        self.settings = config.load()
        self.lock = threading.RLock()
        self.mode = self.settings['mode'] if self.settings['mode'] in ROLE_MODES else ROLE_MODES[0]
        self.results, self.found, self.checking = [], {}, False
        self.session, self.starting, self.session_mode = None, False, ''
        self.lines = []                       # the message log: [{'time', 'text', 'error'}]
        self.rooms = {'network': '', 'searching': False, 'list': [], 'looked': 0, 'done': 0, 'total': 0}
        self.search_run = 0
        self.pings = {}                       # address -> (time, ms) measured from this PC
        self.tools, self.tools_state = None, None
        self.last_question = time.time() + 45     # time for the window to open the first time
        self.quit = threading.Event()
        self.recheck()
        if 'join' in ROLE_MODES and self.settings.get('network'):
            self.search(self.settings['network'])       # the network picked last time
        threading.Thread(target=self._watch, daemon=True).start()

    # --- messages ------------------------------------------------------------------------------

    def log(self, text, error=False):
        config.note(('! ' if error else '') + text)
        with self.lock:
            self.lines.append({'time': time.time(), 'text': text.rstrip(), 'error': bool(error)})
            del self.lines[:-400]

    # --- the health check ------------------------------------------------------------------------

    def recheck(self):
        with self.lock:
            if self.checking:
                return
            self.checking = True
        settings, mode = dict(self.settings), self.mode

        def work():
            try:
                results, found = checks.run_all(settings, mode)
                self._keep_checks(results, found)
            finally:
                self.checking = False
        threading.Thread(target=work, daemon=True).start()

    def _keep_checks(self, results, found):
        with self.lock:
            self.results, self.found = results, found

    def _networks(self):
        return list(self.found.get('networks') or [])

    def _network(self, name):
        nets = self._networks()
        return next((n for n in nets if n['name'] == name), None)

    # --- the state the page draws ----------------------------------------------------------------

    def state(self, log_from=0):
        self.last_question = time.time()
        with self.lock:
            session = self.session
            running = session is not None and session.running
            fails = sum(r.level == checks.FAIL for r in self.results)
            warns = sum(r.level == checks.WARN for r in self.results)
            state = {
                'app': APP_NAME, 'version': VERSION, 'role': ROLE, 'modes': list(ROLE_MODES), 'mode': self.mode,
                'settings': {k: self.settings.get(k, '') for k in SETTINGS_FROM_PAGE},
                'checks': {'busy': self.checking and not self.results, 'fails': fails, 'warns': warns,
                           'items': [{'key': r.key, 'level': r.level, 'title': r.title, 'detail': r.detail,
                                      'fix': r.fix} for r in self.results]},
                'networks': [{'name': n['name'], 'kind': n['kind'], 'ip': n['ip'], 'public': n['public']}
                             for n in self._networks()],
                'session': {'state': 'running' if running else 'starting' if self.starting else 'idle',
                            'mode': self.session_mode,
                            'address': session.room.address if running and session.room is not None else ''},
                'rooms': dict(self.rooms, list=list(self.rooms['list'])),
                'log': self.lines[log_from:], 'log_next': len(self.lines),
                'background': any((config.BASE / name).is_file() for name, _kind in BACKGROUNDS),
                'room': None, 'tools': None,
            }
        if running and self.session_mode == 'host':
            state['room'] = self._room_state()
            state['tools'] = self.tools_state
        return state

    def _room_state(self):
        """The match server's own picture of the room, with this PC's fresh ping to every player added."""
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{config.PANEL_API_PORT}/api/state', timeout=2) as reply:
                room = json.loads(reply.read())
        except (OSError, ValueError):
            return {'offline': True}
        now = time.time()
        for row in room.get('players', []):
            mine = self.pings.get(row.get('ip'))
            row['net_ms'] = mine[1] if mine and now - mine[0] < 5 else None
        return room

    # --- background work ---------------------------------------------------------------------------

    def _watch(self):
        """Once a second: ping the room's players and ask the host tools for their picture; close the
        launcher when its window is gone and no game is running."""
        while not self.quit.is_set():
            time.sleep(1)
            session = self.session
            running = session is not None and session.running
            if running and self.session_mode == 'host':
                self._ping_players()
                tools = self.tools
                if tools is not None:
                    try:
                        self.tools_state = tools.status()
                    except Exception as error:          # the tools must never take the launcher down
                        self.tools_state = {'connected': False, 'error': repr(error)}
            if not running and not self.starting and time.time() - self.last_question > PAGE_GONE_AFTER:
                self.quit.set()

    def _ping_players(self):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{config.PANEL_API_PORT}/api/state', timeout=2) as reply:
                players = json.loads(reply.read()).get('players', [])
        except (OSError, ValueError):
            return
        for row in players:
            ip = row.get('ip', '')
            if row.get('local') or not ip or ip.startswith('127.'):
                continue
            threading.Thread(target=lambda ip=ip: self.pings.__setitem__(ip, (time.time(), network.ping(ip))),
                             daemon=True).start()

    # --- finding rooms -------------------------------------------------------------------------------

    def search(self, name):
        """Keep looking for rooms on the named network until another network is picked or a game starts."""
        with self.lock:
            self.search_run += 1
            run = self.search_run
            self.settings['network'] = name
            self.rooms = {'network': name, 'searching': bool(name), 'list': [], 'looked': 0, 'done': 0, 'total': 0}
        config.save(self.settings)
        if not name:
            return

        def work():
            while run == self.search_run and not self.quit.is_set():
                nets = network.networks()
                net = next((n for n in nets if n['name'] == name), None)
                if net is None:
                    rooms = []
                else:
                    def progress(done, total):
                        if run == self.search_run:
                            self.rooms.update(done=done, total=total)
                    rooms = network.find_rooms([net], progress)
                if run != self.search_run:
                    return
                with self.lock:
                    self.rooms.update(list=rooms, looked=self.rooms['looked'] + 1, connected=net is not None)
                for _wait in range(8):                     # look again every 4 seconds
                    if run != self.search_run or self.session is not None or self.starting:
                        break
                    time.sleep(0.5)
                while (self.session is not None or self.starting) and run == self.search_run:
                    time.sleep(1)                          # no searching while a game runs
        threading.Thread(target=work, daemon=True).start()

    # --- playing -----------------------------------------------------------------------------------

    def play(self, mode, address=''):
        if mode not in ROLE_MODES:
            return False, f'{APP_NAME} cannot do that: use the other launcher.'
        with self.lock:
            if self.session is not None or self.starting:
                return False, 'A game is already running.'
            self.starting, self.session_mode, self.mode = True, mode, mode
            if address:
                self.settings['host_address'] = address
            self.settings['mode'] = mode
            settings = dict(self.settings)
        config.save(settings)
        net = None
        if mode == 'host':
            net = self._network(settings.get('network', '')) or next(iter(self._networks()), None)
            settings['host_network'] = net['name'] if net else ''
        session = Session(settings, mode, net, self.log, self._keep_checks)
        threading.Thread(target=self._run, args=(session, mode), daemon=True).start()
        return True, ''

    def _run(self, session, mode):
        try:
            session.start()
        except game.StartError as error:
            self.log(str(error), error=True)
            self.starting = False
            return
        except Exception as error:                 # anything unforeseen: say it; Session left nothing running
            self.log(f'Could not start: {error!r}', error=True)
            self.starting = False
            return
        with self.lock:
            self.session, self.starting = session, False
        if mode == 'host':
            self._start_tools()
        session.wait()
        self._stop_tools()
        with self.lock:
            self.session = None
        self.recheck()

    def stop(self):
        session = self.session
        if session is not None:
            self._stop_tools()
            session.stop()

    # --- the host's match controls and tools -----------------------------------------------------------

    def room_do(self, what, body):
        """Hand a host action on to the match server. Only these four exist; 'settings' may change the
        minimum number of players and nothing else, so a match can never be set to start by itself."""
        if self.session is None or self.session_mode != 'host':
            return False, 'No room is open.'
        if what == 'settings':
            body = {'min_players': int(body.get('min_players', 2))}
        elif what == 'stop_searches':
            what, body = 'cancel', {'searches': True}
        elif what == 'cancel':
            body = {}
        elif what == 'say':
            body = {'text': str(body.get('text', ''))[:60], 'target': int(body.get('target') or 0)}
        elif what == 'start':
            body = {}
        else:
            return False, 'Unknown action.'
        request = urllib.request.Request(f'http://127.0.0.1:{config.PANEL_API_PORT}/api/{what}',
                                         data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=4) as reply:
                answer = json.loads(reply.read() or b'{}')
        except urllib.error.HTTPError as error:
            try:
                answer = json.loads(error.read() or b'{}')
            except ValueError:
                answer = {}
            return False, answer.get('error') or f'The match server said no ({error.code}).'
        except (OSError, ValueError):
            return False, 'The match server did not answer.'
        if what == 'start':
            self.log('You pressed START MATCH.')
        return True, answer.get('text', '')

    def _start_tools(self):
        try:
            from .hosttools import HostTools
            ready = self.session.ready if self.session is not None else None
            last = ['']

            def tool_log(text):                 # the once-a-second look must not fill the messages
                if text.startswith('status:') or text == last[0]:
                    return
                last[0] = text
                self.log('Host tools: ' + text)
            self.tools = HostTools(port=config.TOOLS_PORT, log=tool_log,
                                   data_dir=ready['data'] if ready else None)
        except Exception as error:
            self.tools = None
            self.log(f'Host tools are not available in this copy ({error!r}).')

    def _stop_tools(self):
        tools, self.tools, self.tools_state = self.tools, None, None
        if tools is not None:
            try:
                tools.close()
            except Exception:
                pass

    def tool(self, name, body):
        tools = self.tools
        if tools is None:
            return False, 'The host tools work only while you host a match.'
        try:
            if name == 'heal':
                return tools.heal()
            if name == 'no_death':
                return tools.set_no_death(bool(body.get('on')))
            if name == 'teleport':
                return tools.teleport_to_player(int(body.get('number') or 0))
            if name == 'clock':
                return tools.hold_clock(bool(body.get('on')))
            if name == 'boss':
                hp = body.get('hp')
                return tools.hold_boss(bool(body.get('on')), int(hp) if hp not in (None, '') else None)
        except Exception as error:
            return False, f'The tool failed: {error!r}'
        return False, 'Unknown tool.'

    # --- small helpers behind the bottom buttons ---------------------------------------------------------

    def choose_game(self):
        """A folder dialog (the one native window this launcher opens)."""
        try:
            import tkinter
            from tkinter import filedialog
            root = tkinter.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(parent=root, title='The game folder (it holds exefs and romfs)')
            root.destroy()
        except Exception as error:
            return False, f'The folder window could not open ({error!r}).'
        if not folder:
            return True, ''
        main = config.game_main_in(folder)
        if not main:
            return False, 'That folder has no exefs\\main and romfs. Pick the folder of your unpacked game.'
        self.settings['game'] = str(main)
        config.save(self.settings)
        self.recheck()
        return True, 'Game folder set.'

    def open_keys(self):
        emulator = config.find_emulator(self.settings.get('emulator', ''))
        if not emulator:
            return False, 'No emulator found yet.'
        keys = config.data_dir(emulator) / 'keys'
        keys.mkdir(parents=True, exist_ok=True)
        os.startfile(str(keys))
        return True, ''

    def save_logs(self):
        path = support.save(self.found.get('data'), self.results)
        if not path:
            return False, 'No game logs yet (play a match first).'
        self.log(f'Logs saved: {path}\nThey hold player names and local network addresses; share them only '
                 'with whoever helps you.')
        return True, f'Saved: {path.name}'

    def send_logs(self):
        host = network.split_address(self.settings.get('host_address', ''))[0]
        if not host:
            return False, 'Join a room once first: the logs go to that host PC.'
        try:
            answer = support.send_to_host(host, self.found.get('data'), self.results)
        except OSError as error:
            return False, f'Sending failed: {error}. "Save logs" writes a file instead.'
        self.log(f'Logs received by the host PC ({answer}). They went only there.')
        return True, 'Sent to the host PC.'

    # --- one action from the page ------------------------------------------------------------------------

    def do(self, body):
        action = body.get('action', '')
        if action == 'set':
            with self.lock:
                for key in SETTINGS_FROM_PAGE:
                    if key in body:
                        self.settings[key] = str(body[key])[:120]
            config.save(self.settings)
            return True, ''
        if action == 'mode':
            if body.get('mode') in ROLE_MODES:
                self.mode = self.settings['mode'] = body['mode']
                config.save(self.settings)
                self.recheck()
            return True, ''
        if action == 'recheck':
            self.recheck()
            return True, ''
        if action == 'search':
            self.search(str(body.get('network', '')))
            return True, ''
        if action == 'join':
            return self.play('join', str(body.get('address', '')).strip())
        if action == 'play':
            return self.play(str(body.get('mode', '')))
        if action == 'stop':
            self.stop()
            return True, ''
        if action == 'room':
            return self.room_do(str(body.get('what', '')), body)
        if action == 'tool':
            return self.tool(str(body.get('name', '')), body)
        simple = {'choose_game': self.choose_game, 'open_keys': self.open_keys, 'save_logs': self.save_logs,
                  'send_logs': self.send_logs}
        if action in simple:
            return simple[action]()
        return False, 'Unknown action.'


def serve(launcher):
    """Start the page's server on a free port of this PC. Returns (server, address of the page)."""
    key = secrets.token_urlsafe(12)
    page = (config.BUNDLE if config.FROZEN else Path(__file__).resolve().parents[1]) / 'ui' / 'index.html'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _send(self, code, body, kind='application/json'):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def _path(self):
            """The part after the key, or None when the key is wrong or the caller is not this PC's page."""
            host = (self.headers.get('Host') or '').split(':')[0]
            prefix = f'/{key}/'
            if host not in ('127.0.0.1', 'localhost') or not self.path.startswith(prefix):
                return None
            return self.path[len(prefix):]

        def do_GET(self):
            path = self._path()
            if path is None:
                return self._send(404, {})
            if path == '':
                return self._send(200, page.read_bytes(), 'text/html; charset=utf-8')
            if path.startswith('api/state'):
                try:
                    start = int(path.partition('log=')[2] or 0)
                except ValueError:
                    start = 0
                return self._send(200, launcher.state(start))
            if path == 'background':
                for name, kind in BACKGROUNDS:
                    if (config.BASE / name).is_file():
                        return self._send(200, (config.BASE / name).read_bytes(), kind)
            self._send(404, {})

        def do_POST(self):
            if self._path() != 'api/do':
                return self._send(404, {})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                ok, message = launcher.do(body if isinstance(body, dict) else {})
            except Exception as error:
                ok, message = False, f'That did not work: {error!r}'
            self._send(200, {'ok': bool(ok), 'message': message or ''})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_address[1]}/{key}/'


def open_window(url):
    """A window of its own without browser buttons (Edge or Chrome in app mode), else the default browser."""
    roots = [os.environ.get(name, '') for name in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')]
    for tail in (r'Microsoft\Edge\Application\msedge.exe', r'Google\Chrome\Application\chrome.exe'):
        for root in roots:
            path = os.path.join(root, tail)
            if root and os.path.exists(path):
                profile = os.path.join(os.environ.get('LOCALAPPDATA', str(config.BASE)), 'DBLauncherWindow')
                subprocess.Popen([path, '--app=' + url, '--window-size=1120,860', '--user-data-dir=' + profile,
                                  '--no-first-run', '--no-default-browser-check', '--disable-features=Translate'])
                return
    import webbrowser
    webbrowser.open(url)


def _already_open():
    """The address of this launcher's window when a copy is already running from this folder."""
    try:
        url = json.loads(INSTANCE_FILE.read_text(encoding='utf-8'))['url']
        with urllib.request.urlopen(url + 'api/state', timeout=2) as reply:
            return url if json.loads(reply.read()).get('app') else None
    except (OSError, ValueError, KeyError):
        return None


def run():
    """The launcher with its window: returns when the window is closed and no game is running."""
    url = _already_open()
    if url:                                   # started twice: show the window of the copy that runs
        open_window(url)
        return
    launcher = Launcher()
    server, url = serve(launcher)
    try:
        INSTANCE_FILE.write_text(json.dumps({'url': url}), encoding='utf-8')
    except OSError:
        pass
    config.note(f'{APP_NAME} {VERSION} opened.')
    if os.environ.get('DUSKLAN_NO_WINDOW') != '1':     # tests read the address from the file above instead
        open_window(url)
    try:
        launcher.quit.wait()
    except KeyboardInterrupt:
        pass
    launcher.stop()
    server.shutdown()
    try:
        INSTANCE_FILE.unlink()
    except OSError:
        pass
