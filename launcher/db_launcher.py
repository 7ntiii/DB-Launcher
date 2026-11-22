"""DB-Launcher: start here.

    python db_launcher.py                 the window
    python db_launcher.py --check [mode]  the health check as text (mode: join | host | solo)
    python db_launcher.py --host          host a match without the window (settings from the last time)
    python db_launcher.py --join ADDRESS  join the room at ADDRESS without the window
    python db_launcher.py --solo          play alone without the window
    <program> --run-script file.py args...   run a room-server script with the Python packed into the program
"""
import os
import runpy
import sys
from pathlib import Path


def run_script():
    script = Path(sys.argv[2]).resolve()
    sys.argv = [str(script)] + sys.argv[3:]
    sys.path.insert(0, str(script.parent))
    os.chdir(script.parent)
    runpy.run_path(str(script), run_name='__main__')


def check_as_text(mode):
    from dusklan import checks, config
    results, _found = checks.run_all(config.load(), mode)
    for r in results:
        print(f'[{r.level:4}] {r.title}' + (f'\n       {r.detail}' if r.detail else '')
              + (f'\n       fix: {r.fix}' if r.fix else ''))
    return 1 if any(r.level == checks.FAIL for r in results) else 0


def play_without_window(mode, address=''):
    from dusklan import APP_NAME, ROLE_MODES, config, game
    from dusklan.session import Session
    if mode not in ROLE_MODES:
        print(f'{APP_NAME} cannot do "{mode}": use the other launcher for that.', flush=True)
        return 1
    settings = config.load()
    if address:
        settings['host_address'] = address

    def log(text, error=False):
        config.note(('! ' if error else '') + text)
        print(text, flush=True)

    session = Session(settings, mode, None, log)
    try:
        session.start()
    except game.StartError as error:
        log(str(error), error=True)
        return 1
    try:
        session.wait()
    except KeyboardInterrupt:
        session.stop()
    return 0


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--run-script':
        run_script()
    elif len(sys.argv) > 1 and sys.argv[1] == '--check':
        sys.exit(check_as_text(sys.argv[2] if len(sys.argv) > 2 else 'join'))
    elif len(sys.argv) > 1 and sys.argv[1] == '--host':
        sys.exit(play_without_window('host'))
    elif len(sys.argv) > 1 and sys.argv[1] == '--solo':
        sys.exit(play_without_window('solo'))
    elif len(sys.argv) > 2 and sys.argv[1] == '--join':
        sys.exit(play_without_window('join', sys.argv[2]))
    else:
        from dusklan import web
        web.run()
