"""Builds the launcher with PyInstaller, then makes the two named copies players get.

    pip install pyinstaller cryptography grpcio
    python build.py

    dist/DB-Launcher.exe        everything (join, host, play alone): for testing
    dist/DB-Launcher Host.exe   host a match, play alone
    dist/DB-Launcher Join.exe   join a match, play alone

The three files are the same program: its file name decides what it offers (dusklan/__init__.py).

The launcher itself uses only the standard library. cryptography and grpc are packed in because the
room servers (run by this same program with --run-script) import them; the modules listed below are
the standard-library ones those servers use and the launcher does not.

Build from a folder whose path holds nothing personal: PyInstaller writes the build path into the
program's debug strings.
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER_MODULES = ('argparse base64 copy datetime getpass hashlib hmac http.server ipaddress json math queue '
                  'secrets select socket sqlite3 ssl struct threading collections concurrent.futures').split()

command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed', '--noupx',
           '--name', 'DB-Launcher', '--collect-submodules', 'cryptography', '--collect-submodules', 'grpc',
           '--collect-submodules', 'dusklan', '--add-data', 'ui;ui',
           '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog']
if (HERE / 'assets' / 'icon.ico').is_file():
    command += ['--icon', 'assets/icon.ico', '--add-data', 'assets;assets']
for module in SERVER_MODULES:
    command += ['--hidden-import', module]
subprocess.check_call(command + ['db_launcher.py'], cwd=HERE)
built = HERE / 'dist' / 'DB-Launcher.exe'
for role in ('Host', 'Join'):
    shutil.copyfile(built, built.with_name(f'DB-Launcher {role}.exe'))
print('built:', built, '+ Host and Join copies')
