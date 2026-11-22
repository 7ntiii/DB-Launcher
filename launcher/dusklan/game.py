"""Preparing the emulator's data and starting the game.

The game talks to "its servers" by name; the emulator build this launcher drives sends those names to
a room instead (EDEN_NX2_ONLINE_* switches). A room is a PC running the room servers: the host's own
PC, reached by the other players over the home network or a VPN.
"""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import config, network

# Emulator switches the network test needs to boot and to keep its audio and memory layout right.
# They are read by the emulator at start; the same values every earlier build of ours was run with.
BOOT_SWITCHES = {
    'EDEN_NX2_DIAG_CODEC_CLIENT_REPLY': '1',
    'EDEN_NX2_EXPERIMENTAL_CODEC_DECODE': '1',
    'EDEN_NX2_EXPERIMENTAL_SYSMIX_OUTPUT': '1',
    'EDEN_NX2_SYSMIX_DRAIN_MULTIPLIER': '1',
    'EDEN_NX2_APP_POOL_PROBE': '1152',
    'EDEN_NX2_GPU_MAP_FLAG_PROBE': '1',
    'EDEN_NX2_SILENT_BAD_OPUS': '1',
    'EDEN_NX2_TRACE_TERMINATE': '1',
}

# qt-config.ini keys this launcher owns, by section (used only when the file does not exist yet)
FIRST_CONFIG = ('[Data%20Storage]\nnand_directory\\default=false\nnand_directory={nand}\n'
                'save_directory\\default=false\nsave_directory={save}\n\n'
                '[Debugging]\nuse_gdbstub\\default=false\nuse_gdbstub=false\n\n'
                '[Services]\nnetwork_interface\\default=true\nnetwork_interface=\n'
                'airplane_mode\\default=false\nairplane_mode=false\n\n'
                '[UI]\ncheck_for_updates\\default=false\ncheck_for_updates=false\n')


class StartError(Exception):
    """A start that cannot go on; the text is for the player."""


def prepare(emulator, game_main, log):
    """Folders, the game's regulation file and the emulator settings a match needs.

    Returns {'data', 'play', 'nand', 'save', 'run'}.
    """
    data = config.data_dir(emulator)
    if not (data / 'keys' / 'prod.keys').is_file():
        (data / 'keys').mkdir(parents=True, exist_ok=True)
        raise StartError(f'Put your own prod.keys and title.keys into:\n{data / "keys"}')
    play = config.play_dir(data)
    nand, save = play / 'nand', play / 'save'
    seed = Path(emulator).parent / 'seed'
    for folder, name in ((nand, 'nand'), (save, 'save')):
        if not folder.exists():
            if (seed / name).is_dir():
                shutil.copytree(seed / name, folder)
            else:
                folder.mkdir(parents=True)
    _regulation(game_main, nand, log)
    _settings(data, nand, save, log)
    run = play / 'runs' / time.strftime('%Y%m%d_%H%M%S')
    run.mkdir(parents=True, exist_ok=True)
    return {'data': data, 'play': play, 'nand': nand, 'save': save, 'run': run}


def set_player_name(nand, name, log):
    """Write the name the game shows for this player into the emulator's profile file (first profile).

    The file is the emulator's own 'profiles.dat': a 16-byte header, then 8 profiles of 200 bytes each
    (id 16, id 16, time 8, name 32, extra 128). Only the 32 name bytes are replaced. When the emulator
    has never run, a profile with a new random id is made, as the emulator would on its first start.
    """
    name = ''.join(c for c in (name or '').strip() if c.isprintable())
    raw = name.encode('utf-8')[:31]
    while raw:                                  # never cut a letter in half
        try:
            raw.decode('utf-8')
            break
        except UnicodeDecodeError:
            raw = raw[:-1]
    if not raw:
        return
    path = nand / 'system' / 'save' / '8000000000000010' / 'su' / 'avators' / 'profiles.dat'
    try:
        if path.is_file() and path.stat().st_size == 0x650:
            data = bytearray(path.read_bytes())
            if data[0x10:0x20] == bytes(16):    # no first profile in the file
                data[0x10:0x20] = os.urandom(16)
        else:
            data = bytearray(0x650)
            data[0x10:0x20] = os.urandom(16)
        field = raw.ljust(32, bytes(1))
        if bytes(data[0x38:0x58]) == field:
            return
        data[0x38:0x58] = field
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(data))
        log(f'Player name set to "{raw.decode("utf-8")}".')
    except OSError as error:
        log(f'The player name could not be saved ({error}).', error=True)


def _regulation(game_main, nand, log):
    """The game reads its rules ("regulation") from a download cache. A real console fills it from the
    network; here it gets the copy inside the game's own files. A file that is already there stays: a
    player keeps exactly the rules they have been playing with."""
    cache = nand / 'system' / 'save' / 'bcat' / config.TITLE_ID / 'Regulation'
    target = cache / 'regulation_nt_1_0.bin'
    if target.is_file() and target.stat().st_size > 0:
        return
    source = Path(game_main).parents[1] / 'romfs' / 'regulation_nt.bin'
    if not source.is_file():
        log('The game folder has no regulation_nt.bin; the game may report a data error.', error=True)
        return
    cache.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def _settings(data, nand, save, log):
    """Point the emulator at this launcher's save folders and switch off what breaks a match
    (airplane mode, the debugger pause, an adapter name saved on another PC)."""
    path = data / 'config' / 'qt-config.ini'
    values = {'nand_directory': nand.as_posix(), 'save_directory': save.as_posix(), 'airplane_mode': 'false',
              'use_gdbstub': 'false', 'check_for_updates': 'false'}
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(FIRST_CONFIG.format(nand=values['nand_directory'], save=values['save_directory']),
                        encoding='utf-8')
        log('First start on this PC: the emulator begins with its default settings.')
        return
    text = original = path.read_text(encoding='utf-8')
    for key, value in values.items():
        text = _set(text, key, value)
    # an adapter name saved elsewhere (a VPN's, another PC's) makes the game report "no internet"
    text = re.sub(r'(?m)^network_interface=.*$', 'network_interface=', text)
    text = re.sub(r'(?m)^network_interface\\default=.*$', r'network_interface\\default=true', text)
    if text != original:
        path.write_text(text, encoding='utf-8')


def _set(text, key, value):
    line = re.compile(rf'(?m)^{re.escape(key)}=.*$')
    if not line.search(text):
        return text
    text = line.sub(lambda _m: f'{key}={value}', text)
    return re.sub(rf'(?m)^{re.escape(key)}\\default=(?:true|false)$', lambda _m: f'{key}\\default=false', text)


def join_room(address, password, play, log):
    """Sign up at a host's room. Returns ('host:port', certificate file)."""
    host, port = network.split_address(address)
    if not host:
        raise StartError('Type the host PC\'s address, or press "Find rooms".')
    base = f'http://{host}:{port + (config.ROOM_PORT - config.GAME_PORT)}'
    log(f'Contacting the room at {host} ...')
    try:
        greeting = network.hello(host, timeout=6)
        if greeting is None:
            raise OSError('no DB room answers at that address')
        certificate = play / 'online_ca' / (re.sub(r'[^0-9A-Za-z.-]', '_', host) + '.der')
        certificate.parent.mkdir(parents=True, exist_ok=True)
        certificate.write_bytes(network.http(base + '/ca.der'))
        network.http(base + '/register', {'room': network.room_id(password)})
    except (OSError, ValueError) as error:
        raise StartError(
            f'Could not reach the room at {host}: {error}\n\n'
            'Check, in this order:\n'
            '1. The host has pressed "Host a match" and their window says "Room open".\n'
            '2. The address is the one the host\'s window shows.\n'
            '3. Both PCs are on the same network (or the same VPN, connected).\n'
            '4. On a VPN: the host\'s Windows must have the VPN network set to Private.') from error
    log(f'Joined the room at {host}' + (f' ("{greeting.get("name")}")' if greeting.get('name') else '') + '.')
    return f'{host}:{port}', certificate


def environment(server, certificate, run, extra=None, local_only=False):
    """The emulator's environment for one session."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(('EDEN_NX2_', 'EDEN_NATIVE_'))}
    env.update(BOOT_SWITCHES)
    env.update(EDEN_NX2_ONLINE_HOSTS=config.ONLINE_HOSTS, EDEN_NX2_ONLINE_SERVER=server,
               EDEN_NX2_ONLINE_CA=str(certificate), EDEN_NX2_CRASH_DUMP=str(run))
    if local_only:
        env['EDEN_NX2_LOOPBACK_ONLY'] = '1'
    # other switches the player set themselves (a .cmd file, the test tools) pass through
    env.update({k: v for k, v in os.environ.items() if k.startswith('EDEN_NX2_') and k not in env})
    env.update(extra or {})
    env.pop('SDL_AUDIODRIVER', None)
    return env


def start(emulator, game_main, env, run):
    console = (run / 'console.log').open('w')
    return subprocess.Popen([str(emulator), '-g', str(game_main)], cwd=str(Path(emulator).parent), env=env,
                            stdout=console, stderr=subprocess.STDOUT)


def keep_log(data, run):
    """After the game closes: a copy of the emulator's log beside the session's other files."""
    log = data / 'log' / 'eden_log.txt'
    try:
        if log.is_file():
            shutil.copyfile(log, run / 'emulator.log')
    except OSError:
        pass


def stop(process):
    """End a process and what it started."""
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                           creationflags=network.NO_WINDOW)
        else:
            process.terminate()
        process.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass
