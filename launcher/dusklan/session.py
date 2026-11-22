"""One play session from start to end: check, prepare, join or host, run the game, clean up.

Used by the window and by the command line, so both do exactly the same.
"""
import os

from . import checks, config, game, hosting

# which failed checks stop a start, per mode
BLOCKING = {'join': ('emulator', 'game', 'keys', 'network'),
            'host': ('emulator', 'game', 'keys', 'network', 'servers', 'ports'),
            'solo': ('emulator', 'game', 'keys', 'servers', 'ports')}


class Session:
    def __init__(self, settings, mode, host_network, log, on_checks=None):
        self.settings, self.mode, self.host_network, self.log = settings, mode, host_network, log
        self.on_checks = on_checks or (lambda results, found: None)
        self.process = self.room = self.ready = None

    def start(self):
        """Raises game.StartError with a text for the player; leaves nothing running when it does."""
        results, found = checks.run_all(self.settings, self.mode)
        self.on_checks(results, found)
        stoppers = [r for r in results if r.level == checks.FAIL and r.key in BLOCKING[self.mode]]
        if stoppers:
            raise game.StartError(stoppers[0].title + '\n\n' + (stoppers[0].fix or stoppers[0].detail))
        emulator, main = found['emulator'], found['game']
        self.ready = ready = game.prepare(emulator, main, self.log)
        game.set_player_name(ready['nand'], self.settings.get('player_name', ''), self.log)
        try:
            if self.mode == 'join':
                server, certificate = game.join_room(self.settings['host_address'], self.settings['password'],
                                                     ready['play'], self.log)
                env = game.environment(server, certificate, ready['run'])
            else:
                net = self.host_network if self.mode == 'host' else None
                if self.mode == 'host' and net is None:
                    net = next((n for n in found['networks'] if n['name'] == self.settings.get('host_network')),
                               None) or next(iter(found['networks']), None)
                if self.mode == 'host' and net is None:
                    raise game.StartError('No network to host on. Connect to your network or VPN first.')
                self.room = hosting.Room(ready['play'], ready['data'], ready['run'], self.log,
                                         name=self.settings.get('room_name', ''),
                                         password=self.settings.get('password', ''), host_network=net)
                server, certificate, extra = self.room.start()
                if self.mode == 'host' and not os.environ.get('EDEN_NX2_DEBUG_SERVER'):
                    # the host tools (hosttools.py) reach the host's own game through this port;
                    # the emulator accepts it on this PC only
                    extra = dict(extra, EDEN_NX2_DEBUG_SERVER=f'127.0.0.1:{config.TOOLS_PORT}')
                env = game.environment(server, certificate, ready['run'], extra, local_only=self.mode == 'solo')
            self.process = game.start(emulator, main, env, ready['run'])
        except BaseException:
            self.stop()
            raise
        self.log(f'Game started. Session files: {ready["run"]}')
        if self.mode == 'host':
            self.log('The match starts only when you press START MATCH here.')

    def wait(self):
        """Block until the game closes, then stop the room and keep the log."""
        if self.process is not None:
            self.process.wait()
        if self.ready:
            game.keep_log(self.ready['data'], self.ready['run'])
        self.stop()
        self.log('Game closed.')

    def stop(self):
        game.stop(self.process)
        if self.room is not None:
            self.room.stop()
        self.process = self.room = None

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None
