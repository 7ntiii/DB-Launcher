"""TEST RIG ONLY: set the log filter of rig game 1's own config (never %APPDATA%).
python diag/twin/rig_logfilter.py "FILTER"     e.g. "*:Warning Service:Info Network:Info"   (no argument: show)"""
import sys
from pathlib import Path

p = Path(__file__).resolve().parent / 'pkgtest' / 'Duskbloods-Lichii-Online' / 'Lichii' / 'user' / 'config' / 'qt-config.ini'
lines = p.read_text(encoding='utf-8', errors='replace').splitlines()
for i, line in enumerate(lines):
    if line.startswith('log_filter='):
        print('was:', line)
        if len(sys.argv) > 1:
            lines[i] = 'log_filter="%s"' % sys.argv[1]
            print('now:', lines[i])
if len(sys.argv) > 1:
    p.write_text('\n'.join(lines) + '\n', encoding='utf-8')
