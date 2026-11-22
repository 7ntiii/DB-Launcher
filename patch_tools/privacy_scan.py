"""Deep privacy scan of what we share: python tools/privacy_scan.py [FOLDER_OR_ZIP ...]

Default targets: every zip in <Downloads>/DuskbloodsGitHub/share and the folder <Downloads>/DuskbloodsGitHub/source.

Looks, in every file (zips are opened, the launcher program's packed Python modules are unpacked and
read too), for: this PC's user name and PC name, the parts of the e-mail address git is set up with,
this PC's network addresses and adapter hardware addresses, the Windows account id, user-folder paths,
any e-mail address, and ZeroTier network ids from this PC. Text is searched as plain bytes and as the
two-byte form Windows programs use. Prints file and finding only; the words searched for are not
printed in full.
"""
import getpass
import io
import marshal
import re
import socket
import subprocess
import sys
import zipfile
import zlib
from pathlib import Path

HOME = Path.home()
GIT = HOME / 'Downloads' / 'DuskbloodsGitHub'


def run(*command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return ''


def words():
    """{label: bytes to look for} from this PC itself (nothing personal is written into this file)."""
    found = {}
    user = getpass.getuser()
    found['user name'] = user
    found['user name without marks'] = re.sub(r'[^A-Za-z0-9]', '', user)
    found['PC name'] = socket.gethostname()
    mail = run('git', 'config', '--global', 'user.email').strip() or \
        run('git', '-C', str(HOME / 'Downloads' / 'DuskbloodsWorkspace' / 'src' / 'lichii-merge'), 'log', '-1', '--format=%ae').strip()
    if '@' in mail and 'noreply' not in mail:
        found['e-mail address'] = mail
        found['e-mail name'] = mail.split('@')[0]
    name = run('git', 'config', '--global', 'user.name').strip()
    if len(name) >= 4:
        found['git name'] = name
    for i, ip in enumerate(sorted(set(re.findall(r'IPv4[^:]*:\s*([0-9.]+)', run('ipconfig'))))):
        if not ip.startswith('127.'):
            found[f'network address {i + 1}'] = ip
    for i, mac in enumerate(sorted(set(re.findall(r'(?:[0-9A-F]{2}-){5}[0-9A-F]{2}', run('getmac'))))):
        found[f'adapter hardware address {i + 1}'] = mac
        found[f'adapter hardware address {i + 1} (colons)'] = mac.replace('-', ':')
    sid = re.search(r'S-1-5-21-[0-9-]+', run('whoami', '/user'))
    if sid:
        found['Windows account id'] = sid.group(0)
    for i, net in enumerate(sorted(set(re.findall(r'\b[0-9a-f]{16}\b', run('zerotier-cli', 'listnetworks'))))):
        found[f'ZeroTier network id {i + 1}'] = net
    return {k: v for k, v in found.items() if len(v) >= 4}


WORDS = words()
NEEDLES = []
for label, word in WORDS.items():
    low = word.lower().encode()
    NEEDLES.append((label, low))
    NEEDLES.append((label + ' (Windows text)', word.lower().encode('utf-16le')))
GENERIC = [
    ('a user-folder path', re.compile(rb'[a-z]:[\\/]+users[\\/]+(?!public|default|<user>|runneradmin|vssadministrator|%|\$|\{|user[\\/]|username|name[\\/]|me[\\/]|you[\\/])[a-z0-9._ -]{2,30}[\\/]')),
    ('an e-mail address', re.compile(rb'[a-z0-9._%+-]{2,40}@(?:outlook|hotmail|gmail|yahoo|live|icloud|proton)[a-z.]*\.[a-z]{2,6}')),
    ('a PC name (DESKTOP-/LAPTOP-)', re.compile(rb'(?:desktop|laptop)-[a-z0-9]{7}\b')),
]


def scan(name, data, hits):
    low = data.lower()
    for label, needle in NEEDLES:
        if needle in low:
            hits.append((name, label, low.count(needle)))
    for label, pattern in GENERIC:
        found = pattern.findall(low)
        if found:
            hits.append((name, label + ': ' + found[0][:60].decode('ascii', 'replace'), len(found)))


def packed_modules(data):
    """The Python modules inside a PyInstaller one-file program: yields (name, bytes) for every packed
    piece (uncompressed), including each module of its PYZ library."""
    magic = b'MEI\014\013\012\013\016'
    at = data.rfind(magic)
    if at < 0:
        return
    import struct
    length, toc_at, toc_len = struct.unpack('!iii', data[at + 8:at + 20])
    start = at + 88 - length                  # the archive's first byte (cookie is 88 bytes, at its end)
    toc = data[start + toc_at:start + toc_at + toc_len]
    pos = 0
    while pos < len(toc):
        size, = struct.unpack('!i', toc[pos:pos + 4])
        entry_at, packed, _full, flag, kind = struct.unpack('!iiiBc', toc[pos + 4:pos + 18])
        name = toc[pos + 18:pos + size].rstrip(b'\0').decode('utf-8', 'replace')
        blob = data[start + entry_at:start + entry_at + packed]
        if flag:
            try:
                blob = zlib.decompress(blob)
            except zlib.error:
                pass
        yield name, blob
        if kind == b'z' and blob[:4] == b'PYZ\0':
            toc_pos, = struct.unpack('!i', blob[8:12])
            try:
                table = marshal.loads(blob[toc_pos:])
            except Exception:
                table = []
            rows = table.items() if isinstance(table, dict) else table
            for key, (_is_pkg, mod_at, mod_len) in rows:
                try:
                    yield f'{name}/{key}', zlib.decompress(blob[mod_at:mod_at + mod_len])
                except zlib.error:
                    yield f'{name}/{key}', blob[mod_at:mod_at + mod_len]
        pos += size


def scan_file(name, data, hits, counts):
    counts[0] += 1
    scan(name, data, hits)
    if name.lower().endswith('.exe') and b'MEI\014\013\012\013\016' in data[-4096:] or \
            (name.lower().endswith('.exe') and 'launcher' in name.lower()):
        for inner, blob in packed_modules(data):
            counts[1] += 1
            scan(f'{name} >> {inner}', blob, hits)
    if name.lower().endswith('.zip'):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for item in z.infolist():
                    if not item.is_dir():
                        scan_file(f'{name} > {item.filename}', z.read(item), hits, counts)
        except zipfile.BadZipFile:
            pass


targets = [Path(a) for a in sys.argv[1:]] or sorted((GIT / 'share').glob('*.zip')) + [GIT / 'source']
print('searching for', len(WORDS), 'personal words of this PC:', ', '.join(WORDS))
total = 0
for target in targets:
    hits, counts = [], [0, 0]
    if target.is_dir():
        for p in target.rglob('*'):
            if p.is_file():
                scan_file(str(p.relative_to(target)), p.read_bytes(), hits, counts)
    else:
        with zipfile.ZipFile(target) as z:
            for item in z.infolist():
                if not item.is_dir():
                    scan_file(item.filename, z.read(item), hits, counts)
    print(f'\n{target.name}: {counts[0]} files, {counts[1]} packed program pieces read, {len(hits)} finding(s)')
    for name, label, n in hits[:60]:
        print(f'   {name}: {label} x{n}')
    total += len(hits)
print('\nTOTAL findings:', total)
