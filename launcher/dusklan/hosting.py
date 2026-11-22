"""Hosting a room: the room servers and the host profile (the host is player 1).

The room servers themselves are separate programs in the 'servers' folder (they are not part of this
launcher's code). This module starts them with the settings LAN play needs and stops them again.
The host steers the match from the launcher's own window (web.py), which talks to the match server's
panel service on this PC.

    servers/dusk_server/frontdoor.py      the game's front door (TLS) + sign-up service + match making
    servers/npln_server/npln_stub.py      the session service behind it
    servers/npln_server/make_pki.py       makes this PC's private certificates once
"""
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from . import config, network
from .game import StartError, stop

# The emulator's 12-digit online profile code decides the player number: the lowest code is player 1,
# who owns the match clock and drives the bosses. The host signs in with a profile of its own that has
# a low code, so the hosting PC is always player 1 (the player's normal profile is not touched).
HOST_PROFILE_CODE = '000016777217'


def python_for(script):
    """The command that runs a server script: this program itself when it is a packed .exe."""
    if config.FROZEN:
        return [sys.executable, '--run-script', str(script)]
    return [sys.executable, str(script)]


class Room:
    """One hosted room. start() returns ('127.0.0.1:port', certificate, extra emulator switches)."""

    def __init__(self, play, data, run, log, name='', password='', host_network=None, local_only=False):
        self.play, self.data, self.run, self.log = Path(play), Path(data), Path(run), log
        self.name = name or 'DB room'
        self.password = password
        self.network = host_network          # entry of network.networks(); None = this PC only
        self.local_only = local_only or host_network is None
        self.processes = []
        self.address = host_network['ip'] if host_network else '127.0.0.1'

    def start(self):
        servers = config.servers_dir()
        if servers is None:
            raise StartError('The "servers" folder is missing next to this launcher: this copy can join rooms '
                             'but not host them. See README, "Hosting".')
        for port in (config.GAME_PORT, config.ROOM_PORT):
            if network.port_busy(port):
                raise StartError(f'Port {port} is already in use: another launcher or an earlier game is still '
                                 'open on this PC. Close it and try again.')
        pki = self._certificates(servers)
        session_port = _free_port(config.GAME_PORT + 1)
        web_port = _free_port(18090)
        listen = ['127.0.0.1'] + ([] if self.local_only else [self.address])
        (self.run / 'server_data').mkdir(parents=True, exist_ok=True)
        quiet = {'creationflags': network.NO_WINDOW} if os.name == 'nt' else {'start_new_session': True}

        stub = servers / 'npln_server' / 'npln_stub.py'
        stub_args = ['--port', str(session_port), '--host', ','.join(listen), '--web-port', str(web_port),
                     '--data', str(self.run / 'server_data'), '--pki', str(pki), '--log', str(self.run / 'server.log')]
        if not self.local_only:
            stub_args += ['--nat-ip', self.address]
        env = self._server_environment(servers)
        self.processes.append(subprocess.Popen(
            python_for(stub) + stub_args, cwd=str(stub.parent), env=env,
            stdout=(self.run / 'server_console.log').open('w'), stderr=subprocess.STDOUT, **quiet))

        door = servers / 'dusk_server' / 'frontdoor.py'
        door_args = ['--port', str(config.GAME_PORT), '--upstream', str(session_port), '--ca-dir', str(pki),
                     '--cert-dir', str(self.play / 'frontdoor_pki'), '--log', str(self.run / 'frontdoor.log')]
        if not self.local_only:
            door_args += ['--bind', '0.0.0.0', '--room-port', str(config.ROOM_PORT), '--room-name', self.name]
        self.processes.append(subprocess.Popen(
            python_for(door) + door_args, cwd=str(door.parent), env=env,
            stdout=(self.run / 'frontdoor_console.log').open('w'), stderr=subprocess.STDOUT, **quiet))

        time.sleep(3)
        if any(p.poll() is not None for p in self.processes):
            self.stop()
            raise StartError(f'A room server stopped right after starting. Its messages are in:\n{self.run}')
        extra = {}
        if not self.local_only:
            try:
                network.http(f'http://127.0.0.1:{config.ROOM_PORT}/register',
                             {'room': network.room_id(self.password), 'bots': False})
            except OSError as error:
                self.stop()
                raise StartError(f'The room\'s sign-up service did not start ({error}). See:\n{self.run}') from error
            extra = self._host_profile()
            self._host_starts_only()
            self.log(f'Room open. The other players join with the address  {self.address}')
        return f'127.0.0.1:{config.GAME_PORT}', pki / 'ca.der', extra

    def _certificates(self, servers):
        pki = self.play / 'pki'
        if not (pki / 'ca.der').is_file():
            self.log('Making this PC\'s private certificates (first time only) ...')
            script = servers / 'npln_server' / 'make_pki.py'
            made = subprocess.run(python_for(script) + ['--out', str(pki)], cwd=str(script.parent),
                                  capture_output=True, creationflags=network.NO_WINDOW)
            if made.returncode != 0 or not (pki / 'ca.der').is_file():
                raise StartError('Could not make the certificates:\n' + made.stderr.decode('utf-8', 'replace')[-400:])
        return pki

    def _server_environment(self, servers):
        """The match server's settings for LAN play (each explained where it is set)."""
        env = dict(os.environ, DUSK_REDIRECT_VALUE='nochange', DUSK_FRONTEND='1', PYTHONUNBUFFERED='1')
        if self.local_only:
            return env
        vpn = self.network['kind'] == 'vpn'
        env.update({
            'DUSK_ONLINE': '1',
            'DUSK_HOST_IP': self.address,           # the address the other players reach this PC at
            'DUSK_ADVERTISE_IP': self.address,
            'DUSK_P2P_FORMAT': 'self',              # every player's game is its own "game server": 2-8 players
            'DUSK_MATCH_HOLD': '1',                 # players keep searching until the host presses Start match
            'DUSK_MATCH_WAIT': '0',
            'DUSK_WAIT_LONGPOLL': '3600',           # keeps a search alive (the game gives up after 4 quick "wait"s)
            'DUSK_TICKET_TTL': '1.6',
            'DUSK_PANEL_PORT': str(config.PANEL_API_PORT),
            # the lobby size and the host game's state, shared through two small files in the log folder
            'DUSK_MATCH_FILE': str(self.data / 'log' / 'dusk_lan_match.txt'),
            'DUSK_STATUS_FILE': str(self.data / 'log' / 'dusk_lan_status.json'),
        })
        if vpn:
            # VPN play: every player joins with this PC's VPN address; the panel marks who is outside it
            env.update(DUSK_TAILSCALE='1', DUSK_VPN_NET=self.network['net'], DUSK_VPN_NAME=self.network['name'])
        for name in ('DUSK_MATCH_HOLD', 'DUSK_P2P_FORMAT', 'DUSK_WAIT_LONGPOLL', 'DUSK_TICKET_TTL', 'DUSK_MATCH_WAIT'):
            if os.environ.get(name):                # a tester's own value wins
                env[name] = os.environ[name]
        return env

    def _host_profile(self):
        if os.environ.get('DUSK_HOST_FIRST', '1') == '0' or os.environ.get('EDEN_NX2_ONLINE_PROFILES'):
            return {}
        folder = self.play / 'host_profile'
        profile = folder / f'127.0.0.1_{config.GAME_PORT}.txt'
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if not profile.is_file():
                profile.write_text(f'server=127.0.0.1:{config.GAME_PORT}\ncode={HOST_PROFILE_CODE}\n'
                                   f'secret={secrets.token_hex(16)}\nfriends=\nremoved=\n',
                                   encoding='ascii', newline='\n')
        except OSError as error:
            self.log(f'Host profile not set up ({error}): the player number follows the normal profile.')
            return {}
        return {'EDEN_NX2_ONLINE_PROFILES': str(folder)}

    def _host_starts_only(self):
        """The match server must never start a match by itself: 'hold' on (players wait for the host's
        Start) and 'start when everyone is searching' off. Sent again here even though both are the
        server's defaults with our settings, so an older value can never stay."""
        for _try in range(10):
            try:
                network.http(f'http://127.0.0.1:{config.PANEL_API_PORT}/api/settings',
                             {'hold': True, 'all': False}, timeout=2)
                return
            except OSError:
                time.sleep(0.5)
        self.log('The match server did not confirm "host starts the match"; it keeps its default (host starts).')

    def stop(self):
        for process in reversed(self.processes):
            stop(process)
        self.processes = []


def _free_port(preferred):
    import socket
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return preferred
