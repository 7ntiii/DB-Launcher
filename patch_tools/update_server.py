"""Serve the newest game program to the other PCs of the home network, for "Update from host.cmd".

    python tools/update_server.py "share/Duskbloods-Lichii-Online valpha13.zip"   # publish that build and serve
    python tools/update_server.py                                              # serve what is published

It copies Lichii/lichii.exe and Lichii/nx2_switches.txt out of the zip into share/update/ and writes
version.txt (name, sha256, size). Then it serves ONLY those three files over plain HTTP on this PC's LAN address,
port 18480, read only (no listing, no other path). Nothing is uploaded anywhere; no Windows setting is changed.
Stop it with Ctrl+C (or by closing its task).
"""
import hashlib
import http.server
import json
import os
import socket
import sys
import zipfile

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPD = os.path.join(WS, 'share', 'update')
FILES = ('lichii.exe', 'nx2_switches.txt', 'version.txt')
PORT = 18480


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.168.1.1', 9))   # no packet is sent: this only picks the LAN interface
        return s.getsockname()[0]
    finally:
        s.close()


def publish(zpath):
    os.makedirs(UPD, exist_ok=True)
    z = zipfile.ZipFile(zpath)
    info = {'build': os.path.basename(zpath).replace('Duskbloods-Lichii-Online ', '').replace('.zip', ''), 'files': {}}
    for name in ('lichii.exe', 'nx2_switches.txt'):
        data = z.read('Duskbloods-Lichii-Online/Lichii/' + name)
        open(os.path.join(UPD, name), 'wb').write(data)
        info['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    # the rest of the package (launcher 1.5+ updates these too): the launcher itself, the host tools, the readme
    info['package'] = {}
    pkg_dir = os.path.join(UPD, 'pkg')
    for member in z.namelist():
        rel = member[len('Duskbloods-Lichii-Online/'):]
        if member.endswith('/') or not rel or rel.startswith(('Lichii/', 'SecondPlayer/')) or rel == 'vc_redist.x64.exe':
            continue
        data = z.read(member)
        out = os.path.join(pkg_dir, *rel.split('/'))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(data)
        info['package'][rel] = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    try:   # the first "WHAT'S NEW" block of the package's readme: shown to the player after the update
        text = z.read('Duskbloods-Lichii-Online/READ ME FIRST.txt').decode('ascii', 'replace').replace('\r', '')
        start = text.index("WHAT'S NEW")
        block = text[start:].split('\n\n')[0].strip().splitlines()
        info['notes'] = [ln.rstrip() for ln in block][:14]
    except Exception:
        info['notes'] = []
    info['published'] = __import__('time').strftime('%Y-%m-%d %H:%M')
    open(os.path.join(UPD, 'version.txt'), 'w', encoding='ascii', newline='\n').write(json.dumps(info, indent=1))
    print('published', info['build'], info['files']['lichii.exe']['sha256'][:16], flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import unquote
        name = unquote(self.path.lstrip('/').split('?')[0])
        path = os.path.join(UPD, name)
        if name.startswith('pkg/'):
            # a package file: only names listed in version.txt (no listing, no path tricks)
            try:
                listed = json.load(open(os.path.join(UPD, 'version.txt'))).get('package', {})
            except Exception:
                listed = {}
            rel = name[4:]
            if rel not in listed:
                self.send_error(404)
                return
            path = os.path.join(UPD, 'pkg', *rel.split('/'))
        elif name not in FILES:
            self.send_error(404)
            return
        if not os.path.isfile(path):
            self.send_error(404)
            return
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(size))
        self.end_headers()
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_POST(self):
        """/logs?pc=NAME&at=STAMP: a player's log zip from the launcher's "Send logs" (kept in share/update_inbox)."""
        import re
        from urllib.parse import urlparse, parse_qs
        u = urlparse(self.path)
        size = int(self.headers.get('Content-Length') or 0)
        if u.path != '/logs' or not 0 < size <= 200 * 1024 * 1024:
            self.send_error(400)
            return
        q = parse_qs(u.query)
        clean = lambda t: re.sub(r'[^A-Za-z0-9_-]', '', t)[:40]
        pc, at = clean(q.get('pc', ['pc'])[0]) or 'pc', clean(q.get('at', [''])[0])
        data = self.rfile.read(size)
        if data[:2] != b'PK':
            self.send_error(400)
            return
        inbox = os.path.join(WS, 'share', 'update_inbox')
        os.makedirs(inbox, exist_ok=True)
        import time
        name = 'DuskLogs_%s_%s_%s.zip' % (pc, at or time.strftime('%Y-%m-%d_%H%M%S'), self.client_address[0].replace('.', '-'))
        with open(os.path.join(inbox, name), 'wb') as f:
            f.write(data)
        body = ('saved as ' + name).encode('ascii')
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print('LOGS RECEIVED', name, len(data), flush=True)

    def log_message(self, fmt, *args):
        print(self.address_string(), fmt % args, flush=True)


def main():
    if len(sys.argv) > 1:
        publish(sys.argv[1])
    if not os.path.isfile(os.path.join(UPD, 'version.txt')):
        sys.exit('nothing published yet: give a zip')
    import subprocess
    import threading
    ips = [lan_ip()]
    try:   # read only: this PC's Tailscale / ZeroTier addresses, if connected (nothing is changed)
        sys.path.insert(0, os.path.join(WS, 'launcher_src'))
        import launcher_extras
        ips += [v['ip'] for v in launcher_extras.detect_vpns() if v['ip'] not in ips]
    except Exception as e:
        print('VPN detection failed:', e, flush=True)
    servers = []
    for ip in ips:
        try:
            servers.append(http.server.ThreadingHTTPServer((ip, PORT), Handler))
            print(f'serving the update on http://{ip}:{PORT}/ (version.txt, lichii.exe, nx2_switches.txt)', flush=True)
        except OSError as e:
            print(f'cannot serve on {ip}: {e}', flush=True)
    for srv in servers[1:]:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    servers[0].serve_forever()


if __name__ == '__main__':
    main()
