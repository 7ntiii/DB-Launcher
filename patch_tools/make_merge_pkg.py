"""Test package from the UPSTREAM MERGE build (build/lichii-merge/bin): python tools/make_merge_pkg.py NAME [rel]
(rel: take the release build from build/lichii-merge-rel/bin, made by tools/build_merge_release.cmd)
Writes share/Duskbloods-Lichii-Online vNAME.zip: the current package folder (launcher, host tools, readme, seeds)
with every program file under Lichii/ replaced by the merged build's (exe, DLLs, plugins, qt.conf, nx2_switches)
and the shader seed replaced by the one in the merged build's cache format."""
import shutil
import sys
import zipfile
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
name = sys.argv[1]
src_pkg = WS / 'share' / 'Duskbloods-Lichii-Online'
tmp = WS / 'share' / '_merge_pkg'
if tmp.exists():
    shutil.rmtree(tmp)
dst = tmp / 'Duskbloods-Lichii-Online'
shutil.copytree(src_pkg, dst, ignore=shutil.ignore_patterns('SecondPlayer', 'launcher_settings.json', '*.log',
                                                            'host_profile'))
L = dst / 'Lichii'
# the test build, or (third argument 'rel') the release build without this PC's folder names inside
BIN = WS / 'build' / ('lichii-merge-rel' if sys.argv[2:3] == ['rel'] else 'lichii-merge') / 'bin'
for p in list(L.iterdir()):
    if p.is_file() and p.suffix.lower() in ('.exe', '.dll', '.conf'):
        p.unlink()
if (L / 'plugins').exists():
    shutil.rmtree(L / 'plugins')
for p in BIN.iterdir():
    if (p.is_file() and p.suffix.lower() in ('.dll', '.conf')) or p.name in ('lichii.exe', 'nx2_switches.txt'):
        shutil.copy2(p, L / p.name)
shutil.copytree(BIN / 'plugins', L / 'plugins')
if (BIN / 'licenses').exists():
    shutil.copytree(BIN / 'licenses', L / 'licenses', dirs_exist_ok=True)
# The shader seed in the merged build's format (shader cache v2), made once from the old seed by
# the build's own migration (build/merge_seed/<title>/lichii-cache.v2.bin); the old-format files go.
SEED = WS / 'build' / 'merge_seed'
for title in (SEED.iterdir() if SEED.exists() else ()):
    target = L / 'shader_seed' / title.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(title, target)
z = WS / 'share' / f'Duskbloods-Lichii-Online v{name}.zip'
if z.exists():
    z.unlink()
with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
    for p in dst.rglob('*'):
        if p.is_file():
            zf.write(p, p.relative_to(tmp).as_posix())
shutil.rmtree(tmp)
print(z.name, z.stat().st_size // 2 ** 20, 'MB')
