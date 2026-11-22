"""Updates: from a GitHub repository's releases, or from the host PC of your room.

GitHub (the normal way). The repository is a setting ("owner/name"). A release that carries updates
has one asset whose name starts with "update" and ends with ".zip". Inside, paths are relative to the
folder this launcher lies in, for example:

    DB-Launcher.exe
    Lichii/lichii.exe
    servers/dusk_server/frontend_api.py

Only what the zip holds is replaced; saves, keys, settings and the game are never part of it and paths
that point at them are refused. Every file is checked against the release's SHA-256 before anything
is replaced (GitHub publishes it for each asset; an "<asset>.sha256" asset works too).

Only the repository's public release API is asked (no account, no token); the request carries nothing
about this PC beyond what any web request does.

Host PC (when GitHub is not set up): the host's update service on port 18480 hands out its emulator
program; see from_host().
"""
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import VERSION, config

AGENT = {'User-Agent': 'db-launcher/' + VERSION, 'Accept': 'application/vnd.github+json'}
PROTECTED = ('user/', 'keys/', 'db_launcher.json', 'launcher_settings.json', 'updates/')
REPO_FORM = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')


class UpdateError(Exception):
    pass


def clean_repo(text):
    """'https://github.com/owner/name/' or 'owner/name' -> 'owner/name' ('' when it is neither)."""
    text = (text or '').strip().removesuffix('.git').strip('/')
    text = re.sub(r'^https?://(www\.)?github\.com/', '', text)
    text = '/'.join(text.split('/')[:2])
    return text if REPO_FORM.match(text) else ''


def _get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=timeout) as reply:
        return reply.read()


def latest(repo):
    """The newest release: {'tag', 'title', 'notes', 'asset': {'name','url','size','sha256'} or None}."""
    repo = clean_repo(repo)
    if not repo:
        raise UpdateError('No update repository is set (Setup > Updates).')
    try:
        release = json.loads(_get(f'https://api.github.com/repos/{repo}/releases/latest'))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise UpdateError(f'{repo} has no published release yet (or the repository is private).') from error
        raise UpdateError(f'GitHub answered {error.code}.') from error
    except (OSError, ValueError) as error:
        raise UpdateError(f'GitHub could not be reached ({error}).') from error
    assets = release.get('assets') or []
    package = next((a for a in assets if a.get('name', '').lower().startswith('update')
                    and a.get('name', '').lower().endswith('.zip')), None)
    asset = None
    if package:
        digest = str(package.get('digest') or '')
        sha = digest.split(':', 1)[1] if digest.startswith('sha256:') else ''
        if not sha:
            side = next((a for a in assets if a.get('name') == package['name'] + '.sha256'), None)
            if side:
                try:
                    sha = _get(side['browser_download_url']).decode('ascii', 'replace').split()[0].lower()
                except (OSError, IndexError):
                    sha = ''
        asset = {'name': package['name'], 'url': package['browser_download_url'],
                 'size': int(package.get('size') or 0), 'sha256': sha.lower()}
    return {'tag': str(release.get('tag_name') or ''), 'title': str(release.get('name') or ''),
            'notes': str(release.get('body') or '').strip(), 'asset': asset}


def is_newer(tag, installed):
    """A release counts as new when its tag differs from the installed one and is not older by number."""
    if not tag or tag == installed:
        return False
    numbers = lambda text: [int(n) for n in re.findall(r'\d+', text)]     # noqa: E731
    return not installed or numbers(tag) >= numbers(installed)


def install(release, progress=None, game_running=lambda: False):
    """Download the release's update zip, check it, and replace the files it holds.

    Returns (list of replaced paths, restart needed). Nothing is replaced unless the whole zip arrived
    and matches its SHA-256.
    """
    asset = release.get('asset')
    if not asset:
        raise UpdateError('This release has no update package (an asset named update*.zip).')
    if game_running():
        raise UpdateError('Close the game first: its files cannot be replaced while it runs.')
    if not asset['sha256']:
        raise UpdateError('The release gives no SHA-256 for its package, so it cannot be checked. Not installed.')
    folder = config.BASE / 'updates'
    folder.mkdir(exist_ok=True)
    target = folder / re.sub(r'[^0-9A-Za-z._-]', '_', f"{release['tag']}_{asset['name']}")
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(asset['url'], headers={'User-Agent': AGENT['User-Agent']})
        with urllib.request.urlopen(request, timeout=60) as reply, target.open('wb') as out:
            got = 0
            while True:
                block = reply.read(1 << 18)
                if not block:
                    break
                out.write(block)
                digest.update(block)
                got += len(block)
                if progress:
                    progress(got, asset['size'])
    except OSError as error:
        target.unlink(missing_ok=True)
        raise UpdateError(f'The download stopped ({error}). Nothing was changed.') from error
    if digest.hexdigest() != asset['sha256']:
        target.unlink(missing_ok=True)
        raise UpdateError('The package did not arrive complete (its check sum is wrong). Nothing was changed.')
    try:
        replaced, restart = unpack(target, config.BASE)
    finally:
        target.unlink(missing_ok=True)
    return replaced, restart


def unpack(archive, base):
    """Replace files under `base` with the zip's. Returns (replaced paths, restart needed)."""
    base = Path(base).resolve()
    own = Path(sys.executable).resolve() if config.FROZEN else None
    replaced, restart = [], False
    with zipfile.ZipFile(archive) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        for member in members:                     # look at every path before touching anything
            rel = member.filename.replace('\\', '/').lstrip('/')
            destination = (base / rel).resolve()
            if base not in destination.parents or rel.lower().startswith(PROTECTED) or '/user/' in '/' + rel.lower():
                raise UpdateError(f'The package holds a path it must not replace ({rel}). Not installed.')
        for member in members:
            rel = member.filename.replace('\\', '/').lstrip('/')
            destination = base / rel
            data = z.read(member)
            if destination.is_file() and destination.stat().st_size == len(data) and destination.read_bytes() == data:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            fresh = destination.with_name(destination.name + '.new')
            fresh.write_bytes(data)
            if own and destination.resolve() == own:
                # a running program cannot be overwritten, but it can be renamed: the new one takes its name
                old = destination.with_name(destination.name + '.old')
                old.unlink(missing_ok=True)
                os.replace(destination, old)
                restart = True
            os.replace(fresh, destination)
            replaced.append(rel)
    return replaced, restart


def from_host(host, emulator, log, game_running=lambda: False):
    """Fetch the host PC's emulator program (its update service, port 18480). The old one stays as .old.

    Returns the build name now installed, or '' when this PC already had it.
    """
    if game_running():
        raise UpdateError('Close the game first.')
    base = f'http://{host}:{config.UPDATE_PORT}'
    try:
        info = json.loads(_get(base + '/version.txt').decode('ascii'))
        files = info['files']
        have = hashlib.sha256(Path(emulator).read_bytes()).hexdigest()
        if have == files['lichii.exe']['sha256']:
            return ''
        fetched = []
        for name, meta in files.items():
            if '/' in name or '\\' in name or name.startswith('.'):
                raise UpdateError(f'The host offers a file name this launcher refuses ({name}).')
            log(f'Fetching {name} ({meta["size"] // 1048576} MB) ...')
            data = _get(f'{base}/{name}', timeout=600)
            if hashlib.sha256(data).hexdigest() != meta['sha256']:
                raise UpdateError(f'{name} did not arrive complete. Nothing was changed.')
            fetched.append((name, data))
    except (OSError, ValueError, KeyError) as error:
        raise UpdateError(f'The host PC\'s update service did not answer ({error}). Is the host ready?') from error
    folder = Path(emulator).parent
    keep = folder / (Path(emulator).name + '.old')
    keep.write_bytes(Path(emulator).read_bytes())
    for name, data in fetched:
        destination = Path(emulator) if name == 'lichii.exe' else folder / name
        fresh = destination.with_name(destination.name + '.new')
        fresh.write_bytes(data)
        os.replace(fresh, destination)
    return str(info.get('build') or 'new build')
