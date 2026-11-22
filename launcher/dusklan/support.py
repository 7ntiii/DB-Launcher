"""Logs for whoever helps with a problem: one zip, saved next to the launcher or sent to the host PC.

The logs hold player names and the local network addresses of the match. They are only read here,
never moved or deleted, and they go nowhere unless the player presses one of the two buttons.
"""
import io
import socket
import time
import urllib.request
import zipfile
from pathlib import Path

from . import VERSION, config

GAME_LOGS = ('dusk_lan', 'eden_log')


def collect(data, results=()):
    """(zip bytes, number of files): game logs, the last sessions' server logs, and the health check."""
    stamp = time.strftime('%Y-%m-%d %H:%M:%S')
    buffer, count = io.BytesIO(), 0
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        log_dir = Path(data) / 'log' if data else None
        if log_dir and log_dir.is_dir():
            for f in sorted(log_dir.iterdir()):
                if f.is_file() and (f.name.startswith(GAME_LOGS) or f.name == 'dusk_lan_status.json'):
                    count += _add(z, f, 'game/' + f.name)
        runs = config.play_dir(Path(data)) / 'runs' if data else None
        if runs and runs.is_dir():
            for run in sorted(p for p in runs.iterdir() if p.is_dir())[-3:]:
                for f in sorted(run.iterdir()):
                    if f.is_file() and f.suffix == '.log' and f.stat().st_size < 30_000_000:
                        count += _add(z, f, f'sessions/{run.name}/{f.name}')
        if config.LOG_FILE.is_file():
            count += _add(z, config.LOG_FILE, 'launcher/' + config.LOG_FILE.name)
        check = '\n'.join(f'[{r.level}] {r.title} | {r.detail}'.rstrip(' |') for r in results)
        z.writestr('SUMMARY.txt', f'DB-Launcher {VERSION}, collected {stamp}\n{count} file(s)\n\n'
                                  f'Health check:\n{check}\n')
    return buffer.getvalue(), count


def _add(z, path, name):
    try:
        z.writestr(name, path.read_bytes())
        return 1
    except OSError:
        return 0


def save(data, results=()):
    """Write the zip next to the launcher; returns its path (None when there are no logs yet)."""
    blob, count = collect(data, results)
    if not count:
        return None
    path = config.BASE / f'DuskLogs_{time.strftime("%Y-%m-%d_%H%M%S")}.zip'
    path.write_bytes(blob)
    return path


def send_to_host(host, data, results=()):
    """Hand the zip to the host PC's log inbox (its update service). Returns the host's answer."""
    blob, count = collect(data, results)
    if not count:
        raise OSError('no game logs on this PC yet (play a match first)')
    pc = ''.join(c for c in socket.gethostname() if c.isalnum() or c in '-_')[:32] or 'pc'
    stamp = time.strftime('%Y-%m-%d_%H%M%S')
    request = urllib.request.Request(f'http://{host}:{config.UPDATE_PORT}/logs?pc={pc}&at={stamp}', data=blob,
                                     method='POST', headers={'Content-Type': 'application/zip'})
    with urllib.request.urlopen(request, timeout=300) as reply:
        return reply.read().decode('ascii', 'replace').strip()
