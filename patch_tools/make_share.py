"""Rebuilds the share package (share\\Duskbloods-Lichii-Online + a zip) from the current build and
this PC's shader cache.

- Lichii\\lichii.exe comes from build\\lichii\\bin (the other files there, Qt DLLs, plugins,
  nx2_switches.txt, qt.conf, dxcompiler, stay as they are in the package folder).
- Lichii\\shader_seed\\<title>\\ gets this PC's pipeline cache + used list
  (%APPDATA%\\eden\\cache\\shader\\<title>). On a player's first boot lichii copies it into their own
  cache (SeedPipelineCache in vk_pipeline_cache.cpp), so every pipeline seen here is built at boot.
- Lichii\\jit_seed\\<title>\\ gets this PC's JIT seed (%APPDATA%\\eden\\cache\\jit\\<title>): the guest code
  blocks met here, which lichii compiles at boot next to the player's own list (jit_seed.cpp), so
  code first met in a match no longer stalls the game while it compiles.
- Host tools (since v2.5): lan_fix\\ (match server fixes, host script, panel page) from
  launcher\\lan_fix, and "Host a match (<version>).cmd" (version from the zip name). READ ME FIRST.txt is written from
  tools\\share_readme.txt ({commit} and {date} are filled in).
- Log collector (next release): lan_fix\\collect_logs.ps1 and "Collect logs.cmd" in the package root
  (PowerShell only: no Python, no admin rights; copies every game's logs into DuskLogs_<PC>_<date-time>).
- Two players on one PC (since v3.9.3): lan_fix\\host_plus.py and lan_fix\\second_player.py, and the two
  .cmd files "Host a match (4 players).cmd" and "Start second player.cmd" in the package root (each finds
  its script next to it or in lan_fix\\).
Close the game first: the cache is written while it runs.
Usage: python tools\\make_share.py [ZIP_NAME]     (default: Duskbloods-Lichii-Online.zip)
"""
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
TITLE = '0400d1d02399a000'
PKG = WS / 'share' / 'Duskbloods-Lichii-Online'
ZIP = WS / 'share' / (sys.argv[1] if len(sys.argv) > 1 else 'Duskbloods-Lichii-Online.zip')
# The version in the zip name ("... v2.6.zip") names the host script; v2.5 without one.
_version = re.search(r'v[0-9]+[.][0-9]+|valpha[0-9]+[a-z0-9]*', ZIP.name)   # 'valpha13' since 2026-11-20
VERSION = _version.group(0) if _version else 'v2.5'
# N13: the full version ("v3.9.12") for the readme; the host .cmd keeps the short one.
_full = re.search(r'v[0-9]+(?:[.][0-9]+)+|valpha[0-9]+[a-z0-9]*', ZIP.name)
FULL_VERSION = _full.group(0) if _full else VERSION
BIN = WS / 'build' / 'lichii' / 'bin'
CACHE = Path(os.environ['APPDATA']) / 'eden' / 'cache' / 'shader' / TITLE
JIT = Path(os.environ['APPDATA']) / 'eden' / 'cache' / 'jit' / TITLE
HOST_FILES = ('lan_fix_host.py', 'frontend_api.py', 'npln_stub.py', 'panel.html', 'host_plus.py',
              'second_player.py', 'collect_logs.ps1', 'update_from_host.ps1')
# copied as they are (CRLF batch files) from launcher\lan_fix into the package root
ROOT_CMDS = ('Host a match (4 players).cmd', 'Host a match (Tailscale).cmd', 'Start second player.cmd',
             'Collect logs.cmd', 'Update from host.cmd')
HOST_CMD = '\r\n'.join([
    '@echo off',
    'rem Host a LAN match: launcher + fixed match server + host panel (lan_fix\\lan_fix_host.py).',
    # review R2 (N11): "where python" also finds the Windows Store shortcut; only a real start counts
    'setlocal',
    'set "PY="',
    'python -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul && set "PY=python"',
    'if not defined PY (',
    '  py -3 -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul && set "PY=py -3"',
    ')',
    'if not defined PY (',
    '  echo Python 3 is needed to host. Install it from python.org and tick "Add python.exe to PATH".',
    '  pause',
    '  exit /b 1',
    ')',
    '%PY% "%~dp0lan_fix\\lan_fix_host.py"',
    'if errorlevel 1 pause',
    ''])
# N12: what the zip may hold (an allow list): the package folder is also PLAYED from, and whatever
# playing or a later version leaves there (SecondPlayer with keys and saves, logs, lobby file,
# lan_ip.txt, launcher_settings*.json copies, crash dumps, DuskLogs_*) must never be shipped.
SHIP_ROOT = {'Lichii', 'lan_fix', 'Play.Duskbloods.exe', 'READ ME FIRST.txt', 'vc_redist.x64.exe'} | set(ROOT_CMDS)


def main():
    if not PKG.is_dir():
        sys.exit(f'package folder missing: {PKG}')
    files = sorted(CACHE.glob('vulkan*.bin'))
    if not any(f.name.startswith('vulkan.') for f in files):
        sys.exit(f'no pipeline cache in {CACHE}')
    shutil.copy2(BIN / 'lichii.exe', PKG / 'Lichii' / 'lichii.exe')
    seed = PKG / 'Lichii' / 'shader_seed' / TITLE
    if seed.exists():
        for old in seed.glob('*'):
            old.unlink()
    seed.mkdir(parents=True, exist_ok=True)
    for f in files:
        if f.name.startswith(('vulkan.', 'vulkan_used.')):
            shutil.copy2(f, seed / f.name)
            print(f'seed {f.name} {f.stat().st_size // 1024} KiB')
    jit_seed = PKG / 'Lichii' / 'jit_seed' / TITLE
    if jit_seed.exists():
        for old in jit_seed.glob('*'):
            old.unlink()
    for f in sorted(JIT.glob('*.bin')):
        jit_seed.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, jit_seed / f.name)
        print(f'jit seed {f.name} {f.stat().st_size // 1024} KiB')
    host = PKG / 'lan_fix'
    host.mkdir(exist_ok=True)
    for name in HOST_FILES:
        shutil.copy2(WS / 'launcher' / 'lan_fix' / name, host / name)
    for old in PKG.glob('Host a match (*).cmd'):
        old.unlink()
    (PKG / f'Host a match ({VERSION}).cmd').write_bytes(HOST_CMD.encode('ascii'))
    # after the glob above: it also matches "Host a match (4 players).cmd" and deletes the old copy
    for name in ROOT_CMDS:
        shutil.copy2(WS / 'launcher' / 'lan_fix' / name, PKG / name)
    commit = subprocess.run(['git', '-C', str(WS / 'src' / 'lichii'), 'rev-parse', '--short=10', 'HEAD'],
                            capture_output=True, text=True).stdout.strip() or 'unknown'
    readme = (WS / 'tools' / 'share_readme.txt').read_text(encoding='utf-8')
    readme = (readme.replace('{commit}', commit).replace('{date}', time.strftime('%Y-%m-%d'))
              .replace('{version}', FULL_VERSION).replace('{hostcmd}', f'Host a match ({VERSION}).cmd'))
    (PKG / 'READ ME FIRST.txt').write_bytes(readme.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    print('host tools and readme written, commit', commit)
    tmp = ZIP.with_name(ZIP.name + '.tmp')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path in sorted(PKG.rglob('*')):
            # launcher_settings.json appears when the launcher is started from the package folder:
            # it holds this PC's paths and room password and must not be shared.
            # 2026-11-17: the package folder is also PLAYED from: never ship what playing leaves there
            # (the second player's data copy with keys and saves, logs, the lobby file, collected logs).
            rel = path.relative_to(PKG).as_posix()
            top = rel.split('/')[0]
            if top not in SHIP_ROOT and top != f'Host a match ({VERSION}).cmd':
                if '/' not in rel:
                    print('not shipped:', rel)
                continue
            if top == 'lan_fix' and '/' in rel and rel.split('/', 1)[1] not in HOST_FILES:
                continue
            if rel.startswith('Lichii/user/') or '__pycache__' in rel \
                    or path.suffix.lower() in ('.dmp', '.log', '.tmp', '.prev'):
                continue
            if path.is_file() and path.name != 'launcher_settings.json':   # review R3
                z.write(path, Path(PKG.name) / path.relative_to(PKG))
    tmp.replace(ZIP)
    print(f'{ZIP} {ZIP.stat().st_size // (1024 * 1024)} MB')


if __name__ == '__main__':
    main()
