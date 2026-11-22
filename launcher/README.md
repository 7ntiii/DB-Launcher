# DB-Launcher

A small launcher for playing the DB network test with friends over a home network or a VPN
(ZeroTier, Tailscale), on the Lichii emulator build that goes with it.

It was written from zero. It comes as two programs made from the same code (the file name decides
which one it is):

- **DB-Launcher Host.exe**: opens a room, steers the match, or plays alone.
- **DB-Launcher Join.exe**: joins a room, or plays alone.

What it does:

1. **Checks** the PC before the game starts and says in plain words what to fix.
2. **Finds rooms by itself**: pick ZeroTier, Tailscale or the home network, click a room, the game starts.
3. **Gives the host one window** for the whole match: players and their ping, Start match, cancel,
   messages to the players, and the host's match tools.

You bring your own copy of the game and your own keys. Neither is part of this project.

## Folder layout

```
DB-Launcher Host.exe     the launcher (or "... Join.exe")
db_launcher.json         its settings (made at the first start)
background.jpg / .png       optional: your own picture behind the window (not part of this project)
Lichii/                     the emulator build (lichii.exe ...)
servers/                    the room servers: needed to host and to play alone
    dusk_server/            frontdoor.py, frontend_api.py, response_schemas.json
    npln_server/            npln_stub.py, make_pki.py, npln_accounts.py, npln_dashboard.py
```

The window is a page (`ui/index.html`, packed into the program) shown in a window of its own by Edge
or Chrome; it talks only to the launcher on the same PC. Its drawing (moon, spires, embers) is ours;
no game artwork is included.

## Playing

Type **your name** first: it is the name the game shows for you.

**Join a match.** Pick how you reach the host. The rooms that are open on that network appear by
themselves and the list keeps itself fresh; click a room and the game starts. On ZeroTier networks
larger than about a thousand addresses the search looks at the addresses near your own and at the
PCs Windows already knows; on Tailscale it asks Tailscale for the devices. An address can also be typed.

**Host a match.** Pick the network your players come from and press *Open the room*. The window turns
into your room: the address to give out, every player with their state and ping (measured every
second), and the match controls. **A match starts only when the host presses Start match**; the
launcher offers no automatic start and sets the match server to "host starts" each time a room opens.
*Cancel match* makes the server forget the running match; *Remove all searching* ends every search.
The host is always player 1.

**Host tools** (while a match runs, on the host's own game): full health, cannot die, freeze the match
time, hold the nearest boss's health, go to a player. See `dusklan/hosttools.py`.

**Play alone.** Starts the game with a room on this PC only.

## The health check

Shown at the top of the window, repeated at every start. Nothing is changed on the PC; every fix is a
sentence for you.

| Check | What it catches |
| --- | --- |
| Emulator | missing, a build without the room switches, missing Visual C++ runtime |
| Game files | no game chosen; an incomplete copy (it starts, then stays on a black screen) |
| Keys | prod.keys missing |
| Memory, disk | under about 10 GB of free memory, under 8 GB of free disk |
| Graphics card | under 8 GB of video memory (NVIDIA cards): frame drops at high resolution |
| Network | no network; a VPN network Windows labels "Public", which blocks the other players |
| Room servers, ports | (hosting) the servers folder is missing, or a room is already running |

## Updates

Not in the window at the moment (the module `dusklan/updates.py` is kept for later).

Setup > *Updates: GitHub repository* takes `owner/name`. At start the launcher asks that repository's
public release list (no account, no token) for the newest release. A release that carries an update
has **one asset named `update*.zip`**; its paths are relative to the launcher's folder, for example
`Lichii/lichii.exe`. The zip is checked against the SHA-256 GitHub publishes for it before any file is
replaced. Saves, keys, settings and the game can never be part of an update: such paths are refused.

Without a repository, *Update from host PC* fetches the emulator program from the host of your room.

## Running from source

```
python db_launcher.py                 the window
python db_launcher.py --check host    the health check as text
python db_launcher.py --host          host without the window
python db_launcher.py --join ADDRESS  join without the window
python build.py                          dist/DB-Launcher.exe  (pip install pyinstaller cryptography grpcio)
```

Only the Python standard library is used by the launcher itself. `cryptography` and `grpcio` are
packed into the .exe because the room servers need them.

## Hosting needs the room servers

The room servers (the `servers` folder) are separate programs and are not part of this launcher's
source. A copy without that folder can join rooms but not host them.

## Privacy

The launcher talks to: the room you join or host (inside your network or VPN), GitHub's release list
when a repository is set, and nothing else. Logs hold player names and local network addresses; they
leave the PC only when you press *Save logs* (a file for you to send) or *Send logs to host*.

## Credits

- **sikoGD**, [playDB-CNT](https://github.com/sikoGD/playDB-CNT): the room servers a host runs.
- **Lichii** (https://github.com/zortos293/Lichii) and the projects it builds on: the emulator.

## License

GPL-3.0-or-later: see `LICENSE.txt`. Who made which part of a package, and the licenses of the parts that are not ours, are in `NOTICE.txt`.
