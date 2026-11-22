r"""Two Duskbloods games on ONE PC talking to each other like two PCs on a LAN (2-player tests
without the laptop). Uses the LAN-fix servers (diag\twin\tools: launcher\lan_fix copies of
frontend_api.py and npln_stub.py over the launcher's own server files).

  game A: %APPDATA%\eden data, server names -> 127.0.0.1 (the match server sees 127.0.0.1 and
          tells B this PC's LAN address, port 15500), debug server 6545 (nx2_switches.txt),
          gdbstub 6543 + diag\net\quic_watch.py
  game B: data in diag\twin\userB (LICHII_USER_DIR; debug server 6546 via env),
          gdbstub 6544 + watcher (log quic_watch_B.log), own online profile (another friend code = another NPLN user), server names ->
          192.168.1.11 (so the match server tells the two apart), its P2P port 15500 bound as
          15501 (LICHII_PORT_MAP; DUSK_P2P_PORTS tells A)
  (Two local addresses on different adapters do not work: Windows' strong host model drops
  traffic between them.)

Both are registered into one room of the match server (room API 18445), so they match.
Usage (workspace):  python diag\twin\twin.py [--no-watch] [--only A|B]
Stops everything when both games exit. Run dir: diag\twin\runs\<time>.
"""
import importlib.util, json, os, socket, subprocess, sys, time
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
TWIN = WS / 'diag' / 'twin'
TOOLS = TWIN / 'tools'
EXE = WS / 'build' / 'lichii' / 'bin' / 'lichii.exe'
GAME = WS / 'game' / 'THE DUSKBLOODS' / 'THE DUSKBLOODS NETWORK TEST VER'
APPDATA = Path(os.environ['APPDATA'])
TEST = APPDATA / 'eden' / 'duskbloods_test'
PKI = TEST / 'pki'
LAN = os.environ.get('TWIN_LAN_IP', '192.168.1.11')
IP_A, IP_B, PORT_B = '127.0.0.1', LAN, 15501
# Third game (TWIN_GAMES=ABC): its server connections come from another local address (this PC's
# ZeroTier adapter), so the match server tells it apart; its P2P address is still the LAN one,
# port 15502 (DUSK_P2P_ADDR / DUSK_P2P_PORTS tell the match server).
IP_C, PORT_C = os.environ.get('TWIN_IP_C', '10.0.0.225'), 15502
# Fourth game (TWIN_GAMES=ABCD): server identity via the Tailscale adapter address, P2P = LAN:15503.
IP_D, PORT_D = os.environ.get('TWIN_IP_D', '169.254.0.1'), 15503
GAMES = os.environ.get('TWIN_GAMES', 'AB')
PORT, UPSTREAM, ROOM_PORT, WEB = 18443, 18444, 18445, 18090
ROOM = 'feedfacecafebeef0123456789abcdef'
# TWIN_ROOM_PASSWORD: the room of that launcher password, so another PC's launcher (Join a room,
# same password, this PC's LAN address) lands in the same room as the twin games.
if os.environ.get('TWIN_ROOM_PASSWORD'):
    import hashlib
    ROOM = hashlib.sha256(('duskbloods-room-v1:' + os.environ['TWIN_ROOM_PASSWORD'].strip())
                          .encode('utf-8')).hexdigest()[:32]
# TWIN_HOST_PANEL=1: the match server runs as the v2.5+ host does (players search until the host
# presses Start match) and the host panel window opens (diag/twin/panel_window.py).
HOST_PANEL = os.environ.get('TWIN_HOST_PANEL') == '1'


def game_main():
    spec = importlib.util.spec_from_file_location(
        'dusk_launcher', WS / 'emulators' / 'v30-eglantine' / 'play_duskbloods_switches.py')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.game_main_from(GAME)


def emu_env(server_ip, extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('EDEN_NX2_', 'EDEN_NATIVE_'))}
    env.update(EDEN_NX2_DIAG_CODEC_CLIENT_REPLY='1', EDEN_NX2_EXPERIMENTAL_CODEC_DECODE='1',
               EDEN_NX2_EXPERIMENTAL_SYSMIX_OUTPUT='1', EDEN_NX2_SYSMIX_DRAIN_MULTIPLIER='1',
               EDEN_NX2_APP_POOL_PROBE='1152', EDEN_NX2_GPU_MAP_FLAG_PROBE='1',
               EDEN_NX2_SILENT_BAD_OPUS='1',
               EDEN_NX2_ONLINE_HOSTS='npln.srv.nintendo.net,npln.nintendo.net,n.n.srv.nintendo.net,'
                                     'p.srv.nintendo.net,fromsoftware-game.net',
               EDEN_NX2_ONLINE_SERVER=f'{server_ip}:{PORT}', EDEN_NX2_ONLINE_CA=str(PKI / 'ca.der'))
    env.pop('SDL_AUDIODRIVER', None)
    env.update(extra)
    return env


def register(ip):
    """Put the game whose server connections come from `ip` into the shared room."""
    body = json.dumps({'room': ROOM}).encode()
    s = socket.create_connection((ip, ROOM_PORT), timeout=5, source_address=(ip, 0))
    s.sendall((f'POST /register HTTP/1.1\r\nHost: {ip}\r\nContent-Type: application/json\r\n'
               f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode() + body)
    r = s.recv(4096); s.close()
    return r.split(b'\r\n', 1)[0].decode()


def main():
    args = sys.argv[1:]
    only = args[args.index('--only') + 1] if '--only' in args else None
    run = TWIN / 'runs' / time.strftime('%Y%m%d_%H%M%S'); run.mkdir(parents=True)
    procs, games = [], {}
    no_window = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        procs.append(subprocess.Popen(
            [sys.executable, '-u', 'npln_stub.py', '--port', str(UPSTREAM),
             '--host', f'127.0.0.1,{LAN}', '--nat-ip', LAN, '--web-port', str(WEB),
             '--data', str(run / 'server_data'), '--pki', str(PKI), '--log', str(run / 'server.log')],
            cwd=TOOLS / 'npln_server', env=dict(os.environ, DUSK_HOST_IP=LAN),
            stdout=(run / 'server_console.log').open('w'), stderr=subprocess.STDOUT,
            creationflags=no_window))
        fenv = dict(os.environ, DUSK_REDIRECT_VALUE='nochange', DUSK_FRONTEND='1', DUSK_ONLINE='1',
                    PYTHONUNBUFFERED='1', DUSK_MATCH_WAIT='0', DUSK_TICKET_TTL='1.6',
                    DUSK_P2P_FORMAT=os.environ.get('TWIN_P2P_FORMAT', 'cross'), DUSK_HOST_IP=LAN, DUSK_P2P_PORTS=f'{IP_B}={PORT_B},{IP_C}={PORT_C}',
                    DUSK_P2P_ADDR=f'{IP_C}={LAN}')
        if 'D' in GAMES:                       # 4th game: own P2P port, P2P address = LAN
            fenv.update(DUSK_P2P_PORTS=fenv['DUSK_P2P_PORTS'] + f',{IP_D}={PORT_D}',
                        DUSK_P2P_ADDR=fenv['DUSK_P2P_ADDR'] + f',{IP_D}={LAN}')
        if HOST_PANEL:
            fenv.update(DUSK_MATCH_HOLD=os.environ.get('DUSK_MATCH_HOLD', '1'),
                        DUSK_WAIT_LONGPOLL=os.environ.get('DUSK_WAIT_LONGPOLL', '3600'),
                        DUSK_PANEL_PORT='18451', DUSK_DEFAULT_ROOM=ROOM,
                        DUSK_PANEL_HTML=str(WS / 'launcher' / 'lan_fix' / 'panel.html'))
            procs.append(subprocess.Popen(
                [sys.executable, '-u', str(TWIN / 'panel_window.py'), LAN],
                stdout=(run / 'panel_window.log').open('w'), stderr=subprocess.STDOUT,
                creationflags=no_window))
        procs.append(subprocess.Popen(
            [sys.executable, '-u', 'frontdoor.py', '--port', str(PORT), '--upstream', str(UPSTREAM),
             '--bind', '0.0.0.0', '--room-port', str(ROOM_PORT), '--ca-dir', str(PKI),
             '--cert-dir', str(TEST / 'frontdoor_pki'), '--log', str(run / 'frontdoor.log')],
            cwd=TOOLS / 'dusk_server', env=fenv, stdout=(run / 'frontdoor_console.log').open('w'),
            stderr=subprocess.STDOUT, creationflags=no_window))
        time.sleep(3)
        for ip in (IP_A, IP_B) + tuple(ip for w, ip in (('C', IP_C), ('D', IP_D)) if w in GAMES):
            print('room register', ip, register(ip), flush=True)
        main_file = game_main()
        if only in (None, 'A'):
            extra = {}
            if os.environ.get('TWIN_PLAYER_A'):      # LICHII_DUSK_PLAYER for game A only (no:team)
                extra['LICHII_DUSK_PLAYER'] = os.environ['TWIN_PLAYER_A']
            if os.environ.get('TWIN_GDB_A') == '1':      # gdbstub on A without the QUIC watcher (hp_watch.py)
                extra['LICHII_GDBSTUB'] = '6543'
            if '--no-watch' not in args:
                extra['LICHII_GDBSTUB'] = '6543'
                procs.append(subprocess.Popen(
                    [sys.executable, str(WS / 'diag' / 'net' / 'quic_watch.py')], cwd=WS,
                    stdout=(run / 'watch_console.log').open('w'), stderr=subprocess.STDOUT))
            games['A'] = subprocess.Popen(
                [str(EXE), '-g', str(main_file)], cwd=EXE.parent, env=emu_env(IP_A, extra),
                stdout=(run / 'console_A.log').open('w'), stderr=subprocess.STDOUT)
        if only in (None, 'B'):
            if games:
                time.sleep(20)                 # let A's boot claim its memory first
            userb = TWIN / 'userB'
            extra_b = {}
            if os.environ.get('TWIN_PLAYER_B'):
                extra_b['LICHII_DUSK_PLAYER'] = os.environ['TWIN_PLAYER_B']
            if '--no-watch' not in args:
                extra_b['LICHII_GDBSTUB'] = '6544'
                procs.append(subprocess.Popen(
                    [sys.executable, str(WS / 'diag' / 'net' / 'quic_watch.py')], cwd=WS,
                    env=dict(os.environ, QW_PORT='6544', QW_LOG='diag/net/quic_watch_B.log'),
                    stdout=(run / 'watch_B_console.log').open('w'), stderr=subprocess.STDOUT))
            games['B'] = subprocess.Popen(
                [str(EXE), '-g', str(main_file)], cwd=EXE.parent,
                env=emu_env(IP_B, {'LICHII_USER_DIR': str(userb),
                                   'EDEN_NX2_ONLINE_PROFILES': str(userb / 'online'),
                                   'LICHII_PORT_MAP': f'15500={PORT_B}',
                                   # an env var beats %APPDATA%\eden\nx2_switches.txt (A's 6545)
                                   'EDEN_NX2_DEBUG_SERVER': '127.0.0.1:6546', **extra_b}),
                stdout=(run / 'console_B.log').open('w'), stderr=subprocess.STDOUT)
        if 'C' in GAMES and only in (None, 'C'):
            time.sleep(75)                     # after B's boot: three boots at once stalled B
            userc = TWIN / 'userC'
            games['C'] = subprocess.Popen(
                [str(EXE), '-g', str(main_file)], cwd=EXE.parent,
                env=emu_env(IP_C, {'LICHII_USER_DIR': str(userc),
                                   'EDEN_NX2_ONLINE_PROFILES': str(userc / 'online'),
                                   'LICHII_PORT_MAP': f'15500={PORT_C}',
                                   'EDEN_NX2_DEBUG_SERVER': '127.0.0.1:6547',
                                   **({'LICHII_DUSK_PLAYER': os.environ['TWIN_PLAYER_C']}
                                      if os.environ.get('TWIN_PLAYER_C') else {})}),
                stdout=(run / 'console_C.log').open('w'), stderr=subprocess.STDOUT)
        if 'D' in GAMES and only in (None, 'D'):
            time.sleep(75)                     # one boot at a time (as C)
            userd = TWIN / 'userD'
            games['D'] = subprocess.Popen(
                [str(EXE), '-g', str(main_file)], cwd=EXE.parent,
                env=emu_env(IP_D, {'LICHII_USER_DIR': str(userd),
                                   'EDEN_NX2_ONLINE_PROFILES': str(userd / 'online'),
                                   'LICHII_PORT_MAP': f'15500={PORT_D}',
                                   'EDEN_NX2_DEBUG_SERVER': '127.0.0.1:6548',
                                   **({'LICHII_DUSK_PLAYER': os.environ['TWIN_PLAYER_D']}
                                      if os.environ.get('TWIN_PLAYER_D') else {})}),
                stdout=(run / 'console_D.log').open('w'), stderr=subprocess.STDOUT)
        (TWIN / 'session.json').write_text(json.dumps(
            {'run': str(run), 'pids': {k: p.pid for k, p in games.items()}, 'runner': os.getpid()},
            indent=2))
        print('run dir', run, 'games', {k: p.pid for k, p in games.items()}, flush=True)
        while any(p.poll() is None for p in games.values()):
            time.sleep(1)
    finally:
        for p in list(games.values()) + procs:
            if p.poll() is None:
                p.kill()


if __name__ == '__main__':
    main()
