"""The automatic health check: everything that has stopped a match before, looked at before the game starts.

Each check returns a Result. Nothing here changes the PC; a fix is always a sentence for the player.
"""
import ctypes
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config, network

OK, WARN, FAIL = 'ok', 'warn', 'fail'

# A complete unpacked game, measured on a PC where it works: romfs 9719 files, 3.8 GB.
# A short copy starts, draws frames and stays on a black screen.
ROMFS_FILES, ROMFS_BYTES = 9719, 3_800_000_000
ONLINE_MARK = b'EDEN_NX2_ONLINE_SERVER'       # the emulator switch this launcher drives


@dataclass
class Result:
    key: str
    level: str
    title: str
    detail: str = ''
    fix: str = ''


def emulator(path):
    if not path or not Path(path).is_file():
        return Result('emulator', FAIL, 'Emulator not found',
                      'No lichii.exe next to this launcher.',
                      'Put the Lichii folder next to this program, or choose the emulator under Setup.')
    if not _file_contains(path, ONLINE_MARK):
        return Result('emulator', FAIL, 'This emulator cannot join rooms', str(path),
                      'Use the Lichii build that comes with this launcher: other builds lack the room switches.')
    if not _vc_runtime():
        return Result('emulator', WARN, 'Microsoft Visual C++ runtime missing', str(path),
                      'Run vc_redist.x64.exe (next to this launcher) once, then start again.')
    return Result('emulator', OK, 'Emulator ready', str(path))


def game(main):
    if not main or not Path(main).is_file():
        return Result('game', FAIL, 'Game not chosen',
                      'The launcher needs your own unpacked copy of the game.',
                      'Press "Choose game folder" and pick the folder that holds exefs and romfs.')
    romfs = Path(main).parents[1] / 'romfs'
    files = size = 0
    for root, _dirs, names in os.walk(romfs):
        for name in names:
            files += 1
            try:
                size += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    if files < ROMFS_FILES * 0.98 or size < ROMFS_BYTES * 0.95:
        return Result('game', FAIL, 'Game folder is incomplete',
                      f'romfs has {files} files, {size / 1e9:.1f} GB; a complete copy has {ROMFS_FILES} files, '
                      f'about {ROMFS_BYTES / 1e9:.1f} GB.',
                      'An incomplete copy starts but stays on a black screen. Copy or unpack the game again.')
    return Result('game', OK, 'Game files complete', f'{files} files, {size / 1e9:.1f} GB')


def keys(data):
    if (Path(data) / 'keys' / 'prod.keys').is_file():
        return Result('keys', OK, 'Keys found')
    return Result('keys', FAIL, 'Keys missing', str(Path(data) / 'keys'),
                  'Put your own prod.keys and title.keys into that folder ("Open keys folder").')


def memory():
    free, total = _memory_gb()
    if total and total < 15:
        return Result('memory', WARN, f'{total:.0f} GB of memory',
                      'The game needs about 9 GB for itself.',
                      'Close browsers and other programs before playing.')
    if free and free < 10:
        return Result('memory', WARN, f'Only {free:.0f} GB of memory free',
                      'The game needs about 9 GB for itself.', 'Close other programs before playing.')
    return Result('memory', OK, f'Memory: {free:.0f} GB free of {total:.0f} GB' if total else 'Memory')


def disk(data):
    try:
        free = shutil.disk_usage(Path(data).anchor or '.').free / 2 ** 30
    except OSError:
        return Result('disk', OK, 'Disk')
    if free < 8:
        return Result('disk', WARN, f'Only {free:.0f} GB free on the data drive',
                      'Shader caches and saves need room.', 'Free some space on that drive.')
    return Result('disk', OK, f'Disk: {free:.0f} GB free')


def graphics():
    """Video memory, when an NVIDIA card reports it (read with nvidia-smi; other cards: no check)."""
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader,nounits'],
                             capture_output=True, text=True, timeout=8, creationflags=network.NO_WINDOW).stdout
        name, megabytes = [part.strip() for part in out.splitlines()[0].split(',')]
        gigabytes = int(megabytes) / 1024
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return Result('graphics', OK, 'Graphics card')
    if gigabytes < 7.5:
        return Result('graphics', WARN, f'{name}: {gigabytes:.0f} GB video memory',
                      'Cards under 8 GB drop frames at high resolution.',
                      'In the emulator choose 1x resolution (Emulation > Configure > Graphics).')
    return Result('graphics', OK, f'{name}: {gigabytes:.0f} GB video memory')


def networks_check(found, hosting):
    """Home network present; a VPN network Windows labels Public blocks a host's friends."""
    if not found:
        return Result('network', FAIL, 'No network',
                      'This PC has no home network or VPN address.', 'Connect to your network (or VPN) first.')
    names = ', '.join(f"{n['name']} {n['ip']}" for n in found)
    blocked = [n for n in found if n['public'] and n['kind'] == 'vpn']
    if blocked:
        name = blocked[0]['name']
        level = WARN
        detail = (f'Windows has the {name} network set to "Public": it blocks other players from reaching this PC'
                  + ('.' if hosting else ' (only matters when you host).'))
        fix = ('Once: right-click Start, open Windows PowerShell (Admin), paste this line, press Enter:\n'
               f'Get-NetConnectionProfile | Where-Object InterfaceAlias -like "{name}*" | '
               'Set-NetConnectionProfile -NetworkCategory Private')
        return Result('network', level, f'{name} network is Public', detail, fix)
    return Result('network', OK, 'Network: ' + names)


def host_ports():
    busy = [port for port in (config.GAME_PORT, config.ROOM_PORT) if network.port_busy(port)]
    if busy:
        return Result('ports', FAIL, 'A room is already running on this PC',
                      'Port ' + ', '.join(map(str, busy)) + ' is in use.',
                      'Close the other launcher or game window, then try again.')
    return Result('ports', OK, 'Room ports free')


def host_tools():
    if config.servers_dir():
        return Result('servers', OK, 'Room servers present')
    return Result('servers', FAIL, 'Room servers missing',
                  'Hosting needs the "servers" folder next to this launcher.',
                  'Joining works without it. See README, "Hosting".')


def run_all(settings, mode='join'):
    """Every check for the chosen mode ('join' | 'host' | 'solo'), worst first."""
    emu = config.find_emulator(settings.get('emulator', ''))
    main = config.find_game(settings.get('game', ''))
    data = config.data_dir(emu) if emu else None
    found = network.networks()
    results = [emulator(emu), game(main)]
    if data:
        results += [keys(data), disk(data)]
    results += [memory(), graphics(), networks_check(found, mode == 'host')]
    if mode in ('host', 'solo'):
        results += [host_tools(), host_ports()]
    order = {FAIL: 0, WARN: 1, OK: 2}
    results.sort(key=lambda r: order[r.level])
    return results, {'emulator': emu, 'game': main, 'data': data, 'networks': found}


def _file_contains(path, needle, chunk=1 << 20):
    try:
        with open(path, 'rb') as f:
            tail = b''
            while True:
                block = f.read(chunk)
                if not block:
                    return False
                if needle in tail + block:
                    return True
                tail = block[-len(needle):]
    except OSError:
        return False


def _vc_runtime():
    if os.name != 'nt':
        return True
    system = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32'
    return (system / 'vcruntime140_1.dll').is_file() and (system / 'msvcp140.dll').is_file()


def _memory_gb():
    if os.name != 'nt':
        return 0.0, 0.0

    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong), ('total', ctypes.c_ulonglong),
                    ('free', ctypes.c_ulonglong), ('total_page', ctypes.c_ulonglong),
                    ('free_page', ctypes.c_ulonglong), ('total_virtual', ctypes.c_ulonglong),
                    ('free_virtual', ctypes.c_ulonglong), ('extended', ctypes.c_ulonglong)]

    status = Status()
    status.length = ctypes.sizeof(Status)
    try:
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except (AttributeError, OSError):
        return 0.0, 0.0
    return status.free / 2 ** 30, status.total / 2 ** 30
