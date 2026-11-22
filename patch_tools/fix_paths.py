"""Rewrite old absolute paths (from before the workspace move, 2026-11-08) to workspace paths.
Safe to run again; only touches the files listed below."""
import json
from pathlib import Path

W = Path(__file__).resolve().parents[1]
V30 = W / 'emulators' / 'v30-eglantine'
GAME = W / 'game' / 'THE DUSKBLOODS' / 'THE DUSKBLOODS NETWORK TEST VER'

for p in (W / 'launcher' / 'launcher_settings.json', V30 / 'launcher_settings.json'):
    d = json.loads(p.read_text(encoding='utf-8'))
    d['game'] = GAME.as_posix()
    d['emulator'] = str(V30 / 'eglantine.exe')
    p.write_text(json.dumps(d, indent=2), encoding='utf-8')
    print('updated', p)

OLD = [
    ('C:\Users\<user>/Downloads/new build with less issues/Eglantine-Duskbloods-v30/Eglantine-Duskbloods-v30', V30.as_posix()),
    ('C:\Users\<user>/Downloads/duskblood testing/THE DUSKBLOODS', (W / 'game' / 'THE DUSKBLOODS').as_posix()),
]
for p in (V30 / 'user' / 'config' / 'qt-config.ini',):
    t = p.read_text(encoding='utf-8')
    n = sum(t.count(a) for a, _ in OLD)
    for a, b in OLD:
        t = t.replace(a, b)
    p.write_text(t, encoding='utf-8')
    print('updated', p, n, 'paths')
