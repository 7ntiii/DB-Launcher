"""Switch the launcher to a tested build, the release way (only after a joint match passed).

    python tools/switch_launcher.py 3.9.16          # dry run: prints what it would do, changes nothing
    python tools/switch_launcher.py 3.9.16 --do     # does it

Steps with --do:
  1. emulators/lichii-v<V>/ is filled from share/Duskbloods-Lichii-Online v<V>.zip (its Lichii/ folder) if missing;
     lichii.exe there must equal the zip's (sha256).
  2. launcher/launcher_settings.json is copied to launcher/launcher_settings.v<OLD>.json (OLD = the version the
     emulator line names now), unless that backup already exists.
  3. Only the "emulator" line of launcher_settings.json changes; every other byte stays.
Refuses while lichii.exe or the launcher runs. Never touches %APPDATA%, the firewall or any system setting.
"""
import hashlib, os, re, shutil, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS = os.path.join(ROOT, 'launcher', 'launcher_settings.json')
PREFIX = 'Duskbloods-Lichii-Online/Lichii/'


def running():
    out = subprocess.run(['tasklist'], capture_output=True, text=True).stdout.lower()
    return [n for n in ('lichii.exe', 'play.duskbloods.exe') if n in out]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    do = '--do' in sys.argv
    if len(args) != 1 or not re.fullmatch(r'\d+(\.\d+)+|alpha[0-9]+[a-z0-9]*', args[0]):
        sys.exit(__doc__)
    ver = args[0]
    zpath = os.path.join(ROOT, 'share', f'Duskbloods-Lichii-Online v{ver}.zip')
    dest = os.path.join(ROOT, 'emulators', f'lichii-v{ver}')
    if not os.path.isfile(zpath):
        sys.exit(f'no zip {zpath}')
    raw = open(SETTINGS, 'rb').read()
    text = raw.decode('utf-8')
    m = re.search(r'("emulator":\s*")([^"]*lichii-v([0-9a-z.]+)\\\\lichii\.exe)(")', text)
    if not m:
        sys.exit('emulator line not found in launcher_settings.json: nothing done')
    old = m.group(3)
    if old == ver:
        sys.exit(f'launcher already on v{ver}: nothing done')
    backup = os.path.join(ROOT, 'launcher', f'launcher_settings.v{old}.json')
    new_path = m.group(2).replace(f'lichii-v{old}', f'lichii-v{ver}')
    new_text = text[:m.start(2)] + new_path + text[m.end(2):]

    z = zipfile.ZipFile(zpath)
    members = [n for n in z.namelist() if n.startswith(PREFIX) and not n.endswith('/')]
    zexe = hashlib.sha256(z.read(PREFIX + 'lichii.exe')).hexdigest()
    print(f'launcher now: v{old}  ->  v{ver}')
    print(f'  emulator folder: {dest} ({"exists" if os.path.isdir(dest) else f"to unpack, {len(members)} files"})')
    print(f'  backup: {backup} ({"exists, kept" if os.path.exists(backup) else "to write"})')
    print(f'  new emulator line: {new_path}')
    busy = running()
    if busy:
        print(f'  RUNNING NOW: {busy} (close them first; --do refuses)')
    if not do:
        print('dry run: nothing changed (add --do)')
        return
    if busy:
        sys.exit('refused: close the games and the launcher first')
    if not os.path.isdir(dest):
        for n in members:
            out = os.path.join(dest, *n[len(PREFIX):].split('/'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with z.open(n) as src, open(out, 'wb') as dst:
                shutil.copyfileobj(src, dst)
    have = hashlib.sha256(open(os.path.join(dest, 'lichii.exe'), 'rb').read()).hexdigest()
    if have != zexe:
        sys.exit(f'refused: {dest}\\lichii.exe differs from the zip')
    if not os.path.exists(backup):
        shutil.copy2(SETTINGS, backup)
    open(SETTINGS, 'wb').write(new_text.encode('utf-8'))
    print(f'done: launcher on v{ver} (backup {os.path.basename(backup)})')


if __name__ == '__main__':
    main()
