r"""Switch which emulator launcher\Play.Duskbloods.exe starts.
Usage: python use_build.py ours   -> build\lichii\bin\lichii.exe (our source build, data in %APPDATA%\eden)
       python use_build.py v30    -> emulators\v30-eglantine\eglantine.exe (portable, data in its user\)"""
import json, sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
TARGETS = {
    'ours': W / 'build' / 'lichii' / 'bin' / 'lichii.exe',
    'v30': W / 'emulators' / 'v30-eglantine' / 'eglantine.exe',
}
which = sys.argv[1] if len(sys.argv) > 1 else ''
if which not in TARGETS:
    sys.exit(__doc__)
exe = TARGETS[which]
if not exe.exists():
    sys.exit(f'missing: {exe} (build it first with tools\build.cmd)')
p = W / 'launcher' / 'launcher_settings.json'
d = json.loads(p.read_text(encoding='utf-8'))
d['emulator'] = str(exe)
p.write_text(json.dumps(d, indent=2), encoding='utf-8')
print(f'launcher now starts: {exe}')
