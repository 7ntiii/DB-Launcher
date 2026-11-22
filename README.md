# DB-Launcher

Play the DB network test with friends over a home network or a VPN (ZeroTier, Tailscale), on a changed
build of the Lichii emulator.

You need your own copy of the game and your own keys. Neither is part of this project.

## Download

Get the newest package from **Releases**:

- **DB-Launcher Host**: for the player who opens the room.
- **DB-Launcher Join**: for everyone else.

Unpack it anywhere (not inside Program Files) and start the launcher. Each package has a
`READ ME FIRST.txt` with the steps.

## What it does

- Checks the PC before the game starts and says in plain words what to fix.
- Finds open rooms by itself: pick ZeroTier, Tailscale or the home network, click a room, the game starts.
- Gives the host one window for the whole match: players and their ping, Start match, cancel,
  messages to the players, and the host's match tools.
- A match starts only when the host presses Start match.

Proven with 2 and 3 players. More players are built in but not tested.

## What is in this repository

| Folder | What it is |
|---|---|
| `launcher/` | The launcher's source (Python, standard library only). `python build.py` builds the programs. |
| `emulator/` | Our changes to the Lichii emulator as two patch files, and the Lichii commit they apply to. |
| `host_tools/` | Our changes to the room servers as patch files, and scripts from the earlier setup. |
| `patch_tools/` | The tools that make and check our changes. |
| `test_tools/` | The scripts of our two-game test rig. |

## Credits

- **sikoGD**, [playDB-CNT](https://github.com/sikoGD/playDB-CNT): the room servers a host runs.
- **Lichii** (https://github.com/zortos293/Lichii) and the projects it builds on (Eglantine, Eden, yuzu,
  Sudachi): the emulator.

## License

GPL-3.0-or-later: see `LICENSE.txt`. Who made which part, and the licenses of the parts that are not
ours, are in `NOTICE.txt`.

This is a fan project. It is not affiliated with, endorsed by or connected to the makers or publishers
of any game or console.
