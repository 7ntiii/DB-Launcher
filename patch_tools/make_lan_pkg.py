"""Packages with the NEW launcher (launcher2_src): python tools/make_lan_pkg.py EMULATOR_ZIP_NAME VERSION

    python tools/make_lan_pkg.py merge5 2.2
        -> <Downloads>/DuskbloodsGitHub/share/DB-Launcher Host v2.2.zip   for the player who opens the room
        -> <Downloads>/DuskbloodsGitHub/share/DB-Launcher Join v2.2.zip   for everyone else

Everything of the GitHub version lives in the DuskbloodsGitHub folder beside the workspace: 'share'
holds the newest packages (the ones to copy to another PC), 'old versions' the earlier ones.

Each zip: the Lichii folder out of share/Duskbloods-Lichii-Online v<EMULATOR_ZIP_NAME>.zip, the launcher
from launcher2_src/dist, a short readme and the room servers (servers/: the originals from
launcher_src/tools with our frontend_api.py / npln_stub.py from launcher/lan_fix on top). The join
package needs the servers too: "Play alone" runs a room on the player's own PC.
The servers are third-party files, so these zips are for our own players and are not the GitHub release.
"""
import shutil
import sys
import zipfile
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
SHARE = WS.parent / 'DuskbloodsGitHub' / 'share'
OLD = WS.parent / 'DuskbloodsGitHub' / 'old versions'
source = WS / 'share' / f'Duskbloods-Lichii-Online v{sys.argv[1]}.zip'
COMMON = '''
The first time: the dot at the top right shows what is missing. "Choose game folder" (bottom) picks your
own unpacked copy of the game; "Open keys folder" is where your own keys go.
If the game does not start, run vc_redist.x64.exe once.
Problems: press "Save logs" and send the zip to whoever helps you (it holds player names and local
network addresses, nothing else).
'''
README = {
    'Host': '''DB-LAUNCHER - HOST

For the player who opens the room. The others use the Join package.

1. Unpack this folder anywhere (not inside Program Files).
2. Start "DB-Launcher Host.exe" and type your name.
3. HOST A MATCH: pick how your players reach you (ZeroTier, Tailscale or the home network) and press
   OPEN THE ROOM. Your game starts and the window turns into your room: the address for your players,
   who is connected, their ping, and the match controls.
4. When the players are searching in the game, press START MATCH. A match never starts by itself.
   PLAY ALONE starts the game with a room on this PC only.
''' + COMMON,
    'Join': '''DB-LAUNCHER - JOIN

For every player except the host.

1. Unpack this folder anywhere (not inside Program Files).
2. Start "DB-Launcher Join.exe" and type your name.
3. JOIN A MATCH: pick how you reach the host (ZeroTier, Tailscale or the home network). The open rooms
   appear by themselves; click a room and the game starts.
4. In the game, open Dusk Battle and start matchmaking. The host starts the match.
   PLAY ALONE starts the game with a room on this PC only.
''' + COMMON,
}
SERVERS = {
    'servers/dusk_server/frontdoor.py': WS / 'launcher_src/tools/dusk_server/frontdoor.py',
    'servers/dusk_server/response_schemas.json': WS / 'launcher_src/tools/dusk_server/response_schemas.json',
    'servers/dusk_server/frontend_api.py': WS / 'launcher/lan_fix/frontend_api.py',
    'servers/npln_server/npln_stub.py': WS / 'launcher/lan_fix/npln_stub.py',
    'servers/npln_server/make_pki.py': WS / 'launcher_src/tools/npln_server/make_pki.py',
    'servers/npln_server/npln_accounts.py': WS / 'launcher_src/tools/npln_server/npln_accounts.py',
    'servers/npln_server/npln_dashboard.py': WS / 'launcher_src/tools/npln_server/npln_dashboard.py',
}
SHARE.mkdir(parents=True, exist_ok=True)
OLD.mkdir(parents=True, exist_ok=True)
for earlier in list(SHARE.glob('Duskbloods-LAN *.zip')) + list(SHARE.glob('DB-Launcher *.zip')):          # share holds the newest version only
    if f' v{sys.argv[2]}.zip' not in earlier.name:
        shutil.move(str(earlier), str(OLD / earlier.name))
for role in ('Host', 'Join'):
    target = SHARE / f'DB-Launcher {role} v{sys.argv[2]}.zip'
    root = f'DB-Launcher-{role}/'
    exe = WS / 'launcher2_src' / 'dist' / f'DB-Launcher {role}.exe'
    if target.exists():
        target.unlink()
    count = 0
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as new:
        for item in old.infolist():
            rel = item.filename.split('/', 1)[1] if '/' in item.filename else ''
            if item.is_dir() or not (rel.startswith('Lichii/') or rel == 'vc_redist.x64.exe'):
                continue
            new.writestr(root + rel, old.read(item))
            count += 1
        new.write(exe, root + exe.name)
        for rel, path in SERVERS.items():
            new.write(path, root + rel)
        new.writestr(root + 'READ ME FIRST.txt', README[role].replace('\n', '\r\n'))
        # the license of the project and of the emulator, and who made what
        new.write(WS / 'launcher2_src' / 'LICENSE.txt', root + 'LICENSE.txt')
        new.write(WS / 'launcher2_src' / 'NOTICE.txt', root + 'NOTICE.txt')
        new.write(WS / 'src' / 'lichii-merge' / 'LICENSE.txt', root + 'Lichii/LICENSE.txt')
        for text in sorted((WS / 'src' / 'lichii-merge' / 'LICENSES').glob('*.txt')):
            new.write(text, root + 'Lichii/licenses/' + text.name)
    print(target, target.stat().st_size // 2 ** 20, 'MB,', count, 'emulator files')
